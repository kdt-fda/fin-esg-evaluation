import os
import requests
import pymysql
import numpy as np
import pandas as pd
import FinanceDataReader as fdr
import yfinance as yf
from datetime import datetime
from pandas.tseries.offsets import Day, DateOffset
from dotenv import load_dotenv

load_dotenv()

# ============================================================
# 1. 공통 설정 및 DB 유틸리티
# ============================================================
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

USER_START_DATE = '2023-01-01'
FETCH_START_DATE = (pd.to_datetime(USER_START_DATE) - Day(300)).strftime('%Y-%m-%d')
END_DATE = datetime.now().strftime('%Y-%m-%d')

ECOS_START_YM = (pd.to_datetime(USER_START_DATE) - DateOffset(months=30)).strftime('%Y%m')

def get_tickers_by_sector(sector_code):
    conn = _connect()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cur:
            sql = "SELECT ticker, stock_name FROM KOSPI200_STOCKS_TB WHERE sector_code = %s AND is_active = TRUE"
            cur.execute(sql, (sector_code,))
            return cur.fetchall()
    finally:
        conn.close()

# ============================================================
# HELPER 함수
# ============================================================
class EcosClient:
    BASE_URL = "https://ecos.bok.or.kr/api"

    def __init__(self):
        self.api_key = os.getenv("ECOS_API_KEY")
        if not self.api_key:
            raise ValueError("❌ ECOS_API_KEY가 설정되지 않았습니다.")

    def fetch_data(self, stat_code, start, end, *item_codes, cycle="M"):
        """
        가변 인자를 사용하여 여러 항목 코드(AA, F4100 등)를 처리하는 안정화 버전
        사용 예: ecos.fetch_data('512Y007', '202101', '202512', 'AA', 'F4100')
        """
        # 1. 가변 인자로 들어온 항목 코드들을 슬래시(/)로 결합
        item_path = "/".join(item_codes) if item_codes else ""
        
        # 2. API URL 구성 (인자 순서: 서비스명/키/형식/언어/시작/종료/통계표/주기/시작/종료/항목...)
        url = f"{self.BASE_URL}/StatisticSearch/{self.api_key}/json/kr/1/500/{stat_code}/{cycle}/{start}/{end}"
        if item_path:
            url += f"/{item_path}"

        try:
            resp = requests.get(url, timeout=30).json()
            rows = resp.get("StatisticSearch", {}).get("row", [])
            
            if not rows:
                # 데이터가 없을 경우 빈 DF 반환 (에러 방지)
                return pd.DataFrame(columns=['Date', 'Value'])
            
            df = pd.DataFrame(rows)
            # 날짜 형식 표준화 (YYYYMM -> YYYY-MM-01)
            df['Date'] = pd.to_datetime(df['TIME'], format='%Y%m', errors='coerce').dt.normalize()
            # 데이터 수치화
            df['Value'] = pd.to_numeric(df['DATA_VALUE'], errors='coerce')
            
            return df[['Date', 'Value']].dropna().sort_values('Date').reset_index(drop=True)
            
        except Exception as e:
            print(f"📡 ECOS API 호출 중 오류 발생: {e}")
            return pd.DataFrame(columns=['Date', 'Value'])

def safe_fetch_fdr(ticker, start, end, col_name='Close'):
    try:
        df = fdr.DataReader(ticker, start, end)
        if df is None or df.empty: return pd.DataFrame()
        df = df.reset_index()
        df.columns = [c.capitalize() if c.lower() == 'date' else c for c in df.columns]
        df['Date'] = pd.to_datetime(df['Date']).dt.normalize()
        val_col = 'Close' if 'Close' in df.columns else df.columns[1]
        return df[['Date', val_col]].rename(columns={val_col: col_name})
    except: return pd.DataFrame()

def safe_fetch_yf(ticker, start, end, col_name):
    """
    yfinance를 사용하여 데이터를 수집하고 형식을 표준화합니다.
    (MultiIndex 해제, 타임존 제거, 날짜 형식 통일)
    """
    try:
        # progress=False로 로그 출력을 최소화합니다.
        data = yf.download(ticker, start=start, end=end, progress=False)
        
        if data.empty:
            print(f"⚠️ yfinance 데이터 부재: {ticker}")
            return pd.DataFrame(columns=['Date', col_name])
        
        # MultiIndex인 경우 'Close' 컬럼만 추출
        if isinstance(data.columns, pd.MultiIndex):
            df = data['Close'].iloc[:, 0].reset_index()
        else:
            df = data['Close'].reset_index()
            
        df.columns = ['Date', col_name]
        
        # [핵심] 타임존 제거 및 날짜 정규화 (MergeError 방지)
        df['Date'] = pd.to_datetime(df['Date']).dt.tz_localize(None).dt.normalize()
        
        return df.sort_values('Date').drop_duplicates('Date').reset_index(drop=True)
    
    except Exception as e:
        print(f"❌ yfinance 수집 중 오류 ({ticker}): {e}")
        return pd.DataFrame(columns=['Date', col_name])

# ============================================================
# 2. 섹터별 계산 함수 (이 아래부터 하나씩 추가)
# ============================================================

# --- [COMM] 커뮤니케이션서비스 섹터 (Communication Services) ---
def process_communication_service():
    """
    커뮤니케이션서비스 섹터 지표 계산 및 COMM_TB 적재
    지표: 나스닥 상관계수(corr_ndx), 금리 베타(interest_beta), 산업 Z-score(z_score)
    """
    print("🚀 [COMM] 커뮤니케이션서비스 섹터 처리 시작...")
    
    # 1. DB에서 종목 리스트 조회 (sector_code: 'COMM')
    stocks = get_tickers_by_sector('COMM')
    if not stocks:
        print("⚠️ COMM 섹터에 해당하는 활성 종목이 DB에 없습니다.")
        return

    # 2. 외부 공통 지표 수집 (나스닥, 미국채 10년물, 산업 ETF)
    # TIGER 200 커뮤니케이션서비스(315270)
    print("📡 나스닥, 금리, 산업 ETF 데이터 수집 중...")
    ndx = safe_fetch_yf('^NDX', FETCH_START_DATE, END_DATE, 'NDX_Close')
    us10yt = safe_fetch_yf('^TNX', FETCH_START_DATE, END_DATE, 'US10YT_Close')
    etf = safe_fetch_fdr('315270', FETCH_START_DATE, END_DATE, 'ETF_Close')
    
    if ndx.empty or us10yt.empty or etf.empty:
        print("❌ 외부 지표 수집 실패로 COMM 섹터 계산을 건너뜁니다.")
        return

    all_results = []

    # 3. 종목별 계산 루프
    for s in stocks:
        ticker, name = s['ticker'], s['stock_name']
        print(f"📡 {name}({ticker}) 지표 산출 중...")
        
        df = safe_fetch_fdr(ticker, FETCH_START_DATE, END_DATE, 'Close')
        if df.empty: continue
        
        # 외부 지표 병합 및 결측치 보정
        m = pd.merge(df, ndx, on='Date', how='left')
        m = pd.merge(m, us10yt, on='Date', how='left')
        m = pd.merge(m, etf, on='Date', how='left')
        
        m = m.sort_values('Date').ffill().bfill()
        
        # [계산 로직]
        s_ret = m['Close'].pct_change()
        n_ret = m['NDX_Close'].shift(1).pct_change() # 나스닥 전일 대비
        i_ret = m['US10YT_Close'].pct_change()      # 금리 변동
        
        # (1) 나스닥 상관계수 (60일)
        m['corr_ndx'] = s_ret.rolling(60).corr(n_ret)
        
        # (2) 금리 베타 (60일)
        cov = s_ret.rolling(60).cov(i_ret)
        var = i_ret.rolling(60).var()
        m['interest_beta'] = (cov / (var + 1e-10)).clip(-10, 10)
        
        # (3) 산업 Z-score (120일) - 상대 강도
        rel_price = m['Close'] / (m['ETF_Close'] + 1e-10)
        m['z_score'] = (rel_price - rel_price.rolling(120).mean()) / (rel_price.rolling(120).std() + 1e-10)
        
        m['ticker'] = ticker
        all_results.append(m[m['Date'] >= USER_START_DATE])

    # 4. DB 적재
    if all_results:
        final_df = pd.concat(all_results).replace({np.nan: None})
        conn = _connect()
        try:
            cur = conn.cursor()
            sql = """
                INSERT INTO COMM_TB (trade_date, ticker, corr_ndx, interest_beta, z_score)
                VALUES (%s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    corr_ndx=VALUES(corr_ndx),
                    interest_beta=VALUES(interest_beta),
                    z_score=VALUES(z_score);
            """
            data = [
                (row['Date'], row['ticker'], row['corr_ndx'], row['interest_beta'], row['z_score']) 
                for _, row in final_df.iterrows()
            ]
            cur.executemany(sql, data)
            conn.commit()
            print(f"✅ COMM_TB 업데이트 완료: {len(final_df)}건")
        except Exception as e:
            print(f"❌ COMM 섹터 적재 에러: {e}")
            conn.rollback()
        finally:
            conn.close()

