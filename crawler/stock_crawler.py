import os
import requests
import pymysql
import pandas as pd
import pandas_ta as ta
from pykrx import stock
from datetime import datetime, timedelta
import calendar
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor
from pykrx.website.comm import webio

# .env 파일 로드
load_dotenv()

# ==========================================
# 0. 전역 세션 패치
# ==========================================
_session = requests.Session()
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"

webio.Post.read = lambda self, **params: _session.post(self.url, headers=self.headers, data=params, timeout=15)
webio.Get.read = lambda self, **params: _session.get(self.url, headers=self.headers, params=params, timeout=15)

def login_to_krx():
    """KRX 데이터 포털 로그인 로직 (세션 획득용)"""
    KRX_ID = os.getenv("KRX_ID")
    KRX_PW = os.getenv("KRX_PW")
    
    if not KRX_ID or not KRX_PW:
        print("⚠️ KRX 계정 정보가 .env에 없습니다. 익명 세션으로 진행합니다.")
        return False

    _LOGIN_PAGE = "https://data.krx.co.kr/contents/MDC/COMS/client/MDCCOMS001.cmd"
    _LOGIN_JSP  = "https://data.krx.co.kr/contents/MDC/COMS/client/view/login.jsp?site=mdc"
    _LOGIN_URL = "https://data.krx.co.kr/contents/MDC/COMS/client/MDCCOMS001D1.cmd"

    try:
        _session.get(_LOGIN_PAGE, headers={"User-Agent": _UA})
        _session.get(_LOGIN_JSP, headers={"User-Agent": _UA, "Referer": _LOGIN_PAGE})
        payload = {"mbrId": KRX_ID, "pw": KRX_PW}
        resp = _session.post(_LOGIN_URL, data=payload, headers={"User-Agent": _UA, "Referer": _LOGIN_PAGE})
        
        if resp.json().get("_error_code") in ["CD001", "CD011"]:
            print("✅ KRX 로그인 성공 및 세션 유지 중")
            return True
        return False
    except:
        return False

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

def safe_int(val):
    if pd.isna(val) or val is None or val == '': return None
    try: return int(float(val))
    except: return None

def safe_float(val):
    if pd.isna(val) or val is None or val == '': return None
    try: return float(val)
    except: return None

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

    if isinstance(result, dict) and result.get('last_date'):
        return result['last_date'].strftime("%Y%m%d")
    elif isinstance(result, (tuple, list)) and result[0]:
        return result[0].strftime("%Y%m%d")
    
    return "20220601"

# ==========================================
# 2. 데이터 수집
# ==========================================
def fetch_all_data(ticker, s_date):
    ticker = clean_ticker(ticker)
    e_date = datetime.now().strftime("%Y%m%d")
    
    fetch_start = (datetime.strptime(s_date, "%Y%m%d") - timedelta(days=200)).strftime("%Y%m%d")
    
    try:
        # 1) 가격 정보
        df_price = stock.get_market_ohlcv(fetch_start, e_date, ticker)
        if df_price.empty: return pd.DataFrame()
        
        # 2) 수급 정보
        df_inv = pd.DataFrame(index=df_price.index, columns=['Foreign_Net_Amt', 'Inst_Net_Amt'])
        try:
            temp_inv = stock.get_market_trading_value_by_date(fetch_start, e_date, ticker)
            if not temp_inv.empty and '외국인합계' in temp_inv.columns:
                df_inv['Foreign_Net_Amt'] = temp_inv['외국인합계']
                df_inv['Inst_Net_Amt'] = temp_inv['기관합계']
        except: pass

        # 3) 공매도 정보
        df_short = pd.DataFrame(index=df_price.index, columns=['Short_Balance'])
        try:
            df_short_raw = stock.get_shorting_balance_by_date(fetch_start, e_date, ticker)
            if not df_short_raw.empty:
                target_cols = ['공매도금액', '공매도잔고금액', '잔고금액']
                found_col = next((c for c in target_cols if c in df_short_raw.columns), None)

                if found_col:
                    df_short['Short_Balance'] = df_short_raw[found_col].reindex(df_price.index, method='nearest')
        except: pass

        df_merged = df_price.join(df_inv, how='left').join(df_short, how='left')
        return df_merged
    
    except Exception as e:
        print(f"⚠️ 수집 에러 ({ticker}): {e}")
        return pd.DataFrame()

