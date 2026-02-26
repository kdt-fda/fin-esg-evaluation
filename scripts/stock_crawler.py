import pymysql
import os
import pandas as pd
import pandas_ta as ta
from pykrx import stock
from datetime import datetime, timedelta
import time
import calendar
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor

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
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor
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

def get_last_update_date(ticker, cur):
    sql = "SELECT MAX(trade_date) as last_date FROM STOCK_TB WHERE ticker = %s"
    cur.execute(sql, (ticker,))
    result = cur.fetchone()

    # 결과가 딕셔너리 형태일 때 (이름으로 접근)
    if isinstance(result, dict) and result.get('last_date'):
        return (result['last_date'] + timedelta(days=1)).strftime("%Y%m%d")
    # 결과가 튜플 형태일 때 (인덱스로 접근)
    elif isinstance(result, (tuple, list)) and result[0]:
        return (result[0] + timedelta(days=1)).strftime("%Y%m%d")
    
    return "20220601"

# ==========================================
# 2. 데이터 수집 (시작일 2022-06-01 고정)
# ==========================================
def fetch_all_data(ticker, s_date):
    ticker = clean_ticker(ticker)
    e_date = datetime.now().strftime("%Y%m%d")
    
    # 지표 계산(MA120 등)을 위해 수집 시작일보다 200일 전 데이터부터 실제로 가져옴
    fetch_start = (datetime.strptime(s_date, "%Y%m%d") - timedelta(days=200)).strftime("%Y%m%d")
    
    try:
        # 1) 가격 정보
        df_price = stock.get_market_ohlcv(fetch_start, e_date, ticker)
        if df_price.empty: return pd.DataFrame()
        
        # 2) 수급 정보
        df_inv = stock.get_market_trading_value_by_date(fetch_start, e_date, ticker)
        df_inv = df_inv.rename(columns={'외국인합계':'Foreign_Net_Amt', '기관합계':'Inst_Net_Amt'})
        
        # 3) 공매도 정보
        try:
            df_short = stock.get_shorting_balance_by_date(fetch_start, e_date, ticker)
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
# 4. 개별 종목 처리 함수 (병렬용)
# ==========================================
def process_single_stock(target):
    if isinstance(target, dict):
        ticker, name = target['ticker'], target['stock_name']
    else:
        ticker, name = target[0], target[1]

    required_cols = ['MA5', 'MA20', 'MA60', 'MA120', 'BB_Upper', 'BB_Lower', 'BB_Breakout', 'RSI', 'MACD', 'MACD_Sig', 'GC_5_20', 'DC_5_20', 'MSCI_Event']
    
    conn = _connect()
    try:
        with conn.cursor() as cur:
            # 1. 마지막 날짜 확인
            s_date = get_last_update_date(ticker, cur)
            if s_date > datetime.now().strftime("%Y%m%d"):
                return f"✅ {name}({ticker}): 이미 최신 상태"

            # 2. 데이터 수집 및 지표 계산
            df = fetch_all_data(ticker, s_date)
            if df.empty: return f"⚠️ {name}({ticker}): 수집 데이터 없음"
            
            df = calculate_indicators(df)

            # 3. 신규 데이터 필터링 (s_date 이후만)
            df_to_save = df[df.index >= datetime.strptime(s_date, "%Y%m%d")].dropna(subset=required_cols)
            if df_to_save.empty: return f"ℹ️ {name}({ticker}): 추가할 신규 데이터 없음"

            data_list = []
            for date, row in df_to_save.iterrows():
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
            cur.executemany(sql, data_list)
            conn.commit()
            return f"🚀 {name}({ticker}): {len(data_list)}건 업데이트 완료"
            
    except Exception as e:
        return f"❌ {name}({ticker}) 에러: {e}"
    finally:
        conn.close()

# ==========================================
# 5. 메인 실행부 (병렬 처리 적용)
# ==========================================
def run_stock_crawler():
    targets = get_targets_from_db()
    if not targets: return
    
    print(f"🚀 {len(targets)}개 종목 병렬 증분 수집 시작 (Thread: 6)")
    
    # 🎯 ThreadPoolExecutor를 사용한 병렬 처리
    with ThreadPoolExecutor(max_workers=6) as executor:
        results = list(executor.map(process_single_stock, targets))
    
    for res in results:
        print(res)
        
    print(f"\n✅ STOCK_TB 모든 작업 완료!")

if __name__ == "__main__":
    run_stock_crawler()