# --- [CD] 경기소비재 섹터 (Consumer Discretionary) ---
def process_consumer_discretionary():
    """
    경기소비재 섹터 지표 계산 및 CONS_DISC_TB 적재
    지표: 소득 모멘텀(purchasing_power_mom), 금리 베타(durables_ir_beta), 
          소비자심리(csi_sentiment), 선행지수(cli_lag), 산업 Z-score(z_score)
    """
    print("🚀 [CD] 경기소비재 섹터 처리 시작...")
    
    # 1. DB에서 종목 리스트 조회 (sector_code: 'CD')
    stocks = get_tickers_by_sector('CD')
    if not stocks:
        print("⚠️ CD 섹터에 해당하는 활성 종목이 DB에 없습니다.")
        return

    # 2. 외부 공통 지표 수집 (FRED, ECOS, ETF)
    ecos = EcosClient()
    ecos_start = pd.to_datetime(FETCH_START_DATE).strftime("%Y%m")
    ecos_end = datetime.now().strftime("%Y%m")

    # ECOS: 소비자심리지수(511Y002-FME), 선행종합지수(901Y067-I16A)
    print("📡 ECOS 소비자심리 및 경기선행지수 수집 중...")
    csi_raw = ecos.fetch_data('511Y002', ecos_start, ecos_end, 'FME')
    cli_raw = ecos.fetch_data('901Y067', ecos_start, ecos_end, 'I16A')
    
    macro_df = pd.DataFrame(columns=['Date'])
    if not csi_raw.empty:
        csi_raw['csi_sentiment'] = csi_raw['Value'].shift(2) # 2개월 선행성
        macro_df = csi_raw[['Date', 'csi_sentiment']]
    if not cli_raw.empty:
        cli_raw['cli_lag'] = cli_raw['Value'].shift(3) # 3개월 선행성
        if macro_df.empty: 
            macro_df = cli_raw[['Date', 'cli_lag']]
        else: 
            macro_df = pd.merge(macro_df, cli_raw[['Date', 'cli_lag']], on='Date', how='outer')

    # FRED 및 산업 ETF (TIGER 경기소비재: 139290)
    print("📡 FRED 실질가처분소득 및 금리 데이터 수집 중...")
    real_dpi = safe_fetch_fdr('FRED:DSPIC96', FETCH_START_DATE, END_DATE, 'Real_DPI')
    dgs10 = safe_fetch_fdr('FRED:DGS10', FETCH_START_DATE, END_DATE, 'US10Y')
    tiger_cd = safe_fetch_fdr('139290', FETCH_START_DATE, END_DATE, 'ETF_Close')

    all_results = []

    # 3. 종목별 계산 루프
    for s in stocks:
        ticker, name = s['ticker'], s['stock_name']
        print(f"📡 {name}({ticker}) 지표 산출 중...")
        
        df = safe_fetch_fdr(ticker, FETCH_START_DATE, END_DATE, 'Close')
        if df.empty: continue
        
        # 데이터 병합
        m = pd.merge(df, tiger_cd, on='Date', how='left')
        m = pd.merge(m, real_dpi, on='Date', how='left')
        m = pd.merge(m, dgs10, on='Date', how='left')
        
        # 월간 매크로 지표 Merge Asof
        if not macro_df.empty:
            m = pd.merge_asof(m.sort_values('Date'), macro_df.sort_values('Date'), 
                              on='Date', direction='backward')

        # 결측치 보정 (기업별 ffill)
        fill_cols = ['ETF_Close', 'Real_DPI', 'US10Y', 'csi_sentiment', 'cli_lag']
        m[fill_cols] = m[fill_cols].ffill().bfill()

        # [계산 로직]
        m = m.sort_values('Date')
        # (1) 소득 모멘텀 (60일)
        m['purchasing_power_mom'] = m['Real_DPI'].pct_change(60)
        
        # (2) 금리 민감도 (Beta)
        ir_ret = m['US10Y'].shift(1).pct_change()
        ir_var = ir_ret.rolling(60).var()
        m['durables_ir_beta'] = (m['Close'].pct_change().rolling(60).cov(ir_ret) / (ir_var + 1e-9)).clip(-10, 10)
        
        # (3) Z-score (상상대 강도)
        rel_price = m['Close'] / (m['ETF_Close'] + 1e-9)
        m['z_score'] = (rel_price - rel_price.rolling(120).mean()) / (rel_price.rolling(120).std() + 1e-9)
        
        m['ticker'] = ticker
        all_results.append(m[m['Date'] >= USER_START_DATE])

    # 4. DB 적재
    if all_results:
        final_df = pd.concat(all_results).replace({np.nan: None})
        conn = _connect()
        try:
            cur = conn.cursor()
            sql = """
                INSERT INTO CONS_DISC_TB (trade_date, ticker, purchasing_power_mom, durables_ir_beta, csi_sentiment, cli_lag, z_score)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    purchasing_power_mom=VALUES(purchasing_power_mom),
                    durables_ir_beta=VALUES(durables_ir_beta),
                    csi_sentiment=VALUES(csi_sentiment),
                    cli_lag=VALUES(cli_lag),
                    z_score=VALUES(z_score);
            """
            data = [
                (row['Date'], row['ticker'], row['purchasing_power_mom'], row['durables_ir_beta'], 
                 row['csi_sentiment'], row['cli_lag'], row['z_score']) 
                for _, row in final_df.iterrows()
            ]
            cur.executemany(sql, data)
            conn.commit()
            print(f"✅ CONS_DISC_TB 업데이트 완료: {len(final_df)}건")
        except Exception as e:
            print(f"❌ CD 섹터 적재 에러: {e}")
            conn.rollback()
        finally:
            conn.close()

