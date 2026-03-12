# 메인 주식 데이터

import time
import calendar
import pandas as pd
import pandas_ta as ta
from pykrx import stock
from datetime import datetime
import os
import warnings

# 빨간 경고 메시지 끄기
warnings.filterwarnings('ignore')

# ==========================================
# 1. 설정값 (연도 설정)
# ==========================================
FETCH_START_YEAR = 2022  # 지표 계산용 (여유있게 전년도부터)
SAVE_START_YEAR = 2023   # 실제 저장할 연도 시작
SAVE_END_YEAR = 2025     # 실제 저장할 연도 끝

# ==========================================
# 2. 티커(종목코드) 수리공 함수
# ==========================================
def clean_ticker(x):
    x = str(x).strip()
    if x.lower() == 'nan' or x == '': return ''
    if x.endswith('.0'): x = x[:-2]
    return x.zfill(6) # 6자리 채우기 (005930)

# ==========================================
# 3. 종목 리스트 파일 읽기
# ==========================================
def get_tickers_from_file():
    filename = "KOSPI200_converted.csv" # 코스피 200 리스트(종목 + 티커)
    
    # 파일이 없으면 대체 파일 찾기
    if not os.path.exists(filename):
        if os.path.exists("KOSPI200_fixed.csv"):
            filename = "KOSPI200_fixed.csv" # 티커 6자리 수정 파일
        else:
            print(f"❌ '{filename}' 파일이 없어요! 같은 폴더에 파일이 있는지 확인해주세요.")
            return []
    
    print(f"📂 '{filename}' 파일을 읽습니다...")
    
    try:
        # 한글 인코딩 자동 감지 시도
        try:
            df = pd.read_csv(filename, encoding='utf-8', converters={'티커': str})
        except:
            df = pd.read_csv(filename, encoding='cp949', converters={'티커': str})

        df.columns = df.columns.str.strip()
        
        # 티커 컬럼 이름 찾기
        target_col = '티커'
        for cand in ['Code', 'Symbol', 'code', 'symbol', '티커']:
            if cand in df.columns:
                target_col = cand
                break
        
        if target_col not in df.columns:
            print("❌ 파일에 티커(Code/Symbol) 컬럼이 없어요.")
            return []

        # 티커 정리 후 리스트로 반환
        df[target_col] = df[target_col].apply(clean_ticker)
        return list(zip(df[target_col], df['종목명']))

    except Exception as e:
        print(f"❌ 파일 읽기 에러: {e}")
        return []

# ==========================================
# 4. 데이터 수집 (가격 + 투자자별 매매동향)
# ==========================================
def fetch_all_data(ticker, start_year, end_year):
    ticker = clean_ticker(ticker)
    
    s_date = f"{start_year}0101"
    today = datetime.now().strftime("%Y%m%d")
    e_date = f"{end_year}1231"
    
    # 미래 날짜는 오늘로 제한
    if e_date > today: e_date = today
    
    try:
        # 1. 가격 정보 (시가, 고가, 저가, 종가, 거래량)
        df_price = stock.get_market_ohlcv(s_date, e_date, ticker)
        if df_price.empty: return pd.DataFrame()
        time.sleep(0.05) # 서버 부하 방지용 짧은 휴식
        
        # 2. 투자자 정보 (외국인, 기관, 개인 수급)
        try:
            df_inv = stock.get_market_trading_value_by_date(s_date, e_date, ticker)
            
            # 컬럼 이름 통일
            rename_map = {
                '외국인합계':'Foreign_Net_Amt', 
                '기관합계':'Inst_Net_Amt', 
                '개인':'Indiv_Net_Amt', 
                '기타법인':'Other_Net_Amt'
            }
            df_inv = df_inv.rename(columns=rename_map)
            
            cols = ['Foreign_Net_Amt', 'Inst_Net_Amt', 'Indiv_Net_Amt', 'Other_Net_Amt']
            # 필요한 컬럼이 다 있는지 확인하고 가져오기
            if set(cols).issubset(df_inv.columns):
                df_inv = df_inv[cols]
            else:
                df_inv = pd.DataFrame()
        except: 
            df_inv = pd.DataFrame()
        
        # 가격 데이터와 투자자 데이터 합치기
        df_merged = df_price.join(df_inv, how='left')
            
        return df_merged.fillna(0)

    except Exception as e:
        print(f"⚠️ 데이터 수집 에러 ({ticker}): {e}")
        return pd.DataFrame()

