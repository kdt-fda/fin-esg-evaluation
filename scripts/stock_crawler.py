import pymysql
import os
import pandas as pd
import pandas_ta as ta
from pykrx import stock
from datetime import datetime, timedelta
import time
import calendar

# ==========================================
# 1. 설정값 & DB 연결 정보
# ==========================================
def _connect():
    host = os.environ.get('DB_HOST')
    port = int(os.environ.get('DB_PORT'))
    user = os.getenv('DB_USER')
    password = os.getenv('DB_PASSWORD')
    db_name = os.getenv('DB_NAME')

    conn = pymysql.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        database=db_name
    )

    return conn

# ==========================================
# 2. 티커(종목코드) 수리공 함수
# ==========================================
def clean_ticker(x):
    x = str(x).strip()
    if x.lower() == 'nan' or x == '': return ''
    if x.endswith('.0'): x = x[:-2]
    return x.zfill(6)

# ==========================================
# 3. 종목 리스트 획득 (CSV 대신 DB 조회로 대체)
# ==========================================
def get_targets_from_db():
    """KOSPI200_STOCKS_TB에서 활성 종목 리스트를 가져옵니다."""
    conn = _connect()

    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cur:
            cur.execute("SELECT ticker, stock_name FROM KOSPI200_STOCKS_TB WHERE is_active = TRUE;")
            return cur.fetchall()
    finally:
        conn.close()

# ==========================================
# 4. 데이터 수집 (가격 + 투자자 + 공매도 잔고)
# ==========================================
def fetch_all_data(ticker):
    ticker = clean_ticker(ticker)
    # 지표 계산을 위해 넉넉하게 200일 전부터 수집
    s_date = (datetime.now() - timedelta(days=200)).strftime("%Y%m%d")
    e_date = datetime.now().strftime("%Y%m%d")
    
    try:
        # 1) 가격 정보 (OHLCV)
        df_price = stock.get_market_ohlcv(s_date, e_date, ticker)
        if df_price.empty: return pd.DataFrame()
        
        # 2) 투자자 정보 (외인, 기관)
        df_inv = stock.get_market_trading_value_by_date(s_date, e_date, ticker)
        df_inv = df_inv.rename(columns={'외국인합계':'Foreign_Net_Amt', '기관합계':'Inst_Net_Amt'})
        
        # 3) 공매도 잔고 정보 (팀원 코드 로직 통합)
        try:
            df_short = stock.get_shorting_balance_by_date(s_date, e_date, ticker)
            # pykrx 버전에 따른 컬럼명 자동 수리
            found_col = next((c for c in ['공매도잔고금액', '공매도금액', '잔고금액'] if c in df_short.columns), None)
            if found_col:
                df_short_val = df_short[[found_col]].rename(columns={found_col: 'Short_Balance'})
            else:
                df_short_val = pd.DataFrame(index=df_price.index)
                df_short_val['Short_Balance'] = 0
        except:
            df_short_val = pd.DataFrame(index=df_price.index)
            df_short_val['Short_Balance'] = 0

        # 데이터 합치기
        df_merged = df_price.join(df_inv[['Foreign_Net_Amt', 'Inst_Net_Amt']], how='left')
        df_merged = df_merged.join(df_short_val, how='left')
            
        return df_merged.fillna(0)
    except Exception as e:
        print(f"⚠️ 수집 에러 ({ticker}): {e}")
        return pd.DataFrame()
    