# --- [CS] 생활소비재 섹터 (Consumer Staples) ---
def process_consumer_staples():
    """
    생활소비재 섹터 지표 계산 및 CONS_STAPLES_TB 적재
    지표: 실질 성장률(cpi 차감), 에비타 마진, 소비자심리, 상대강도 Z-score
    """
    print("🚀 [CS] 생활소비재 섹터 처리 시작...")
    stocks = get_tickers_by_sector('CS')
    if not stocks: return
    ticker_list = [s['ticker'] for s in stocks]

    ecos = EcosClient()
    ecos_start, ecos_end = pd.to_datetime(FETCH_START_DATE).strftime("%Y%m"), datetime.now().strftime("%Y%m")
    csi_raw = ecos.fetch_data('511Y002', ecos_start, ecos_end, 'FME')
    cpi_raw = ecos.fetch_data('901Y009', ecos_start, ecos_end, '0')
    
    # 매크로 데이터프레임 구조 강제 정의
    macro_df = pd.DataFrame(columns=['Date', 'csi_sentiment', 'cpi_yoy'])
    if not csi_raw.empty:
        csi_raw['csi_sentiment'] = csi_raw['Value'].shift(3)
        macro_df = pd.merge(macro_df, csi_raw[['Date', 'csi_sentiment']], on='Date', how='outer')
    if not cpi_raw.empty:
        cpi_raw['cpi_yoy'] = cpi_raw['Value'].pct_change(12)
        macro_df = pd.merge(macro_df, cpi_raw[['Date', 'cpi_yoy']], on='Date', how='outer')
    macro_df['Date'] = pd.to_datetime(macro_df['Date']).dt.normalize()

    usd_krw = safe_fetch_yf('USDKRW=X', FETCH_START_DATE, END_DATE, 'USD_KRW')
    tiger_cs = safe_fetch_fdr('227560', FETCH_START_DATE, END_DATE, 'ETF_Close')

    conn = _connect()
    try:
        # end_date를 Date로 확실히 Alias
        funda_sql = f"SELECT ticker, end_date as Date, revenue_growth, ebitda, revenue FROM FUNDAMENTAL_TB WHERE ticker IN ({str(ticker_list)[1:-1]})"
        df_funda = pd.read_sql(funda_sql, conn)
        df_funda['Date'] = pd.to_datetime(df_funda['Date']).dt.normalize()
    finally:
        conn.close()

    all_results = []
    for s in stocks:
        ticker, name = s['ticker'], s['stock_name']
        print(f"📡 {name}({ticker}) 지표 산출 중...")
        df = safe_fetch_fdr(ticker, FETCH_START_DATE, END_DATE, 'Close')
        if df.empty: continue
        
        # 1. 기초 병합
        m = pd.merge(df, tiger_cs, on='Date', how='left')
        m = pd.merge(m, usd_krw, on='Date', how='left')
        m = m.sort_values('Date')
        
        # 2. 매크로 병합 (컬럼 없으면 생성)
        if not macro_df.empty:
            m = pd.merge_asof(m, macro_df.sort_values('Date'), on='Date', direction='backward')
        for col in ['csi_sentiment', 'cpi_yoy']:
            if col not in m.columns: m[col] = np.nan

        # 3. 펀더멘털 병합 (컬럼 없으면 생성)
        stock_funda = df_funda[df_funda['ticker'] == ticker].sort_values('Date')
        if not stock_funda.empty:
            m = pd.merge_asof(m, stock_funda.drop(columns=['ticker']), on='Date', direction='backward')
        for col in ['revenue_growth', 'ebitda', 'revenue']:
            if col not in m.columns: m[col] = np.nan

        # 4. [계산] 0 채우기 없이 진행 -> 결과가 NaN이면 DB에 NULL로 들어감
        m['real_revenue_growth'] = m['revenue_growth'] - m['cpi_yoy']
        m['ebitda_margin'] = m['ebitda'] / m['revenue']
        rel_price = m['Close'] / (m['ETF_Close'] + 1e-9)
        m['z_score'] = (rel_price - rel_price.rolling(120).mean()) / (rel_price.rolling(120).std() + 1e-9)
        
        m['ticker'] = ticker
        all_results.append(m[m['Date'] >= USER_START_DATE])

    # 5. DB 적재
    if all_results:
        final_df = pd.concat(all_results).replace({np.nan: None})
        conn = _connect()
        try:
            cur = conn.cursor()
            sql = """
                INSERT INTO CONS_STAPLES_TB (trade_date, ticker, real_revenue_growth, ebitda_margin, csi_sentiment, z_score)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    real_revenue_growth=VALUES(real_revenue_growth),
                    ebitda_margin=VALUES(ebitda_margin),
                    csi_sentiment=VALUES(csi_sentiment),
                    z_score=VALUES(z_score);
            """
            data = [
                (row['Date'], row['ticker'], row['real_revenue_growth'], row['ebitda_margin'], 
                 row['csi_sentiment'], row['z_score']) 
                for _, row in final_df.iterrows()
            ]
            cur.executemany(sql, data)
            conn.commit()
            print(f"✅ CONS_STAPLES_TB 업데이트 완료: {len(final_df)}건")
        except Exception as e:
            print(f"❌ CS 섹터 적재 에러: {e}")
            conn.rollback()
        finally:
            conn.close()

# --- [CONS] 건설 섹터 (Construction) ---
def process_construction():
    """
    건설 섹터 지표 계산 및 CONSTRUCTION_TB 적재
    지표: 금리 베타(interest_beta), 환율 상관성(fx_correlation), 
          업황 BSI 모멘텀(bsi_momentum), 제조업 지수 시차(mfg_lag3), 산업 Z-score
    """
    print("🚀 [CONS] 건설 섹터 처리 시작...")
    
    # 1. DB에서 종목 리스트 조회 (sector_code: 'CONS')
    stocks = get_tickers_by_sector('CONS')
    if not stocks:
        print("⚠️ CONS 섹터에 해당하는 활성 종목이 DB에 없습니다.")
        return

    # 2. 외부 데이터 수집 (ECOS, FinanceDataReader, Yahoo Finance)
    ecos = EcosClient()
    ecos_start = pd.to_datetime(FETCH_START_DATE).strftime("%Y%m")
    ecos_end = datetime.now().strftime("%Y%m")

    # ECOS: 건설업 업황실적BSI(512Y007-AA-F4100), 제조업 지수(901Y032-I11AC)
    print("📡 ECOS 건설 BSI 및 제조업 지수 수집 중...")
    bsi_raw = ecos.fetch_data('512Y007', ecos_start, ecos_end, 'AA', 'F4100') # item_code 합쳐서 전달
    mfg_raw = ecos.fetch_data('901Y032', ecos_start, ecos_end, 'I11AC')

    # BSI 모멘텀 가공 (포인트 변화 -> 표준화)
    if not bsi_raw.empty:
        bsi_raw['bsi_diff_3m'] = bsi_raw['Value'].diff(3)
        roll = bsi_raw['bsi_diff_3m'].rolling(12, min_periods=6)
        bsi_raw['bsi_momentum'] = (bsi_raw['bsi_diff_3m'] - roll.mean()) / (roll.std() + 1e-9)
    
    macro_df = pd.DataFrame(columns=['Date'])
    if not bsi_raw.empty:
        macro_df = bsi_raw[['Date', 'bsi_momentum']].copy()
    if not mfg_raw.empty:
        mfg_raw['mfg_idx'] = mfg_raw['Value']
        if macro_df.empty: macro_df = mfg_raw[['Date', 'mfg_idx']]
        else: macro_df = pd.merge(macro_df, mfg_raw[['Date', 'mfg_idx']], on='Date', how='outer')

    # 환율, 국채 금리, 섹터 ETF (TIGER 200 건설: 139220)
    print("📡 환율, 금리 및 건설 ETF 데이터 수집 중...")
    usd_krw = safe_fetch_yf('USDKRW=X', FETCH_START_DATE, END_DATE, 'USD_KRW')
    kr10yt = safe_fetch_fdr('INVESTING:KR10YT=RR', FETCH_START_DATE, END_DATE, 'KR10Y')
    tiger_cons = safe_fetch_fdr('139220', FETCH_START_DATE, END_DATE, 'ETF_Close')

    all_results = []

    # 3. 종목별 계산 루프
    for s in stocks:
        ticker, name = s['ticker'], s['stock_name']
        print(f"📡 {name}({ticker}) 지표 산출 중...")
        
        df = safe_fetch_fdr(ticker, FETCH_START_DATE, END_DATE, 'Close')
        if df.empty: continue
        
        # 기본 병합
        m = pd.merge(df, tiger_cons, on='Date', how='left')
        
        # Asof 병합 (환율, 금리, 매크로)
        m = m.sort_values('Date')
        for extra_df in [usd_krw, kr10yt, macro_df]:
            if not extra_df.empty:
                extra_df['Date'] = pd.to_datetime(extra_df['Date'])
                m = pd.merge_asof(m, extra_df.sort_values('Date'), on='Date', direction='backward')

        # 결측치 보정
        fill_cols = ['USD_KRW', 'KR10Y', 'ETF_Close', 'bsi_momentum', 'mfg_idx']
        m[fill_cols] = m[fill_cols].ffill().bfill()

        # [계산 로직]
        s_ret = m['Close'].pct_change()
        # (1) 금리 민감도
        i_ret = m['KR10Y'].pct_change()
        m['interest_beta'] = (s_ret.rolling(60).cov(i_ret) / (i_ret.rolling(60).var() + 1e-10)).clip(-10, 10)
        
        # (2) 환율 상관성
        u_ret = m['USD_KRW'].pct_change()
        m['fx_correlation'] = s_ret.rolling(60).corr(u_ret)
        
        # (3) 제조업 지수 시차 (3개월)
        m['mfg_lag3'] = m['mfg_idx'].shift(60)
        
        # (4) Z-score (산업 상대 강도)
        rel_price = m['Close'] / (m['ETF_Close'] + 1e-9)
        m['z_score'] = (rel_price - rel_price.rolling(120).mean()) / (rel_price.rolling(120).std() + 1e-9)
        
        m['ticker'] = ticker
        all_results.append(m[m['Date'] >= USER_START_DATE])

    # 4. DB 적재
    if all_results:
        final_df = pd.concat(all_results).replace({np.nan: None})
        conn = _connect()
        try:
            cur = conn.cursor()
            sql = """
                INSERT INTO CONSTRUCTION_TB (trade_date, ticker, interest_beta, fx_correlation, bsi_momentum, mfg_lag3, z_score)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    interest_beta=VALUES(interest_beta),
                    fx_correlation=VALUES(fx_correlation),
                    bsi_momentum=VALUES(bsi_momentum),
                    mfg_lag3=VALUES(mfg_lag3),
                    z_score=VALUES(z_score);
            """
            data = [
                (row['Date'], row['ticker'], row['interest_beta'], row['fx_correlation'], 
                 row['bsi_momentum'], row['mfg_lag3'], row['z_score']) 
                for _, row in final_df.iterrows()
            ]
            cur.executemany(sql, data)
            conn.commit()
            print(f"✅ CONSTRUCTION_TB 업데이트 완료: {len(final_df)}건")
        except Exception as e:
            print(f"❌ CONS 섹터 적재 에러: {e}")
            conn.rollback()
        finally:
            conn.close()

