import os
import FinanceDataReader as fdr
import yfinance as yf
import pandas as pd
import numpy as np
import requests
from dotenv import load_dotenv

# ============================================================
# [SECTION 1] 설정 및 기간 확장
# ============================================================
load_dotenv()
USER_START_DATE = '2023-01-01'
END_DATE = '2025-12-31'
FETCH_START_DATE = '2021-01-01'
START_YM = '202101'

CONS_STOCKS = {
    '삼성물산': '028260', '현대건설': '000720', '삼성E&A': '028050',
    '한전기술': '052690', 'KCC': '002380', '대우건설': '047040',
    'DL이앤씨': '375500', 'GS건설': '006360', '한일시멘트': '300720', 'DL': '000210'
}

# ============================================================
# [SECTION 2] Helper 함수
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
        if df is None or df.empty:
            return pd.DataFrame({'Date': pd.to_datetime([]), col_name: pd.Series(dtype='float64')})
        df = df.reset_index()
        df.columns = [c.capitalize() if c.lower() == 'date' else c for c in df.columns]
        df['Date'] = pd.to_datetime(df['Date']).dt.normalize()
        val_col = 'Close' if 'Close' in df.columns else df.columns[1]
        df = df[['Date', val_col]].rename(columns={val_col: col_name})
        return df.sort_values('Date').drop_duplicates('Date')
    except:
        return pd.DataFrame({'Date': pd.to_datetime([]), col_name: pd.Series(dtype='float64')})

def safe_fetch_yf(ticker, start, end, col_name):
    try:
        data = yf.download(ticker, start=start, end=end, progress=False)
        if data.empty:
            return pd.DataFrame({'Date': pd.to_datetime([]), col_name: pd.Series(dtype='float64')})
        if isinstance(data.columns, pd.MultiIndex):
            df = data['Close'].iloc[:, 0].reset_index()
        else:
            df = data['Close'].reset_index()
        df.columns = ['Date', col_name]
        df['Date'] = pd.to_datetime(df['Date']).dt.tz_localize(None).dt.normalize()
        return df
    except:
        return pd.DataFrame({'Date': pd.to_datetime([]), col_name: pd.Series(dtype='float64')})

# ============================================================
# [SECTION 3] 데이터 수집 및 통합
# ============================================================
def fetch_construction_data():
    ecos = EcosClient()

    stock_list = []
    for name, ticker in CONS_STOCKS.items():
        print(f"📡 {name}({ticker}) 주가 데이터 수집 중...")
        df = safe_fetch_fdr(ticker, FETCH_START_DATE, END_DATE, 'Close')
        if not df.empty:
            df['Ticker'], df['Stock_Name'] = ticker, name
            stock_list.append(df)
    if not stock_list:
        return pd.DataFrame()
    full_stocks = pd.concat(stock_list).reset_index(drop=True)

    print("📡 ECOS 건설업 업황실적BSI(AA/F4100) 및 제조업 지수 수집 중...")
    bsi_df = ecos.fetch_data('512Y007', START_YM, '202512', 'AA', 'F4100')
    mfg_df = ecos.fetch_data('901Y032', START_YM, '202512', 'I11AC')

    print("📡 원/달러 환율 및 국채 금리 수집 중...")
    usd_krw = safe_fetch_yf('USDKRW=X', FETCH_START_DATE, END_DATE, 'USD_KRW')
    kr10yt = safe_fetch_fdr('INVESTING:KR10YT=RR', FETCH_START_DATE, END_DATE, 'KR10YT_Close')
    tiger_cons = safe_fetch_fdr('139220', FETCH_START_DATE, END_DATE, 'TigerCons_Close')

    def force_fix_type(df):
        df = df.copy()
        if 'Date' not in df.columns or df['Date'].empty:
            df['Date'] = pd.to_datetime(df['Date'])
        df['Date'] = pd.to_datetime(df['Date']).dt.tz_localize(None).dt.normalize()
        df['Date'] = df['Date'].astype('datetime64[ns]')
        return df.sort_values('Date').reset_index(drop=True)

    full_stocks = force_fix_type(full_stocks)
    usd_krw, kr10yt, tiger_cons = [force_fix_type(d) for d in [usd_krw, kr10yt, tiger_cons]]
    bsi_df, mfg_df = force_fix_type(bsi_df), force_fix_type(mfg_df)

    # ---- 핵심 수정(제안 1번): 포인트 변화(diff) + 표준화(z-score) ----
    # 월별 bsi_df에서 3개월 포인트 변화 계산
    if not bsi_df.empty:
        bsi_df['bsi_diff_3m'] = bsi_df['Value'].diff(3)

        # 12개월(=12행) 롤링으로 표준화 (min_periods는 6으로 완화)
        roll = bsi_df['bsi_diff_3m'].rolling(12, min_periods=6)
        bsi_df['bsi_diff_3m_z'] = (bsi_df['bsi_diff_3m'] - roll.mean()) / (roll.std() + 1e-9)

    merged = pd.merge_asof(full_stocks, usd_krw, on='Date', direction='backward', tolerance=pd.Timedelta('2D'))
    merged = pd.merge_asof(merged, kr10yt, on='Date', direction='backward', tolerance=pd.Timedelta('2D'))
    merged = pd.merge(merged, tiger_cons, on='Date', how='left')

    # cons_bsi 레벨 + bsi_diff_3m_z(표준화된 포인트 변화) 붙이기
    if not bsi_df.empty:
        merged = pd.merge_asof(
            merged.sort_values('Date'),
            bsi_df[['Date', 'Value', 'bsi_diff_3m_z']].rename(columns={'Value': 'cons_bsi', 'bsi_diff_3m_z': 'bsi_momentum'}),
            on='Date',
            direction='backward'
        )

    if not mfg_df.empty:
        merged = pd.merge_asof(
            merged.sort_values('Date'),
            mfg_df.rename(columns={'Value': 'mfg_idx'})[['Date', 'mfg_idx']],
            on='Date',
            direction='backward'
        )

    fill_cols = ['USD_KRW', 'KR10YT_Close', 'TigerCons_Close', 'cons_bsi', 'bsi_momentum', 'mfg_idx']
    fill_cols = [c for c in fill_cols if c in merged.columns]

    merged = merged.sort_values(['Stock_Name', 'Date'])
    if fill_cols:
        merged[fill_cols] = merged.groupby('Stock_Name')[fill_cols].ffill().bfill()

    return merged

