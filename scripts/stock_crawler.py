import pymysql
import os
import pandas as pd
import pandas_ta as ta
from pykrx import stock
from datetime import datetime, timedelta
import time
import calendar
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

# ==========================================
# 1. DB 연결 설정
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
        database=db_name,
        charset='utf8mb4'
    )
    return conn

def clean_ticker(x):
    x = str(x).strip()
    if x.lower() == 'nan' or x == '': return ''
    if x.endswith('.0'): x = x[:-2]
    return x.zfill(6)

def get_targets_from_db():
    conn = _connect()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cur:
            cur.execute("SELECT ticker, stock_name FROM KOSPI200_STOCKS_TB WHERE is_active = TRUE;")
            return cur.fetchall()
    finally:
        conn.close()

# ==========================================
# 2. 데이터 수집 (시작일 2022-06-01 고정)
# ==========================================
def fetch_all_data(ticker):
    ticker = clean_ticker(ticker)
    # 2023-01-01에 MA120 지표를 만들기 위해 충분한 과거 데이터 확보
    s_date = "20220601"
    e_date = datetime.now().strftime("%Y%m%d")
    
    try:
        # 1) 가격 정보
        df_price = stock.get_market_ohlcv(s_date, e_date, ticker)
        if df_price.empty: return pd.DataFrame()
        
        # 2) 수급 정보
        df_inv = stock.get_market_trading_value_by_date(s_date, e_date, ticker)
        df_inv = df_inv.rename(columns={'외국인합계':'Foreign_Net_Amt', '기관합계':'Inst_Net_Amt'})
        
        # 3) 공매도 정보
        try:
            df_short = stock.get_shorting_balance_by_date(s_date, e_date, ticker)
            found_col = next((c for c in ['공매도잔고금액', '공매도금액', '잔고금액'] if c in df_short.columns), None)
            if found_col:
                df_short_val = df_short[[found_col]].rename(columns={found_col: 'Short_Balance'})
            else:
                df_short_val = pd.DataFrame(index=df_price.index); df_short_val['Short_Balance'] = 0
        except:
            df_short_val = pd.DataFrame(index=df_price.index); df_short_val['Short_Balance'] = 0

        df_merged = df_price.join(df_inv[['Foreign_Net_Amt', 'Inst_Net_Amt']], how='left')
        df_merged = df_merged.join(df_short_val, how='left')
            
        return df_merged.fillna(0)
    except Exception as e:
        print(f"⚠️ 수집 에러 ({ticker}): {e}")
        return pd.DataFrame()

# ==========================================
# 3. 기술적 지표 계산 (MSCI 멀티 연도 반영)
# ==========================================
def calculate_indicators(df):
    rename = {'시가':'Open', '고가':'High', '저가':'Low', '종가':'Close', '거래량':'Volume'}
    df = df.rename(columns=rename)
    
    if len(df) < 120: return df
    
    try:
        for ma in [5, 20, 60, 120]: 
            df[f'MA{ma}'] = df['Close'].rolling(window=ma).mean()
        
        bb = ta.bbands(df['Close'], length=20, std=2)
        if bb is not None:
            df['BB_Lower'], df['BB_Upper'] = bb.iloc[:, 0], bb.iloc[:, 2]
            df['BB_Breakout'] = ((df['Close'].shift(1) <= df['BB_Upper'].shift(1)) & (df['Close'] > df['BB_Upper'])).astype(int)
            
        df['GC_5_20'] = ((df['MA5'].shift(1) < df['MA20'].shift(1)) & (df['MA5'] > df['MA20'])).astype(int)
        df['DC_5_20'] = ((df['MA5'].shift(1) > df['MA20'].shift(1)) & (df['MA5'] < df['MA20'])).astype(int)
        
        df['RSI'] = ta.rsi(df['Close'], length=14)
        macd = ta.macd(df['Close'])
        if macd is not None:
            df['MACD'], df['MACD_Sig'] = macd.iloc[:, 0], macd.iloc[:, 2]
            
        # MSCI 이벤트 날짜 계산 (2022~현재)
        msci_dates = []
        curr_y = datetime.now().year
        for y in range(2022, curr_y + 1):
            for m in [2, 5, 8, 11]:
                last = calendar.monthrange(y, m)[1]
                b_days = pd.bdate_range(f"{y}-{m}-01", f"{y}-{m}-{last}")
                if not b_days.empty:
                    msci_dates.append(b_days[-1].strftime("%Y-%m-%d"))
        df['MSCI_Event'] = df.index.strftime('%Y-%m-%d').isin(msci_dates).astype(int)
        
    except: pass
    return df.fillna(0)