# --- [ENG] 에너지/화학 섹터 (Energy & Chemicals) ---
def process_energy_chemical():
    """
    에너지/화학 섹터 지표 계산 및 ENER_CHEM_TB 적재
    지표: 스프레드 모멘텀(에틸렌-나프타), 제조업 시차(mfg_lag3, lag6), 
          오일 베타(XLE), 산업 Z-score(Ench_ETF)
    """
    print("🚀 [ENG] 에너지/화학 섹터 처리 시작...")
    
    # 1. DB에서 종목 리스트 조회 (sector_code: 'ENG')
    stocks = get_tickers_by_sector('ENG')
    if not stocks:
        print("⚠️ ENG 섹터에 해당하는 활성 종목이 DB에 없습니다.")
        return

    # 2. 외부 데이터 수집 (ECOS, Yahoo Finance, ETF)
    ecos = EcosClient()
    ecos_start = pd.to_datetime(FETCH_START_DATE).strftime("%Y%m")
    ecos_end = datetime.now().strftime("%Y%m")

    # ECOS: 에틸렌(404Y016-30511101AA), 나프타(404Y016-30412101AA), 제조업생산(901Y032-I11AC)
    print("📡 ECOS 화학 스프레드 및 제조업 지수 수집 중...")
    eth_df = ecos.fetch_data('404Y016', ecos_start, ecos_end, '30511101AA')
    nap_df = ecos.fetch_data('404Y016', ecos_start, ecos_end, '30412101AA')
    mfg_df = ecos.fetch_data('901Y032', ecos_start, ecos_end, 'I11AC')

    macro_df = pd.DataFrame(columns=['Date'])
    # 스프레드 모멘텀 계산
    if not eth_df.empty and not nap_df.empty:
        spread = pd.merge(eth_df.rename(columns={'Value':'E'}), 
                          nap_df.rename(columns={'Value':'N'}), on='Date', how='inner')
        spread['spread_momentum'] = (spread['E'] - spread['N']).pct_change(1)
        macro_df = spread[['Date', 'spread_momentum']]

    if not mfg_df.empty:
        mfg_df['mfg_idx'] = mfg_df['Value']
        if macro_df.empty: macro_df = mfg_df[['Date', 'mfg_idx']]
        else: macro_df = pd.merge(macro_df, mfg_df[['Date', 'mfg_idx']], on='Date', how='outer')

    # 글로벌 에너지 ETF (XLE) 및 국내 섹터 ETF (KODEX 에너지화학: 117460)
    print("📡 글로벌 에너지(XLE) 및 국내 섹터 ETF 데이터 수집 중...")
    xle = safe_fetch_yf('XLE', FETCH_START_DATE, END_DATE, 'XLE_Close')
    kodex_ench = safe_fetch_fdr('117460', FETCH_START_DATE, END_DATE, 'ETF_Close')

    all_results = []

    # 3. 종목별 계산 루프
    for s in stocks:
        ticker, name = s['ticker'], s['stock_name']
        print(f"📡 {name}({ticker}) 지표 산출 중...")
        
        df = safe_fetch_fdr(ticker, FETCH_START_DATE, END_DATE, 'Close')
        if df.empty: continue
        
        # 병합
        m = pd.merge(df, kodex_ench, on='Date', how='left')
        
        # Asof 병합 (XLE, 매크로)
        m = m.sort_values('Date')
        if not xle.empty:
            m = pd.merge_asof(m, xle.sort_values('Date'), on='Date', direction='backward', tolerance=pd.Timedelta('2D'))
        if not macro_df.empty:
            m = pd.merge_asof(m, macro_df.sort_values('Date'), on='Date', direction='backward')

        # 결측치 보정
        fill_cols = ['ETF_Close', 'XLE_Close', 'spread_momentum', 'mfg_idx']
        m[fill_cols] = m[fill_cols].ffill().bfill()

        # [계산 로직]
        # (1) 오일 베타 (60일) - 글로벌 에너지 가격 동조화
        s_ret = m['Close'].pct_change()
        x_ret = m['XLE_Close'].pct_change()
        m['oil_beta'] = (s_ret.rolling(60, min_periods=40).cov(x_ret) / 
                         (x_ret.rolling(60, min_periods=40).var() + 1e-10)).clip(-5, 5)
        
        # (2) 제조업 지수 시차 (3개월, 6개월)
        m['mfg_lag3'] = m['mfg_idx'].shift(60)
        m['mfg_lag6'] = m['mfg_idx'].shift(120)
        
        # (3) Z-score (산업 상대 강도)
        rel_price = m['Close'] / (m['ETF_Close'] + 1e-9)
        m['z_score'] = (rel_price - rel_price.rolling(120).mean()) / (rel_price.rolling(120).std() + 1e-9)
        
        m['ticker'] = ticker
        all_results.append(m[m['Date'] >= USER_START_DATE])

    # 4. DB 적재
    if all_results:
        final_df = pd.concat(all_results).replace({np.nan: None})
        conn = _connect()
        try:
            cur = conn.cursor()
            sql = """
                INSERT INTO ENER_CHEM_TB (trade_date, ticker, spread_momentum, mfg_lag3, mfg_lag6, oil_beta, z_score)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    spread_momentum=VALUES(spread_momentum), mfg_lag3=VALUES(mfg_lag3), 
                    mfg_lag6=VALUES(mfg_lag6), oil_beta=VALUES(oil_beta), z_score=VALUES(z_score);
            """
            data = [
                (row['Date'], row['ticker'], row['spread_momentum'], row['mfg_lag3'], 
                 row['mfg_lag6'], row['oil_beta'], row['z_score']) 
                for _, row in final_df.iterrows()
            ]
            cur.executemany(sql, data)
            conn.commit()
            print(f"✅ ENER_CHEM_TB 업데이트 완료: {len(final_df)}건")
        except Exception as e:
            print(f"❌ ENG 섹터 적재 에러: {e}")
            conn.rollback()
        finally:
            conn.close()

# --- [FIN] 금융 섹터 (Finance) ---
def process_finance():
    """
    금융 섹터 지표 계산 및 FINANCE_TB 적재
    지표: 금리 민감도(interest_beta), VIX 상관성(vix_corr), 
          글로벌 금융 동조화(global_fin_beta), 산업 Z-score(z_score)
    """
    print("🚀 [FIN] 금융 섹터 처리 시작...")
    
    # 1. DB에서 종목 리스트 조회 (sector_code: 'FIN')
    stocks = get_tickers_by_sector('FIN')
    if not stocks:
        print("⚠️ FIN 섹터에 해당하는 활성 종목이 DB에 없습니다.")
        return

    # 2. 외부 공통 지표 수집 (금리, VIX, XLF, 산업 ETF)
    # TIGER 200 금융(139270)
    print("📡 금리, VIX, 글로벌 금융(XLF) 데이터 수집 중...")
    kr10y = safe_fetch_fdr('INVESTING:KR10YT=RR', FETCH_START_DATE, END_DATE, 'KR10Y')
    xlf = safe_fetch_yf('XLF', FETCH_START_DATE, END_DATE, 'XLF_Close')
    vix = safe_fetch_yf('^VIX', FETCH_START_DATE, END_DATE, 'VIX_Close')
    tiger_fin = safe_fetch_fdr('139270', FETCH_START_DATE, END_DATE, 'ETF_Close')
    
    if kr10y.empty or vix.empty or xlf.empty or tiger_fin.empty:
        print("❌ 외부 지표 수집 실패로 FIN 섹터 계산을 건너뜁니다.")
        return

    all_results = []

    # 3. 종목별 계산 루프
    for s in stocks:
        ticker, name = s['ticker'], s['stock_name']
        print(f"📡 {name}({ticker}) 지표 산출 중...")
        
        df = safe_fetch_fdr(ticker, FETCH_START_DATE, END_DATE, 'Close')
        if df.empty: continue
        
        # 외부 지표 병합
        m = pd.merge(df, tiger_fin, on='Date', how='left')
        m = pd.merge(m, kr10y, on='Date', how='left')
        m = pd.merge(m, vix, on='Date', how='left')
        m = pd.merge(m, xlf, on='Date', how='left')
        
        # 결측치 보정 (금융 데이터는 연속성이 중요하므로 ffill)
        m = m.sort_values('Date').ffill().bfill()
        
        # [계산 로직]
        s_ret = m['Close'].pct_change()
        
        # (1) 개선된 금리 민감도 (Interest Sensitivity)
        # 금리 1%p 변동 시 주가 수익률 변동 측정 (안정화 로직 적용)
        k_diff = m['KR10Y'].diff()
        rolling_cov = s_ret.rolling(60).cov(k_diff)
        rolling_var = k_diff.rolling(60).var()
        m['interest_beta'] = (rolling_cov / (rolling_var + 1e-10)).clip(-10, 10)
        
        # (2) 시장 공포 민감도 (VIX Correlation)
        v_ret = m['VIX_Close'].pct_change()
        m['vix_corr'] = s_ret.rolling(60).corr(v_ret).fillna(0)
        
        # (3) 글로벌 금융 동조화 (XLF Beta)
        x_ret = m['XLF_Close'].shift(1).pct_change()
        m['global_fin_beta'] = (s_ret.rolling(60).cov(x_ret) / (x_ret.rolling(60).var() + 1e-10)).clip(-5, 5)
        
        # (4) 산업 내 상대 강도 Z-score (120일)
        rel_price = m['Close'] / (m['ETF_Close'] + 1e-10)
        m['z_score'] = (rel_price - rel_price.rolling(120).mean()) / (rel_price.rolling(120).std() + 1e-10)
        
        m['ticker'] = ticker
        all_results.append(m[m['Date'] >= USER_START_DATE])

    # 4. DB 적재
    if all_results:
        final_df = pd.concat(all_results).replace({np.nan: None})
        conn = _connect()
        try:
            cur = conn.cursor()
            sql = """
                INSERT INTO FINANCE_TB (trade_date, ticker, interest_beta, vix_corr, global_fin_beta, z_score)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    interest_beta=VALUES(interest_beta),
                    vix_corr=VALUES(vix_corr),
                    global_fin_beta=VALUES(global_fin_beta),
                    z_score=VALUES(z_score);
            """
            data = [
                (row['Date'], row['ticker'], row['interest_beta'], row['vix_corr'], 
                 row['global_fin_beta'], row['z_score']) 
                for _, row in final_df.iterrows()
            ]
            cur.executemany(sql, data)
            conn.commit()
            print(f"✅ FINANCE_TB 업데이트 완료: {len(final_df)}건")
        except Exception as e:
            print(f"❌ FIN 섹터 적재 에러: {e}")
            conn.rollback()
        finally:
            conn.close()

