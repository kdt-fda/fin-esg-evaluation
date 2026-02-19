import os
import FinanceDataReader as fdr
import yfinance as yf
import pandas as pd
import numpy as np
import requests
from dotenv import load_dotenv

# ============================================================
# [SECTION 1] 설정 및 기간 확장 (기존 유지)
# ============================================================
load_dotenv()
USER_START_DATE = '2023-01-01'
END_DATE = '2025-12-31'
FETCH_START_DATE = '2021-01-01'
START_YM = '202101'

ING_STOCKS = {
    'LG에너지솔루션': '373220', '한화에어로스페이스': '012450', '한화시스템': '272210',
    '포스코퓨처엠': '003670', 'HMM': '011200', 'LS ELECTRIC': '010120',
    '현대글로비스': '086280', '한국항공우주': '047810', '포스코인터내셔널': '047050',
    'LIG넥스원': '079550', '대한항공': '003490', 'LS': '006260',
    '대한전선': '001440', '엘앤에프': '066970', '에코프로머티': '450080',
    '에스원': '012750', '팬오션': '028670', '한전KPS': '051600',
    'CJ대한통운': '000120', 'SK아이이테크놀로지': '361610'
}

# ============================================================
# [SECTION 2] Helper 함수 (기존 유지)
# ============================================================
class EcosClient:
    BASE_URL = "https://ecos.bok.or.kr/api"
    def __init__(self):
        self.api_key = os.getenv("ECOS_API_KEY")

    def fetch_data(self, stat_code, start, end, *item_codes, cycle="M", lang="kr"):
        item_path = "/".join(item_codes) if item_codes else ""
        url = f"{self.BASE_URL}/StatisticSearch/{self.api_key}/json/{lang}/1/500/{stat_code}/{cycle}/{start}/{end}"
        if item_path:
            url += f"/{item_path}"

        try:
            resp = requests.get(url).json()
            rows = resp.get("StatisticSearch", {}).get("row", [])
            if not rows:
                return pd.DataFrame({'Date': pd.to_datetime([]), 'Value': pd.Series(dtype='float64')})

            df = pd.DataFrame(rows)
            df['Date'] = pd.to_datetime(df['TIME'], format='%Y%m').dt.normalize()
            df['Value'] = pd.to_numeric(df['DATA_VALUE'])
            return df[['Date', 'Value']].sort_values('Date').drop_duplicates('Date')
        except Exception:
            return pd.DataFrame({'Date': pd.to_datetime([]), 'Value': pd.Series(dtype='float64')})

def safe_fetch_fdr(ticker, start, end, col_name='Close'):
    try:
        df = fdr.DataReader(ticker, start, end)
        if df is None or df.empty: return pd.DataFrame(columns=['Date', col_name])
        df = df.reset_index()
        df.columns = [c.capitalize() if c.lower() == 'date' else c for c in df.columns]
        df['Date'] = pd.to_datetime(df['Date']).dt.normalize()
        val_col = 'Close' if 'Close' in df.columns else df.columns[1]
        df = df[['Date', val_col]].rename(columns={val_col: col_name})
        return df.sort_values('Date').drop_duplicates('Date')
    except: return pd.DataFrame(columns=['Date', col_name])

# ============================================================
# [SECTION 3] 데이터 수집 및 통합 (BDI 대체 지표 추가)
# ============================================================
def fetch_industrials_data():
    ecos = EcosClient()
    
    # 1. 개별 종목 주가 수집
    stock_list = []
    for name, ticker in ING_STOCKS.items():
        print(f"📡 {name}({ticker}) 주가 데이터 수집 중...")
        df = safe_fetch_fdr(ticker, FETCH_START_DATE, END_DATE, 'Close')
        if not df.empty:
            df['Ticker'], df['Stock_Name'] = ticker, name
            stock_list.append(df)
    full_stocks = pd.concat(stock_list).reset_index(drop=True)

    # 2. ECOS 공식 지표 수집
    print("📡 ECOS 제조업 생산지수(I11AC) 수집 중...")
    mfg_df = ecos.fetch_data('901Y032', START_YM, '202512', 'I11AC')
    
    print("📡 ECOS 운수창고업 업황실적BSI(AA/H4900) 수집 중...") 
    sea_bsi_df = ecos.fetch_data('512Y007', START_YM, '202512', 'AA', 'H4900')

    # [추가] BDI 대체 지표: 운수창고업 매출 BSI (BDI와 상관관계가 높은 실제 물동량 지표)
    print("📡 BDI 대체지표(운수창고업 매출BSI - AB/H4900) 수집 중...")
    shipping_vol_df = ecos.fetch_data('512Y007', START_YM, '202512', 'AB', 'H4900')

    # 3. 시장 및 섹터 ETF 수집
    print("📡 KOSPI 200 및 산업재 ETF 데이터 수집 중...")
    kospi200 = safe_fetch_fdr('KS200', FETCH_START_DATE, END_DATE, 'KOSPI200_Close')
    tiger_ig = safe_fetch_fdr('227550', FETCH_START_DATE, END_DATE, 'TigerIG_Close')

    # --------------------------------------------------------
    # [핵심] 병합 전 Dtype 강제 일치 함수 (MergeError 해결)
    # --------------------------------------------------------
    def force_fix_type(df):
        df = df.copy()
        if 'Date' not in df.columns or df['Date'].empty:
            df['Date'] = pd.to_datetime(df['Date'])
        df['Date'] = pd.to_datetime(df['Date']).dt.tz_localize(None).dt.normalize().astype('datetime64[ns]')
        return df.sort_values('Date').reset_index(drop=True)

    full_stocks = force_fix_type(full_stocks)
    kospi200, tiger_ig = force_fix_type(kospi200), force_fix_type(tiger_ig)
    mfg_df, sea_bsi_df = force_fix_type(mfg_df), force_fix_type(sea_bsi_df)
    shipping_vol_df = force_fix_type(shipping_vol_df)

    # 4. 시계열 병합
    merged = pd.merge_asof(full_stocks, kospi200, on='Date', direction='backward')
    merged = pd.merge_asof(merged, tiger_ig, on='Date', direction='backward')
    
    if not mfg_df.empty:
        merged = pd.merge_asof(merged, mfg_df.rename(columns={'Value': 'mfg_idx'}), on='Date', direction='backward')
    if not sea_bsi_df.empty:
        merged = pd.merge_asof(merged, sea_bsi_df.rename(columns={'Value': 'sea_bsi'}), on='Date', direction='backward')
    if not shipping_vol_df.empty:
        merged = pd.merge_asof(merged, shipping_vol_df.rename(columns={'Value': 'ship_vol_idx'}), on='Date', direction='backward')

    # 5. 결측치 보정 (계산 전 ffill)
    fill_cols = ['KOSPI200_Close', 'TigerIG_Close', 'mfg_idx', 'sea_bsi', 'ship_vol_idx']
    fill_cols = [c for c in fill_cols if c in merged.columns]
    merged = merged.sort_values(['Stock_Name', 'Date'])
    if fill_cols:
        merged[fill_cols] = merged.groupby('Stock_Name')[fill_cols].ffill().bfill()
        
    return merged