# ==========================================
# 4. 메인 실행 및 DB 전송 (executemany 최적화)
# ==========================================
def run_stock_crawler():
    targets = get_targets_from_db()
    if not targets: return
    
    print(f"🚀 {len(targets)}개 종목 2023-01-01 이후 전체 데이터 수집 시작")
    conn = _connect()

    required_cols = ['MA5', 'MA20', 'MA60', 'MA120', 'BB_Upper', 'BB_Lower', 'BB_Breakout', 'RSI', 'MACD', 'MACD_Sig', 'GC_5_20', 'DC_5_20', 'MSCI_Event']
    
    try:
        cur = conn.cursor()
        for i, target in enumerate(targets):
            ticker, name = target['ticker'], target['stock_name']
            
            df = fetch_all_data(ticker)
            if df.empty: continue
            df = calculate_indicators(df)

            # 필요한 컬럼이 모두 포함되어 있는지 확인
            missing_cols = [col for col in required_cols if col not in df.columns]
            if missing_cols:
                print(f"[{i+1}/{len(targets)}] {name}({ticker}): 지표 누락 ({missing_cols}) - Skip")
                continue
            
            # 2023-01-01 이후이면서 지표가 모두 계산된 행만 필터링
            df_to_save = df[(df.index >= "2023-01-01")].dropna(subset=required_cols)
            
            if df_to_save.empty:
                print(f"[{i+1}/{len(targets)}] {name}({ticker}): 데이터 부족 - Skip")
                continue

            data_list = []
            for date, row in df_to_save.iterrows():
                # executemany 에러 방지를 위해 numpy 타입을 기본 python 타입으로 변환
                val = (
                    date.strftime('%Y-%m-%d'), ticker, name,
                    int(row['Open']), int(row['High']), int(row['Low']), int(row['Close']), int(row['Volume']),
                    int(row['Foreign_Net_Amt']), int(row['Inst_Net_Amt']), int(row['Short_Balance']),
                    float(row['MA5']), float(row['MA20']), float(row['MA60']), float(row['MA120']),
                    float(row['BB_Upper']), float(row['BB_Lower']), int(row['BB_Breakout']),
                    int(row['MSCI_Event']), float(row['RSI']), float(row['MACD']), float(row['MACD_Sig']),
                    int(row['GC_5_20']), int(row['DC_5_20']), 0, 0
                )
                data_list.append(val)

            sql = """
                INSERT INTO STOCK_TB (trade_date, ticker, stock_name, open, high, low, close, volume, 
                                    foreign_net_amt, inst_net_amt, short_balance, 
                                    ma5, ma20, ma60, ma120, bb_upper, bb_lower, bb_breakout, 
                                    msci_event, rsi, macd, macd_signal, golden_cross_5_20, death_cross_5_20, 
                                    golden_cross_20_60, death_cross_20_60)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE 
                    close=VALUES(close), volume=VALUES(volume), short_balance=VALUES(short_balance),
                    foreign_net_amt=VALUES(foreign_net_amt), inst_net_amt=VALUES(inst_net_amt);
            """
            if data_list:
                cur.executemany(sql, data_list)
                conn.commit()
                print(f"[{i+1}/{len(targets)}] {name}({ticker}) {len(data_list)}건 완료")
            
            time.sleep(0.05)
            
        print(f"\n✅ STOCK_TB 업데이트 완료!")
    except Exception as e:
        print(f"\n❌ 에러: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    run_stock_crawler()