# ==========================================
# 5. 지표 계산 (핵심 로직!)
# ==========================================
def calculate_indicators(df):
    # 한글 컬럼명을 영어로 변경
    rename = {'시가':'Open', '고가':'High', '저가':'Low', '종가':'Close', '거래량':'Volume'}
    df = df.rename(columns=rename)
    
    # 숫자형으로 변환 (에러 방지)
    cols = ['Open', 'High', 'Low', 'Close', 'Volume']
    for c in cols:
        if c in df.columns: df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0)
        
    # 데이터가 너무 적으면 계산 불가
    if len(df) < 60: return df
    
    try:
        # --- 이동평균선 ---
        for ma in [5, 10, 20, 60, 120]: 
            df[f'MA{ma}'] = df['Close'].rolling(window=ma).mean()
        
        # --- 볼린저 밴드 (수정됨) ---
        # pandas_ta 결과 순서: [Lower(0), Mid(1), Upper(2)]
        bb = ta.bbands(df['Close'], length=20, std=2)
        if bb is not None:
            df['BB_Lower'] = bb.iloc[:, 0] # 바닥
            df['BB_Upper'] = bb.iloc[:, 2] # 천장
            
            # 볼린저 밴드 돌파 (Breakout) 로직 수정
            # 1 = 상단 돌파 (매수 신호), -1 = 하단 돌파 (매도 신호)
            df['BB_Breakout'] = 0
            
            prev_close = df['Close'].shift(1)
            prev_upper = df['BB_Upper'].shift(1)
            prev_lower = df['BB_Lower'].shift(1)
            
            # 상향 돌파: 어제는 밴드 안, 오늘은 밴드 위
            cond_up = (prev_close <= prev_upper) & (df['Close'] > df['BB_Upper'])
            df.loc[cond_up, 'BB_Breakout'] = 1
            
            # 하향 돌파: 어제는 밴드 안, 오늘은 밴드 아래
            cond_down = (prev_close >= prev_lower) & (df['Close'] < df['BB_Lower'])
            df.loc[cond_down, 'BB_Breakout'] = -1
            
        # --- 골든/데드 크로스 (수정됨) ---
        # [단기] 5일 vs 20일
        ma5_prev = df['MA5'].shift(1)
        ma20_prev = df['MA20'].shift(1)
        
        df['Golden_Cross_5_20'] = 0
        # 골든: 5일선이 20일선을 아래에서 위로 뚫음
        cond_gc_5_20 = (ma5_prev < ma20_prev) & (df['MA5'] > df['MA20'])
        df.loc[cond_gc_5_20, 'Golden_Cross_5_20'] = 1
        
        df['Death_Cross_5_20'] = 0
        # 데드: 5일선이 20일선을 위에서 아래로 뚫음
        cond_dc_5_20 = (ma5_prev > ma20_prev) & (df['MA5'] < df['MA20'])
        df.loc[cond_dc_5_20, 'Death_Cross_5_20'] = 1

        # [중기] 20일 vs 60일
        ma60_prev = df['MA60'].shift(1)
        # ma20_prev는 위에서 이미 구함
        
        df['Golden_Cross_20_60'] = 0
        cond_gc_20_60 = (ma20_prev < ma60_prev) & (df['MA20'] > df['MA60'])
        df.loc[cond_gc_20_60, 'Golden_Cross_20_60'] = 1
        
        df['Death_Cross_20_60'] = 0
        cond_dc_20_60 = (ma20_prev > ma60_prev) & (df['MA20'] < df['MA60'])
        df.loc[cond_dc_20_60, 'Death_Cross_20_60'] = 1
        
        # --- RSI & MACD ---
        df['RSI'] = ta.rsi(df['Close'], length=14)
        macd = ta.macd(df['Close'])
        if macd is not None: 
            df['MACD'] = macd.iloc[:, 0]
            df['MACD_Signal'] = macd.iloc[:, 2]
            
        # --- MSCI 리밸런싱 날짜 (2,5,8,11월 말일) ---
        msci_dates = []
        for y in range(FETCH_START_YEAR, SAVE_END_YEAR + 1):
            for m in [2, 5, 8, 11]:
                last = calendar.monthrange(y, m)[1]
                msci_dates.append(pd.bdate_range(f"{y}-{m}-01", f"{y}-{m}-{last}")[-1].strftime("%Y-%m-%d"))
        
        df['MSCI_Event'] = 0
        df.loc[df.index.strftime('%Y-%m-%d').isin(msci_dates), 'MSCI_Event'] = 1
        
    except Exception as e:
        # 가끔 데이터가 꼬인 종목은 패스
        pass
    
    return df.fillna(0)