# --- [HC] 헬스케어 섹터 (Healthcare) ---
def process_healthcare():
    """
    헬스케어 섹터 지표 계산 및 HEALTHCARE_TB 적재
    지표: R&D 비율(rnd_ratio), PBR Z-score, PBR 과열 여부, 변동성 비율(vol_ratio), 고변동성 여부, 산업 Z-score
    """
    print("🚀 [HC] 헬스케어 섹터 처리 시작...")
    
    # 1. DB에서 종목 리스트 조회 (sector_code: 'HC')
    stocks = get_tickers_by_sector('HC')
    if not stocks:
        print("⚠️ HC 섹터에 해당하는 활성 종목이 DB에 없습니다.")
        return
    
    ticker_list = [s['ticker'] for s in stocks]

    # 2. 외부 공통 지표 수집 (코스피 200, 헬스케어 ETF)
    # TIGER 200 헬스케어(227540)
    print("📡 시장 지수 및 헬스케어 ETF 데이터 수집 중...")
    kospi200 = safe_fetch_fdr('KS200', FETCH_START_DATE, END_DATE, 'KOSPI200_Close')
    tiger_hc = safe_fetch_fdr('227540', FETCH_START_DATE, END_DATE, 'ETF_Close')
    
    # 3. DB에서 재무 및 R&D 데이터 수집 (FUNDAMENTAL_TB, RND_TB)
    print("📡 DB에서 재무(PBR) 및 R&D 투자 데이터 수집 중...")
    conn = _connect()
    try:
        # PBR 및 매출 데이터
        funda_sql = f"""
            SELECT ticker, end_date as Date, pbr, revenue 
            FROM FUNDAMENTAL_TB 
            WHERE ticker IN ({str(ticker_list)[1:-1]})
        """
        df_funda = pd.read_sql(funda_sql, conn)
        df_funda['Date'] = pd.to_datetime(df_funda['Date']).dt.normalize()

        # 쿼리에서 year와 quarter만 가져옴
        rnd_sql = f"""
            SELECT ticker, year, quarter, rnd_expense 
            FROM RND_TB 
            WHERE ticker IN ({str(ticker_list)[1:-1]})
        """
        df_rnd_raw = pd.read_sql(rnd_sql, conn)
        
        # [핵심] year와 quarter를 바탕으로 분기 말 날짜 생성 (Merge를 위함)
        quarter_map = {'Q1': '-03-31', 'Q2': '-06-30', 'Q3': '-09-30', 'Q4': '-12-31'}
        df_rnd_raw['Date'] = pd.to_datetime(
            df_rnd_raw['year'].astype(str) + df_rnd_raw['quarter'].map(quarter_map)
        )
        df_rnd = df_rnd_raw[['ticker', 'Date', 'rnd_expense']]
    finally:
        conn.close()

    # 재무 + R&D 통합
    df_biotech = pd.merge(df_funda, df_rnd, on=['ticker', 'Date'], how='outer')
    df_biotech['rnd_ratio'] = (df_biotech['rnd_expense'] / (df_biotech['revenue'] + 1e-9)) * 100

    all_results = []

    # 4. 종목별 계산 루프
    for s in stocks:
        ticker, name = s['ticker'], s['stock_name']
        print(f"📡 {name}({ticker}) 지표 산출 중...")
        df = safe_fetch_fdr(ticker, FETCH_START_DATE, END_DATE, 'Close')
        if df.empty: continue
        
        m = pd.merge(df, tiger_hc, on='Date', how='left')
        m = pd.merge(m, kospi200, on='Date', how='left')
        m = m.sort_values('Date')
        
        # [핵심] 병합 대상 데이터가 비어있어도 컬럼은 생성해줘야 계산 에러가 안 남
        stock_data = df_biotech[df_biotech['ticker'] == ticker].sort_values('Date')
        if not stock_data.empty:
            m = pd.merge_asof(m, stock_data.drop(columns=['ticker']), on='Date', direction='backward')
        
        # 중요: 계산에 쓰이는 컬럼이 병합 실패로 누락되었다면 NaN으로 생성
        for col in ['pbr', 'rnd_ratio', 'revenue']:
            if col not in m.columns: m[col] = np.nan

        # [지표 계산] 0 채우기 제거
        m['pbr_zscore'] = (m['pbr'] - m['pbr'].rolling(120).mean()) / (m['pbr'].rolling(120).std() + 1e-9)
        m['is_pbr_overheated'] = (m['pbr_zscore'] > 2.0).astype(float) # NaN은 0.0이 됨
        
        # 변동성 비율
        s_ret, k_ret = m['Close'].pct_change(), m['KOSPI200_Close'].pct_change()
        m['vol_ratio'] = s_ret.rolling(20).std() / (k_ret.rolling(20).std() + 1e-10)
        m['is_high_vol_stock'] = (m['vol_ratio'] > 1.5).astype(float)
        
        rel_price = m['Close'] / (m['ETF_Close'] + 1e-10)
        m['z_score'] = (rel_price - rel_price.rolling(120).mean()) / (rel_price.rolling(120).std() + 1e-10)
        
        m['ticker'] = ticker
        all_results.append(m[m['Date'] >= USER_START_DATE])

    # 5. DB 적재
    if all_results:
        final_df = pd.concat(all_results).replace({np.nan: None})
        conn = _connect()
        try:
            cur = conn.cursor()
            sql = """
                INSERT INTO HEALTHCARE_TB (
                    trade_date, ticker, rnd_ratio, pbr_zscore, 
                    is_pbr_overheated, vol_ratio, is_high_vol_stock, z_score
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    rnd_ratio=VALUES(rnd_ratio), pbr_zscore=VALUES(pbr_zscore),
                    is_pbr_overheated=VALUES(is_pbr_overheated), vol_ratio=VALUES(vol_ratio),
                    is_high_vol_stock=VALUES(is_high_vol_stock), z_score=VALUES(z_score);
            """
            data = [
                (row['Date'], row['ticker'], row['rnd_ratio'], row['pbr_zscore'], 
                 row['is_pbr_overheated'], row['vol_ratio'], row['is_high_vol_stock'], row['z_score']) 
                for _, row in final_df.iterrows()
            ]
            cur.executemany(sql, data)
            conn.commit()
            print(f"✅ HEALTHCARE_TB 업데이트 완료: {len(final_df)}건")
        except Exception as e:
            print(f"❌ HC 섹터 적재 에러: {e}")
            conn.rollback()
        finally:
            conn.close()