# ============================================================
# [SECTION 4] 파생 지표 계산
# ============================================================
def calculate_cons_metrics(group):
    group = group.sort_values('Date')
    s_ret = group['Close'].pct_change()

    if 'KR10YT_Close' in group.columns:
        i_ret = group['KR10YT_Close'].pct_change()
        group['interest_beta'] = s_ret.rolling(60, min_periods=30).cov(i_ret) / (i_ret.rolling(60, min_periods=30).var() + 1e-10)

    if 'USD_KRW' in group.columns:
        u_ret = group['USD_KRW'].pct_change()
        group['fx_correlation'] = s_ret.rolling(60, min_periods=30).corr(u_ret)

    # bsi_momentum는 병합 단계에서 이미 월단위(diff->z-score)로 계산됨 (재계산 X)

    if 'mfg_idx' in group.columns:
        group['mfg_lag3'] = group['mfg_idx'].shift(60)

    if 'TigerCons_Close' in group.columns:
        rel_price = group['Close'] / (group['TigerCons_Close'] + 1e-9)
        group['z_score'] = (rel_price - rel_price.rolling(120, min_periods=30).mean()) / (rel_price.rolling(120, min_periods=30).std() + 1e-9)

    return group

# ============================================================
# [SECTION 5] 실행 및 저장
# ============================================================
if __name__ == "__main__":
    df_raw = fetch_construction_data()

    if not df_raw.empty:
        print("🚀 건설 섹터 파생 지표 산출 중...")
        df_processed = df_raw.groupby('Stock_Name', group_keys=False).apply(calculate_cons_metrics, include_groups=False)

        df_processed['Stock_Name'] = df_raw.sort_values(['Stock_Name', 'Date'])['Stock_Name'].values
        df_processed['Ticker'] = df_raw.sort_values(['Stock_Name', 'Date'])['Ticker'].values

        df_processed = df_processed.sort_values(['Stock_Name', 'Date']).reset_index(drop=True)
        df_final = df_processed[df_processed['Date'] >= USER_START_DATE].copy()

        print("-" * 30)
        if 'bsi_momentum' in df_final.columns:
            print(f"📊 bsi_momentum 데이터 수: {df_final['bsi_momentum'].count()} 건")
        else:
            print("⚠️ bsi_momentum 컬럼이 생성되지 않았습니다.")

        final_cols = ['Date', 'Ticker', 'Stock_Name', 'Close', 'interest_beta', 'fx_correlation', 'bsi_momentum', 'mfg_lag3', 'z_score']
        actual_cols = [c for c in final_cols if c in df_final.columns]
        df_final = df_final[actual_cols]

        df_final.to_csv('construction_processed.csv', index=False, encoding='utf-8-sig')
        print("✅ 오류 해결 및 전처리 완료: construction_processed.csv")
        print(df_final.head(10))