# ==========================================
# 6. 메인 실행 함수
# ==========================================
def main():
    targets = get_tickers_from_file()
    if not targets: return
    
    print(f"🚀 총 {len(targets)}개 종목의 데이터 수집을 시작합니다!")
    print(f"📅 수집 기간: {FETCH_START_YEAR} ~ {SAVE_END_YEAR}")
    
    all_data = []
    
    for i, (ticker, name) in enumerate(targets):
        # 진행 상황 표시 (줄바꿈 없이 덮어쓰기)
        print(f"[{i+1}/{len(targets)}] {name}({ticker}) 처리 중...      ", end="\r")
        
        df = fetch_all_data(ticker, FETCH_START_YEAR, SAVE_END_YEAR)
        if df.empty: continue
        
        df = calculate_indicators(df)
        df['Ticker'] = ticker 
        df['Stock_Name'] = name
        all_data.append(df)
        
    print("\n\n💾 CSV 파일로 저장 중입니다...")
    
    if all_data:
        full = pd.concat(all_data)
        
        # 연도별로 쪼개서 저장
        for year in range(SAVE_START_YEAR, SAVE_END_YEAR+1):
            yf_data = full[full.index.year == year]
            
            if not yf_data.empty:
                # 저장할 컬럼 목록
                cols = [
                    'Ticker', 'Stock_Name', 'Close', 'Open', 'High', 'Low', 'Volume',
                    'Foreign_Net_Amt', 'Inst_Net_Amt', 
                    'MA5', 'MA20', 'MA60', 'MA120', 'BB_Upper', 'BB_Lower', 'BB_Breakout',
                    'Golden_Cross_5_20', 'Death_Cross_5_20',
                    'Golden_Cross_20_60', 'Death_Cross_20_60',
                    'MSCI_Event', 'RSI', 'MACD', 'MACD_Signal'
                ]
                
                # 없는 컬럼은 0으로 채우기 (안전장치)
                for c in cols:
                    if c not in yf_data.columns: yf_data[c] = 0
                
                # 파일명 생성 및 저장
                fname = f"stock_data_{year}.csv"
                
                # [핵심] 한글 깨짐 방지를 위해 'utf-8-sig' 사용
                yf_data[cols].to_csv(fname, index=True, encoding='utf-8-sig')
                print(f"✅ {fname} 저장 완료!")
    else:
        print("❌ 데이터를 하나도 못 가져왔어요. 인터넷 연결이나 티커 파일을 확인해주세요.")

if __name__ == "__main__":
    main()

# 공매도 잔고 추가 (날짜 컬럼 이름 자동 수리 버전)

import pandas as pd
from pykrx import stock
import time
from tqdm import tqdm
import warnings
import os

# 빨간 경고 글씨 무시하기
warnings.filterwarnings('ignore')