# --- [HI] 중공업 섹터 (Heavy Industry) ---
def process_heavy_industry():
    """
    중공업 섹터 지표 계산 및 HEAVY_IND_TB 적재
    지표: 환율 베타(fx_beta), 제조업 모멘텀(mfg_momentum), 제조업 시차(mfg_lag3),
          에너지 모멘텀(energy_momentum), 산업 Z-score(z_score)
    """
    print("🚀 [HI] 중공업 섹터 처리 시작...")
    
    # 1. DB에서 종목 리스트 조회 (sector_code: 'HI')
    stocks = get_tickers_by_sector('HI')
    if not stocks:
        print("⚠️ HI 섹터에 해당하는 활성 종목이 DB에 없습니다.")
        return

    # 2. 외부 공통 지표 수집 (ECOS, Yahoo Finance, ETF)
    ecos = EcosClient()
    ecos_start = pd.to_datetime(FETCH_START_DATE).strftime("%Y%m")
    ecos_end = datetime.now().strftime("%Y%m")

    # ECOS: 제조업 생산지수(901Y032-I11AC)
    print("📡 ECOS 제조업 생산지수 수집 중...")
    mfg_raw = ecos.fetch_data('901Y032', ecos_start, ecos_end, 'I11AC')
    
    macro_df = pd.DataFrame(columns=['Date'])
    if not mfg_raw.empty:
        mfg_raw['mfg_idx'] = mfg_raw['Value']
        macro_df = mfg_raw[['Date', 'mfg_idx']]

    # 환율, WTI 유가, 섹터 ETF (KODEX 기계장비: 102960)
    print("📡 환율, 유가 및 중공업(기계) ETF 데이터 수집 중...")
    usd_krw = safe_fetch_yf('USDKRW=X', FETCH_START_DATE, END_DATE, 'USD_KRW')
    wti = safe_fetch_yf('CL=F', FETCH_START_DATE, END_DATE, 'WTI_Close')
    mach_etf = safe_fetch_fdr('102960', FETCH_START_DATE, END_DATE, 'ETF_Close')

    all_results = []

    # 3. 종목별 계산 루프
    for s in stocks:
        ticker, name = s['ticker'], s['stock_name']
        print(f"📡 {name}({ticker}) 지표 산출 중...")
        
        df = safe_fetch_fdr(ticker, FETCH_START_DATE, END_DATE, 'Close')
        if df.empty: continue
        
        # 기본 병합
        m = pd.merge(df, mach_etf, on='Date', how='left')
        
        # Asof 병합 (환율, 유가, 제조업 지수)
        m = m.sort_values('Date')
        for extra_df in [usd_krw, wti, macro_df]:
            if not extra_df.empty:
                extra_df['Date'] = pd.to_datetime(extra_df['Date'])
                m = pd.merge_asof(m, extra_df.sort_values('Date'), on='Date', 
                                  direction='backward', tolerance=pd.Timedelta('2D'))

        # 결측치 보정 (ffill/bfill로 공휴일 등 메움)
        fill_cols = ['USD_KRW', 'WTI_Close', 'ETF_Close', 'mfg_idx']
        m[fill_cols] = m[fill_cols].ffill().bfill()

        # [계산 로직]
        # (1) 환율 민감도 (FX Beta) - 20일 수익률 기준 60일 윈도우
        # 환율 상승(원화 약세) 시 중공업 주의 수출 가격 경쟁력 반영
        u_ret_20 = m['USD_KRW'].pct_change(20)
        s_ret_20 = m['Close'].pct_change(20)
        m['fx_beta'] = (s_ret_20.rolling(60).cov(u_ret_20) / 
                        (u_ret_20.rolling(60).var() + 1e-10)).clip(-5, 5)
        
        # (2) 제조업 모멘텀 및 시차 (3개월)
        m['mfg_momentum'] = m['mfg_idx'].pct_change(60)
        m['mfg_lag3'] = m['mfg_idx'].shift(60)
        
        # (3) 에너지 발주 모멘텀 (WTI 60일 이동평균의 20일 변화율)
        wti_ma = m['WTI_Close'].rolling(60, min_periods=20).mean()
        m['energy_momentum'] = wti_ma.pct_change(20)
        
        # (4) Z-score (산업 상대 강도)
        rel_price = m['Close'] / (m['ETF_Close'] + 1e-9)
        m['z_score'] = (rel_price - rel_price.rolling(120).mean()) / (rel_price.rolling(120).std() + 1e-9)
        
        m['ticker'] = ticker
        all_results.append(m[m['Date'] >= USER_START_DATE])

    # 4. DB 적재
    if all_results:
        final_df = pd.concat(all_results).replace({np.nan: None})
        conn = _connect()
        try:
            cur = conn.cursor()
            sql = """
                INSERT INTO HEAVY_IND_TB (trade_date, ticker, fx_beta, mfg_momentum, mfg_lag3, energy_momentum, z_score)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    fx_beta=VALUES(fx_beta), mfg_momentum=VALUES(mfg_momentum),
                    mfg_lag3=VALUES(mfg_lag3), energy_momentum=VALUES(energy_momentum),
                    z_score=VALUES(z_score);
            """
            data = [
                (row['Date'], row['ticker'], row['fx_beta'], row['mfg_momentum'], 
                 row['mfg_lag3'], row['energy_momentum'], row['z_score']) 
                for _, row in final_df.iterrows()
            ]
            cur.executemany(sql, data)
            conn.commit()
            print(f"✅ HEAVY_IND_TB 업데이트 완료: {len(final_df)}건")
        except Exception as e:
            print(f"❌ HI 섹터 적재 에러: {e}")
            conn.rollback()
        finally:
            conn.close()