# ==========================================
# 3. 기술적 지표 계산 (MSCI 멀티 연도 반영)
# ==========================================
def calculate_indicators(df):
    rename = {'시가':'Open', '고가':'High', '저가':'Low', '종가':'Close', '거래량':'Volume'}
    df = df.rename(columns=rename)

    indicator_cols = ['MA5', 'MA20', 'MA60', 'MA120', 'BB_Upper', 'BB_Lower', 'BB_Breakout',
                      'RSI', 'MACD', 'MACD_Sig', 'GC_5_20', 'DC_5_20', 'GC_20_60', 'DC_20_60', 'MSCI_Event']
    for col in indicator_cols:
        if col not in df.columns:
            df[col] = None
    
    try:
        for ma in [5, 20, 60, 120]: 
            df[f'MA{ma}'] = df['Close'].rolling(window=ma).mean()
        
        bb = ta.bbands(df['Close'], length=20, std=2)
        if bb is not None:
            df['BB_Lower'], df['BB_Upper'] = bb.iloc[:, 0], bb.iloc[:, 2]
            df['BB_Breakout'] = ((df['Close'].shift(1) <= df['BB_Upper'].shift(1)) & (df['Close'] > df['BB_Upper'])).astype(int)
            
        df['GC_5_20'] = ((df['MA5'].shift(1) < df['MA20'].shift(1)) & (df['MA5'] > df['MA20'])).astype(int)
        df['DC_5_20'] = ((df['MA5'].shift(1) > df['MA20'].shift(1)) & (df['MA5'] < df['MA20'])).astype(int)

        df['GC_20_60'] = ((df['MA20'].shift(1) < df['MA60'].shift(1)) & (df['MA20'] > df['MA60'])).astype(int)
        df['DC_20_60'] = ((df['MA20'].shift(1) > df['MA60'].shift(1)) & (df['MA20'] < df['MA60'])).astype(int)
        
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
    return df

# ==========================================
# 4. 개별 종목 처리 함수 (병렬용)
# ==========================================
def process_single_stock(target):
    if isinstance(target, dict):
        ticker, name = target['ticker'], target['stock_name']
    else:
        ticker, name = target[0], target[1]
    
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
            target_start = max(datetime.strptime(s_date, "%Y%m%d"), datetime(2023, 1, 1))
            df_to_save = df[df.index >= target_start]
            if df_to_save.empty: return f"ℹ️ {name}({ticker}): 추가할 신규 데이터 없음"

            data_list = []
            for date, row in df_to_save.iterrows():
                val = (
                    date.strftime('%Y-%m-%d'), ticker, name,
                    safe_int(row.get('Open')), safe_int(row.get('High')), safe_int(row.get('Low')),
                    safe_int(row.get('Close')), safe_int(row.get('Volume')), safe_int(row.get('Foreign_Net_Amt')),
                    safe_int(row.get('Inst_Net_Amt')), safe_int(row.get('Short_Balance')),
                    safe_float(row.get('MA5')), safe_float(row.get('MA20')), safe_float(row.get('MA60')),
                    safe_float(row.get('MA120')), safe_float(row.get('BB_Upper')), safe_float(row.get('BB_Lower')),
                    safe_int(row.get('BB_Breakout')), safe_int(row.get('MSCI_Event')), safe_float(row.get('RSI')),
                    safe_float(row.get('MACD')), safe_float(row.get('MACD_Sig')), safe_int(row.get('GC_5_20')),
                    safe_int(row.get('DC_5_20')), safe_int(row.get('GC_20_60')), safe_int(row.get('DC_20_60'))
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
                    open=VALUES(open), high=VALUES(high), low=VALUES(low),
                    close=VALUES(close), volume=VALUES(volume), short_balance=VALUES(short_balance),
                    foreign_net_amt=VALUES(foreign_net_amt), inst_net_amt=VALUES(inst_net_amt),
                    ma5=VALUES(ma5), ma20=VALUES(ma20), ma60=VALUES(ma60), ma120=VALUES(ma120),
                    bb_upper=VALUES(bb_upper), bb_lower=VALUES(bb_lower), bb_breakout=VALUES(bb_breakout),
                    rsi=VALUES(rsi), macd=VALUES(macd), macd_signal=VALUES(macd_signal),
                    msci_event=VALUES(msci_event), golden_cross_5_20=VALUES(golden_cross_5_20),
                    death_cross_5_20=VALUES(death_cross_5_20), golden_cross_20_60=VALUES(golden_cross_20_60),
                    death_cross_20_60=VALUES(death_cross_20_60);
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
    login_to_krx()

    targets = get_targets_from_db()
    if not targets: return
    
    print(f"🚀 {len(targets)}개 종목 수집 시작 (Thread: 6)")
    
    with ThreadPoolExecutor(max_workers=6) as executor:
        results = list(executor.map(process_single_stock, targets))
    
    for res in results:
        print(res)
        
    print(f"\n✅ STOCK_TB 모든 작업 완료!")

if __name__ == "__main__":
    run_stock_crawler()