def add_short_selling_data(file_path):
    print(f"📂 '{file_path}' 파일을 불러오는 중입니다...")
    
    try:
        # 파일을 읽습니다. (한글 깨짐 방지 처리)
        try:
            df = pd.read_csv(file_path, encoding='utf-8-sig')
        except:
            df = pd.read_csv(file_path, encoding='cp949')

        # ==========================================
        # [수정 1] '날짜'를 'Date'로 이름표 갈아끼우기
        # ==========================================
        if '날짜' in df.columns:
            print("🔧 컬럼 이름 '날짜'를 'Date'로 변경합니다.")
            df = df.rename(columns={'날짜': 'Date'})
            
        # 이제 'Date' 컬럼이 확실히 있으니까 날짜 형식으로 변환
        df['Date'] = pd.to_datetime(df['Date'])
        
        unique_tickers = df['Ticker'].unique()
        print(f"총 {len(unique_tickers)}개 종목의 공매도 잔고를 가져옵니다. 힘내라 컴퓨터! 🏋️")
        
        short_data_list = []
        
        for ticker in tqdm(unique_tickers):
            # 티커 6자리로 예쁘게 만들기
            ticker_str = str(ticker).strip().zfill(6)
            
            # 해당 종목 데이터 기간 확인
            subset = df[df['Ticker'] == ticker]
            if subset.empty: continue
            
            start_date = subset['Date'].min().strftime("%Y%m%d")
            end_date = subset['Date'].max().strftime("%Y%m%d")
            
            try:
                # 공매도 잔고 요청
                df_short = stock.get_shorting_balance_by_date(start_date, end_date, ticker_str)
                df_short = df_short.reset_index()
                
                # 컬럼 이름 찾기 (공매도잔고금액 or 공매도금액)
                target_col = 'Short_Balance_Value' # 기본값
                
                # pykrx 버전에 따라 컬럼명이 다를 수 있어서 확인
                possible_cols = ['공매도잔고금액', '공매도금액', '잔고금액']
                found_col = None
                
                for col in possible_cols:
                    if col in df_short.columns:
                        found_col = col
                        break
                
                if found_col:
                    df_short = df_short.rename(columns={
                        '날짜': 'Date',
                        found_col: 'Short_Balance_Value'
                    })
                else:
                    # 못 찾으면 0으로 채움
                    df_short['Date'] = df_short['날짜'] if '날짜' in df_short.columns else pd.to_datetime(df_short.index)
                    df_short['Short_Balance_Value'] = 0

                # 합치기용 임시 데이터프레임
                temp_df = pd.DataFrame()
                temp_df['Date'] = pd.to_datetime(df_short['Date'])
                temp_df['Short_Balance_Value'] = df_short['Short_Balance_Value']
                temp_df['Ticker'] = ticker 
                
                short_data_list.append(temp_df)
                time.sleep(0.3) 
                
            except Exception as e:
                # 에러나면 패스
                continue

        if short_data_list:
            print("🔗 데이터를 합치는 중...")
            all_short_data = pd.concat(short_data_list)
            all_short_data['Date'] = pd.to_datetime(all_short_data['Date'])
            
            # 원래 데이터에 공매도 데이터 붙이기
            merged_df = pd.merge(df, all_short_data, on=['Date', 'Ticker'], how='left')
            merged_df['Short_Balance_Value'] = merged_df['Short_Balance_Value'].fillna(0)
            
            # 파일 덮어쓰기 (한글 안 깨지게 utf-8-sig)
            merged_df.to_csv(file_path, index=False, encoding='utf-8-sig')
            print(f"🎉 성공! '{file_path}' 파일 업데이트 완료!")
            
        else:
            print("😭 데이터를 하나도 못 가져왔어요.")

    except Exception as e:
        print(f"❌ 파일 처리 중 에러 발생: {e}")

# --- 실행 ---
files_to_process = [
    'stock_data_2023.csv',
    'stock_data_2024.csv',
    'stock_data_2025.csv'
]

for file in files_to_process:
    if os.path.exists(file):
        add_short_selling_data(file)
    else:
        print(f"❌ '{file}' 파일이 없어요.")

        # 나스닥 지수 (종가만) 추가 - 에러 수정 버전

import FinanceDataReader as fdr
import pandas as pd
import warnings

# 경고 메시지 무시
warnings.filterwarnings('ignore')

def get_nasdaq_data():
    print("🚀 나스닥 데이터(종가만!) 수집을 시작합니다!")

    # 1. 날짜 정하기
    start_date = '2023-01-01'
    end_date = '2025-12-31'

    # 2. 나스닥(IXIC) 지수 가져오기
    try:
        df = fdr.DataReader('IXIC', start_date, end_date)
    except Exception as e:
        print(f"❌ 데이터 가져오기 실패: {e}")
        return

    # 3. 날짜가 인덱스(목차)로 되어있는데, 보기 좋게 컬럼으로 빼기
    df = df.reset_index()

    # ==========================================
    # [수정] 여기가 핵심입니다! 🔧
    # 첫 번째 컬럼(날짜) 이름이 'index'든 뭐든 상관없이 'Date'로 강제 변경!
    # ==========================================
    df.rename(columns={df.columns[0]: 'Date'}, inplace=True)

    # 이제 'Date'가 확실히 있으니까 안심하고 가져옵니다.
    df = df[['Date', 'Close']] 
    
    # 다른 주식 종가랑 헷갈리지 않게 이름을 'NASDAQ_Close'로 바꿔줍니다.
    df = df.rename(columns={'Close': 'NASDAQ_Close'})

    # 4. 파일로 저장하기
    file_name = 'nasdaq_2023_2025.csv'
    df.to_csv(file_name, index=False, encoding='utf-8-sig') 

    print(f"🎉 성공! '{file_name}' 파일이 생성되었습니다.")
    print("데이터 미리보기:")
    print(df.head()) 

# --- 실행 ---
get_nasdaq_data()