# --- [IND] 산업재 섹터 (Industrials) ---
def process_industrials():
    """
    산업재 섹터 지표 계산 및 INDUSTRIALS_TB 적재
    지표: 변동성 비율(vol_ratio), 물류 모멘텀(logistics_momentum), 
          물동량 시차(ship_vol_lag3), 제조업 시차(mfg_lag3, lag6), 산업 Z-score
    """
    print("🚀 [IND] 산업재 섹터 처리 시작...")
    
    # 1. DB에서 종목 리스트 조회 (sector_code: 'IND')
    stocks = get_tickers_by_sector('IND')
    if not stocks:
        print("⚠️ IND 섹터에 해당하는 활성 종목이 DB에 없습니다.")
        return

    # 2. 외부 공통 지표 수집 (ECOS, ETF, 지수)
    ecos = EcosClient()
    ecos_start = pd.to_datetime(FETCH_START_DATE).strftime("%Y%m")
    ecos_end = datetime.now().strftime("%Y%m")

    # ECOS: 제조업생산(901Y032-I11AC), 운수창고BSI(512Y007-AA/H4900), 매출BSI(512Y007-AB/H4900)
    print("📡 ECOS 제조업 및 물류 BSI 지수 수집 중...")
    mfg_raw = ecos.fetch_data('901Y032', ecos_start, ecos_end, 'I11AC')
    sea_bsi_raw = ecos.fetch_data('512Y007', ecos_start, ecos_end, 'AA', 'H4900')
    ship_vol_raw = ecos.fetch_data('512Y007', ecos_start, ecos_end, 'AB', 'H4900')
    
    macro_df = pd.DataFrame(columns=['Date'])
    if not mfg_raw.empty:
        mfg_raw['mfg_idx'] = mfg_raw['Value']
        macro_df = mfg_raw[['Date', 'mfg_idx']]
    
    if not sea_bsi_raw.empty:
        sea_bsi_raw['sea_bsi'] = sea_bsi_raw['Value']
        if macro_df.empty: macro_df = sea_bsi_raw[['Date', 'sea_bsi']]
        else: macro_df = pd.merge(macro_df, sea_bsi_raw[['Date', 'sea_bsi']], on='Date', how='outer')
        
    if not ship_vol_raw.empty:
        ship_vol_raw['ship_vol_idx'] = ship_vol_raw['Value']
        if macro_df.empty: macro_df = ship_vol_raw[['Date', 'ship_vol_idx']]
        else: macro_df = pd.merge(macro_df, ship_vol_raw[['Date', 'ship_vol_idx']], on='Date', how='outer')

    # 시장 지수 및 섹터 ETF (TIGER 200 산업재: 227550)
    print("📡 KOSPI 200 및 산업재 ETF 데이터 수집 중...")
    kospi200 = safe_fetch_fdr('KS200', FETCH_START_DATE, END_DATE, 'KOSPI200_Close')
    tiger_ig = safe_fetch_fdr('227550', FETCH_START_DATE, END_DATE, 'ETF_Close')

    all_results = []

    # 3. 종목별 계산 루프
    for s in stocks:
        ticker, name = s['ticker'], s['stock_name']
        print(f"📡 {name}({ticker}) 지표 산출 중...")
        
        df = safe_fetch_fdr(ticker, FETCH_START_DATE, END_DATE, 'Close')
        if df.empty: continue
        
        # 기본 병합
        m = pd.merge(df, tiger_ig, on='Date', how='left')
        m = pd.merge(m, kospi200, on='Date', how='left')
        
        # Asof 병합 (매크로 지표)
        m = m.sort_values('Date')
        if not macro_df.empty:
            m = pd.merge_asof(m, macro_df.sort_values('Date'), on='Date', direction='backward')

        # 결측치 보정
        fill_cols = ['ETF_Close', 'KOSPI200_Close', 'mfg_idx', 'sea_bsi', 'ship_vol_idx']
        m[fill_cols] = m[fill_cols].ffill().bfill()

        # [계산 로직]
        s_ret = m['Close'].pct_change()
        
        # (1) 상대적 변동성 비율 (Vol Ratio) - 20일 기준
        k_ret = m['KOSPI200_Close'].pct_change()
        v_stock = s_ret.rolling(20, min_periods=15).std()
        v_market = k_ret.rolling(20, min_periods=15).std()
        m['vol_ratio'] = v_stock / (v_market + 1e-10)
        
        # (2) 물류 수요 모멘텀 (3개월 시계열 기준)
        m['logistics_momentum'] = m['sea_bsi'].pct_change(60)
        
        # (3) 원자재 교역 물동량 Lag (3개월 시차)
        m['ship_vol_lag3'] = m['ship_vol_idx'].shift(60)

        # (4) 제조업 지수 시차 (3개월, 6개월)
        m['mfg_lag3'] = m['mfg_idx'].shift(60)
        m['mfg_lag6'] = m['mfg_idx'].shift(120)
        
        # (5) 산업 내 상대 강도 Z-score (120일)
        rel_price = m['Close'] / (m['ETF_Close'] + 1e-9)
        m['z_score'] = (rel_price - rel_price.rolling(120, min_periods=30).mean()) / \
                       (rel_price.rolling(120, min_periods=30).std() + 1e-9)
        
        m['ticker'] = ticker
        all_results.append(m[m['Date'] >= USER_START_DATE])

    # 4. DB 적재
    if all_results:
        final_df = pd.concat(all_results).replace({np.nan: None})
        conn = _connect()
        try:
            cur = conn.cursor()
            sql = """
                INSERT INTO INDUSTRIALS_TB (
                    trade_date, ticker, vol_ratio, logistics_momentum, 
                    ship_vol_lag3, mfg_lag3, mfg_lag6, z_score
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    vol_ratio=VALUES(vol_ratio), logistics_momentum=VALUES(logistics_momentum),
                    ship_vol_lag3=VALUES(ship_vol_lag3), mfg_lag3=VALUES(mfg_lag3),
                    mfg_lag6=VALUES(mfg_lag6), z_score=VALUES(z_score);
            """
            data = [
                (row['Date'], row['ticker'], row['vol_ratio'], row['logistics_momentum'], 
                 row['ship_vol_lag3'], row['mfg_lag3'], row['mfg_lag6'], row['z_score']) 
                for _, row in final_df.iterrows()
            ]
            cur.executemany(sql, data)
            conn.commit()
            print(f"✅ INDUSTRIALS_TB 업데이트 완료: {len(final_df)}건")
        except Exception as e:
            print(f"❌ IND 섹터 적재 에러: {e}")
            conn.rollback()
        finally:
            conn.close()

# --- [IT] 정보기술 섹터 (Information Technology) ---
def process_it():
    """
    정보기술 섹터 지표 계산 및 IT_TB 적재
    지표: 반도체 동조성(soxx_corr), 애플 모멘텀(apple_momentum), 
          제조업 경기 모멘텀(mfg_cycle_momentum), 산업 Z-score(z_score)
    """
    print("🚀 [IT] 정보기술 섹터 처리 시작...")
    
    # 1. DB에서 종목 리스트 조회 (sector_code: 'IT')
    stocks = get_tickers_by_sector('IT')
    if not stocks:
        print("⚠️ IT 섹터에 해당하는 활성 종목이 DB에 없습니다.")
        return

    # 2. 글로벌 동적 지표 수집 (SOXX, AAPL, XLI, IT ETF)
    # TIGER 200 IT(139260)
    print("📡 글로벌 반도체(SOXX), 애플, 제조업(XLI) 및 IT ETF 데이터 수집 중...")
    soxx = safe_fetch_yf('SOXX', FETCH_START_DATE, END_DATE, 'SOXX_Close')
    aapl = safe_fetch_yf('AAPL', FETCH_START_DATE, END_DATE, 'AAPL_Close')
    xli = safe_fetch_yf('XLI', FETCH_START_DATE, END_DATE, 'XLI_Close')
    tiger_it = safe_fetch_fdr('139260', FETCH_START_DATE, END_DATE, 'ETF_Close')
    
    if soxx.empty or aapl.empty or xli.empty or tiger_it.empty:
        print("❌ 글로벌 지표 수집 실패로 IT 섹터 계산을 건너뜁니다.")
        return

    all_results = []

    # 3. 종목별 계산 루프
    for s in stocks:
        ticker, name = s['ticker'], s['stock_name']
        print(f"📡 {name}({ticker}) 지표 산출 중...")
        
        df = safe_fetch_fdr(ticker, FETCH_START_DATE, END_DATE, 'Close')
        if df.empty: continue
        
        # 데이터 병합
        m = pd.merge(df, tiger_it, on='Date', how='left')
        m = pd.merge(m, soxx, on='Date', how='left')
        m = pd.merge(m, aapl, on='Date', how='left')
        m = pd.merge(m, xli, on='Date', how='left')
        
        # 결측치 보정 (글로벌 지표는 시차 등으로 인해 ffill 필수)
        m = m.sort_values('Date').ffill().bfill()
        
        # [계산 로직]
        s_ret = m['Close'].pct_change()
        
        # (1) 반도체 동조성 (SOXX 상관계수)
        # 미국 반도체 지수의 전일(shift 1) 수익률과 종목 수익률의 60일 상관계수
        soxx_ret = m['SOXX_Close'].shift(1).pct_change()
        m['soxx_corr'] = s_ret.rolling(60).corr(soxx_ret)
        
        # (2) 글로벌 IT 수요 모멘텀 (애플 60일 변화율)
        m['apple_momentum'] = m['AAPL_Close'].pct_change(60)
        
        # (3) 글로벌 제조업 경기 선행 모멘텀 (XLI 60일 변화율)
        m['mfg_cycle_momentum'] = m['XLI_Close'].pct_change(60)
        
        # (4) 산업 내 상대 강도 Z-score (120일)
        rel_price = m['Close'] / (m['ETF_Close'] + 1e-10)
        m['z_score'] = (rel_price - rel_price.rolling(120).mean()) / (rel_price.rolling(120).std() + 1e-10)
        
        m['ticker'] = ticker
        all_results.append(m[m['Date'] >= USER_START_DATE])

    # 4. DB 적재
    if all_results:
        final_df = pd.concat(all_results).replace({np.nan: None})
        conn = _connect()
        try:
            cur = conn.cursor()
            sql = """
                INSERT INTO IT_TB (trade_date, ticker, soxx_corr, apple_momentum, mfg_cycle_momentum, z_score)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    soxx_corr=VALUES(soxx_corr), 
                    apple_momentum=VALUES(apple_momentum),
                    mfg_cycle_momentum=VALUES(mfg_cycle_momentum), 
                    z_score=VALUES(z_score);
            """
            data = [
                (row['Date'], row['ticker'], row['soxx_corr'], row['apple_momentum'], 
                 row['mfg_cycle_momentum'], row['z_score']) 
                for _, row in final_df.iterrows()
            ]
            cur.executemany(sql, data)
            conn.commit()
            print(f"✅ IT_TB 업데이트 완료: {len(final_df)}건")
        except Exception as e:
            print(f"❌ IT 섹터 적재 에러: {e}")
            conn.rollback()
        finally:
            conn.close()