# ==========================================
# 5. 지표 계산 (팀원 핵심 로직 반영)
# ==========================================
def calculate_indicators(df):
    rename = {'시가':'Open', '고가':'High', '저가':'Low', '종가':'Close', '거래량':'Volume'}
    df = df.rename(columns=rename)
    
    if len(df) < 120: return df
    
    try:
        # 이동평균선
        for ma in [5, 20, 60, 120]: 
            df[f'MA{ma}'] = df['Close'].rolling(window=ma).mean()
        
        # 볼린저 밴드
        bb = ta.bbands(df['Close'], length=20, std=2)
        if bb is not None:
            df['BB_Lower'], df['BB_Upper'] = bb.iloc[:, 0], bb.iloc[:, 2]
            df['BB_Breakout'] = ((df['Close'].shift(1) <= df['BB_Upper'].shift(1)) & (df['Close'] > df['BB_Upper'])).astype(int)
            
        # 골든/데드 크로스
        df['GC_5_20'] = ((df['MA5'].shift(1) < df['MA20'].shift(1)) & (df['MA5'] > df['MA20'])).astype(int)
        df['DC_5_20'] = ((df['MA5'].shift(1) > df['MA20'].shift(1)) & (df['MA5'] < df['MA20'])).astype(int)
        
        # RSI & MACD
        df['RSI'] = ta.rsi(df['Close'], length=14)
        macd = ta.macd(df['Close'])
        if macd is not None:
            df['MACD'], df['MACD_Sig'] = macd.iloc[:, 0], macd.iloc[:, 2]
            
        # MSCI 이벤트 (2, 5, 8, 11월 영업일 말일)
        msci_dates = []
        curr_y = datetime.now().year
        for m in [2, 5, 8, 11]:
            last = calendar.monthrange(curr_y, m)[1]
            msci_dates.append(pd.bdate_range(f"{curr_y}-{m}-01", f"{curr_y}-{m}-{last}")[-1].strftime("%Y-%m-%d"))
        df['MSCI_Event'] = df.index.strftime('%Y-%m-%d').isin(msci_dates).astype(int)
        
    except: pass
    return df.fillna(0)

# ==========================================
# 6. 메인 실행 및 DB 전송
# ==========================================
def run_stock_crawler():
    targets = get_targets_from_db()
    if not targets: return
    
    print(f"🚀 {len(targets)}개 종목 수집 및 DB(STOCK_TB) 전송 시작")
    conn = _connect()
    
    try:
        cur = conn.cursor()
        for i, target in enumerate(targets):
            ticker, name = target['ticker'], target['stock_name']
            print(f"[{i+1}/{len(targets)}] {name}({ticker}) 처리 중...", end="\r")
            
            df = fetch_all_data(ticker)
            if df.empty: continue
            df = calculate_indicators(df)
            
            latest = df.iloc[-1]
            trade_date = latest.name.strftime('%Y-%m-%d')
            
            # DB 구조(STOCK_TB) 컬럼 순서에 맞춰 튜플 생성
            val = (
                trade_date, ticker, name,
                int(latest['Open']), int(latest['High']), int(latest['Low']), int(latest['Close']),
                int(latest['Volume']), 
                int(latest['Foreign_Net_Amt']), int(latest['Inst_Net_Amt']), int(latest['Short_Balance']), # 수급+공매도
                float(latest['MA5']), float(latest['MA20']), float(latest['MA60']), float(latest['MA120']),
                float(latest['BB_Upper']), float(latest['BB_Lower']), int(latest['BB_Breakout']),
                int(latest['MSCI_Event']), float(latest['RSI']), float(latest['MACD']), float(latest['MACD_Sig']),
                int(latest['GC_5_20']), int(latest['DC_5_20']), 0, 0
            )

            # SQL (short_balance 컬럼 반영)
            sql = """
                INSERT INTO STOCK_TB (trade_date, ticker, stock_name, open, high, low, close, volume, 
                                    foreign_net_amt, inst_net_amt, short_balance, 
                                    ma5, ma20, ma60, ma120, bb_upper, bb_lower, bb_breakout, 
                                    msci_event, rsi, macd, macd_signal, golden_cross_5_20, death_cross_5_20, 
                                    golden_cross_20_60, death_cross_20_60)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE close=VALUES(close), volume=VALUES(volume), short_balance=VALUES(short_balance);
            """
            cur.execute(sql, val)
            time.sleep(0.05)
            
        conn.commit()
        print(f"\n✅ STOCK_TB 업데이트 완료! ({datetime.now()})")
    except Exception as e:
        print(f"\n❌ 에러: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    run_stock_crawler()