# ============================================================
# [SECTION 4] 파생 지표 계산 (물동량 Lag 추가)
# ============================================================
def calculate_industrials_metrics(group):
    group = group.sort_values('Date')
    s_ret = group['Close'].pct_change()
    
    # 1. 상대적 변동성 비율 (Vol Ratio)
    if 'KOSPI200_Close' in group.columns:
        k_ret = group['KOSPI200_Close'].pct_change()
        v_stock = s_ret.rolling(20, min_periods=15).std()
        v_market = k_ret.rolling(20, min_periods=15).std()
        group['vol_ratio'] = v_stock / (v_market + 1e-10)
    
    # 2. [수정] 물류 수요 모멘텀 (실제 3개월 시계열 기준)
    if 'sea_bsi' in group.columns:
        # 행 기준 3이 아니라, 영업일 기준 60일(약 3개월) 전의 BSI와 비교
        group['logistics_momentum'] = group['sea_bsi'].pct_change(60)
    
    # 3. 원자재 교역 물동량 Lag (3개월 전 물동량이 현재 주가에 미치는 영향)
    if 'ship_vol_idx' in group.columns:
        # 이미 60일 shift로 잘 구현되어 있음
        group['ship_vol_lag3'] = group['ship_vol_idx'].shift(60)

    # 4. 제조업 지수 시차 (ECOS)
    if 'mfg_idx' in group.columns:
        # 60일(3개월), 120일(6개월) 전 지수를 현재 행에 매칭
        group['mfg_lag3'] = group['mfg_idx'].shift(60)
        group['mfg_lag6'] = group['mfg_idx'].shift(120)
        
    # 5. 산업 내 상대 강도 Z-score (120일)
    if 'TigerIG_Close' in group.columns:
        rel_price = group['Close'] / (group['TigerIG_Close'] + 1e-9)
        # 120일 이동평균과 표준편차를 활용한 표준화
        group['z_score'] = (rel_price - rel_price.rolling(120, min_periods=30).mean()) / \
                           (rel_price.rolling(120, min_periods=30).std() + 1e-9)
    
    return group

# ============================================================
# [SECTION 5] 실행 및 최종 저장
# ============================================================
if __name__ == "__main__":
    df_raw = fetch_industrials_data()
    
    if not df_raw.empty:
        print("🚀 산업재 섹터 파생 지표 산출 중...")
        df_processed = df_raw.groupby('Stock_Name', group_keys=False).apply(calculate_industrials_metrics, include_groups=False)
        
        df_processed['Stock_Name'] = df_raw.sort_values(['Stock_Name', 'Date'])['Stock_Name'].values
        df_processed['Ticker'] = df_raw.sort_values(['Stock_Name', 'Date'])['Ticker'].values

        df_processed = df_processed.sort_values(['Stock_Name', 'Date']).reset_index(drop=True)
        df_final = df_processed[df_processed['Date'] >= USER_START_DATE].copy()
        
        # [최종 컬럼 구성] ship_vol_lag3 추가
        final_cols = ['Date', 'Ticker', 'Stock_Name', 'Close', 'vol_ratio', 'logistics_momentum', 'ship_vol_lag3', 'mfg_lag3', 'mfg_lag6', 'z_score']
        actual_cols = [c for c in final_cols if c in df_final.columns]
        df_final = df_final[actual_cols]

        output_filename = 'industrials_processed.csv'
        df_final.to_csv(output_filename, index=False, encoding='utf-8-sig')
        print(f"✅ 산업재 섹터 전처리 완료: {output_filename}")
        print(df_final.head(10))