# --- [MAT] 철강/소재 섹터 (Materials) ---
def process_materials():
    """
    철강/소재 섹터 지표 계산 및 MATERIALS_TB 적재
    지표: 중국 모멘텀(china_momentum), 제조업 시차(mfg_lag3), 선행지수 시차(cli_lag3),
          구리 베타(copper_beta), 오일 베타(oil_beta), 철강 베타(steel_beta), 산업 Z-score
    """
    print("🚀 [MAT] 철강/소재 섹터 처리 시작...")
    
    # 1. DB에서 종목 리스트 조회 (sector_code: 'MAT')
    stocks = get_tickers_by_sector('MAT')
    if not stocks:
        print("⚠️ MAT 섹터에 해당하는 활성 종목이 DB에 없습니다.")
        return

    # 2. 외부 공통 지표 수집 (ECOS, Yahoo Finance, ETF)
    ecos = EcosClient()
    ecos_start = pd.to_datetime(FETCH_START_DATE).strftime("%Y%m")
    ecos_end = datetime.now().strftime("%Y%m")

    # ECOS: 제조업생산(901Y032-I11AC), 선행종합지수(901Y067-I16A), 철강1차제품 PPI(404Y014-3071AA)
    print("📡 ECOS 제조업, 선행지수 및 철강 PPI 수집 중...")
    mfg_raw = ecos.fetch_data('901Y032', ecos_start, ecos_end, 'I11AC')
    cli_raw = ecos.fetch_data('901Y067', ecos_start, ecos_end, 'I16A')
    steel_ppi_raw = ecos.fetch_data('404Y014', ecos_start, ecos_end, '3071AA')
    
    macro_df = pd.DataFrame(columns=['Date'])
    if not mfg_raw.empty:
        mfg_raw['mfg_idx'] = mfg_raw['Value']
        macro_df = mfg_raw[['Date', 'mfg_idx']]
    
    if not cli_raw.empty:
        cli_raw['cli_idx'] = cli_raw['Value']
        if macro_df.empty: macro_df = cli_raw[['Date', 'cli_idx']]
        else: macro_df = pd.merge(macro_df, cli_raw[['Date', 'cli_idx']], on='Date', how='outer')

    if not steel_ppi_raw.empty:
        steel_ppi_raw['steel_ppi'] = steel_ppi_raw['Value']
        if macro_df.empty: macro_df = steel_ppi_raw[['Date', 'steel_ppi']]
        else: macro_df = pd.merge(macro_df, steel_ppi_raw[['Date', 'steel_ppi']], on='Date', how='outer')

    # 원자재 및 글로벌 지표 (구리, WTI, 중국 ETF-FXI, 철강 ETF-117680)
    print("📡 원자재(구리/WTI) 및 중국/철강 ETF 데이터 수집 중...")
    copper = safe_fetch_yf('HG=F', FETCH_START_DATE, END_DATE, 'Copper_Close')
    wti = safe_fetch_yf('CL=F', FETCH_START_DATE, END_DATE, 'WTI_Close')
    fxi = safe_fetch_yf('FXI', FETCH_START_DATE, END_DATE, 'FXI_Close')
    steel_etf = safe_fetch_fdr('117680', FETCH_START_DATE, END_DATE, 'ETF_Close')

    all_results = []

    # 3. 종목별 계산 루프
    for s in stocks:
        ticker, name = s['ticker'], s['stock_name']
        print(f"📡 {name}({ticker}) 지표 산출 중...")
        
        df = safe_fetch_fdr(ticker, FETCH_START_DATE, END_DATE, 'Close')
        if df.empty: continue
        
        # 기본 병합
        m = pd.merge(df, steel_etf, on='Date', how='left')
        
        # Asof 병합
        m = m.sort_values('Date')
        for extra_df in [copper, wti, fxi, macro_df]:
            if not extra_df.empty:
                extra_df['Date'] = pd.to_datetime(extra_df['Date'])
                m = pd.merge_asof(m, extra_df.sort_values('Date'), on='Date', 
                                  direction='backward', tolerance=pd.Timedelta('2D'))

        # 결측치 보정
        fill_cols = ['Copper_Close', 'WTI_Close', 'FXI_Close', 'ETF_Close', 'steel_ppi', 'mfg_idx', 'cli_idx']
        m[fill_cols] = m[fill_cols].ffill().bfill()

        # [계산 로직]
        s_ret = m['Close'].pct_change()
        
        # (1) 중국 경기 모멘텀 (20일 변화율)
        m['china_momentum'] = m['FXI_Close'].pct_change(20)
        
        # (2) 제조업 및 선행지수 시차 (3개월)
        m['mfg_lag3'] = m['mfg_idx'].shift(60)
        m['cli_lag3'] = m['cli_idx'].shift(60)
        
        # (3) 원자재 및 에너지 베타 (60일)
        c_ret = m['Copper_Close'].pct_change()
        w_ret = m['WTI_Close'].pct_change()
        m['copper_beta'] = (s_ret.rolling(60, min_periods=40).cov(c_ret) / (c_ret.rolling(60, min_periods=40).var() + 1e-10)).clip(-5, 5)
        m['oil_beta'] = (s_ret.rolling(60, min_periods=40).cov(w_ret) / (w_ret.rolling(60, min_periods=40).var() + 1e-10)).clip(-5, 5)
        
        # (4) 철강 베타 (PPI 기반 - 민감도 조정 로직 적용)
        if 'steel_ppi' in m.columns:
            p_ret = m['steel_ppi'].pct_change()
            m['steel_beta'] = (s_ret.rolling(60, min_periods=5).cov(p_ret) / (p_ret.rolling(60, min_periods=5).var() + 1e-10))
            m['steel_beta'] = m['steel_beta'].replace([np.inf, -np.inf], np.nan).ffill().fillna(0).clip(-5, 5)
        
        # (5) 산업 내 상대 강도 Z-score (120일)
        rel_price = m['Close'] / (m['ETF_Close'] + 1e-9)
        m['z_score'] = (rel_price - rel_price.rolling(120).mean()) / (rel_price.rolling(120).std() + 1e-9)
        
        m['ticker'] = ticker
        all_results.append(m[m['Date'] >= USER_START_DATE])

    # 4. DB 적재
    if all_results:
        final_df = pd.concat(all_results).replace({np.nan: None})
        conn = _connect()
        try:
            cur = conn.cursor()
            sql = """
                INSERT INTO MATERIALS_TB (
                    trade_date, ticker, china_momentum, mfg_lag3, cli_lag3, 
                    copper_beta, oil_beta, steel_beta, z_score
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    china_momentum=VALUES(china_momentum), mfg_lag3=VALUES(mfg_lag3),
                    cli_lag3=VALUES(cli_lag3), copper_beta=VALUES(copper_beta),
                    oil_beta=VALUES(oil_beta), steel_beta=VALUES(steel_beta),
                    z_score=VALUES(z_score);
            """
            data = [
                (row['Date'], row['ticker'], row['china_momentum'], row['mfg_lag3'], 
                 row['cli_lag3'], row['copper_beta'], row['oil_beta'], 
                 row['steel_beta'], row['z_score']) 
                for _, row in final_df.iterrows()
            ]
            cur.executemany(sql, data)
            conn.commit()
            print(f"✅ MATERIALS_TB 업데이트 완료: {len(final_df)}건")
        except Exception as e:
            print(f"❌ MAT 섹터 적재 에러: {e}")
            conn.rollback()
        finally:
            conn.close()

# ============================================================
# 3. 메인 실행부 (Main Pipeline)
# ============================================================

def run_sector_indicator_calculator():
    """모든 섹터의 파생 지표를 순차적으로 계산하고 DB에 적재합니다."""
    start_time = datetime.now()
    print(f"🏁 [Step 3] 섹터별 통합 지표 계산 시작: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)

    # 실행할 섹터 함수 리스트
    sector_functions = [
        process_communication_service, # COMM
        process_consumer_discretionary, # CD
        process_consumer_staples,       # CS
        process_construction,           # CONS
        process_energy_chemical,        # ENG
        process_finance,                # FIN
        process_healthcare,             # HC
        process_heavy_industry,         # HI
        process_industrials,            # IND
        process_it,                     # IT
        process_materials               # MAT
    ]

    for func in sector_functions:
        try:
            func()
            print("-" * 30)
        except Exception as e:
            print(f"❌ {func.__name__} 실행 중 치명적 오류 발생: {e}")
            continue

    end_time = datetime.now()
    duration = end_time - start_time
    print("=" * 50)
    print(f"✨ 모든 섹터 업데이트 완료! (소요 시간: {duration})")
    print(f"📅 종료 시각: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")

if __name__ == "__main__":
    # .env 파일 로드 확인
    if not os.getenv("ECOS_API_KEY"):
        print("❌ ECOS_API_KEY가 설정되지 않았습니다. .env 파일을 확인해주세요.")
    else:
        run_sector_indicator_calculator()