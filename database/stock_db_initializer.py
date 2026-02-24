import pymysql
import os

def initialize_stock_db():
    # DB 생성 단계 (기존 STOCK_DB가 없을 수 있으므로 database 인자 없이 연결)
    host = os.environ.get('DB_HOST')
    port = int(os.environ.get('DB_PORT'))
    user = os.getenv('DB_USER')
    password = os.getenv('DB_PASSWORD')

    init_conn = pymysql.connect(
        host=host, port=port, user=user, password=password)
    
    try:
        with init_conn.cursor() as cur:
            # DB 생성 및 사용 설정
            cur.execute('CREATE DATABASE IF NOT EXISTS STOCK_DB CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;')
            cur.execute('USE STOCK_DB;')
            print("STOCK_DB 생성 및 선택 완료.")
            
        # 테이블 생성
        tables = {
            "SECTOR_TB": """
                CREATE TABLE SECTOR_TB (
                    sector_code VARCHAR(10) NOT NULL,
                    sector_name VARCHAR(100) NOT NULL,
                    PRIMARY KEY(sector_code)
                );
            """,
            "KOSPI200_STOCKS_TB": """
                CREATE TABLE KOSPI200_STOCKS_TB (
                    ticker VARCHAR(10) NOT NULL,
                    stock_name VARCHAR(100),
                    sector_code VARCHAR(10) NOT NULL,
                    is_active BOOLEAN DEFAULT TRUE,
                    PRIMARY KEY(ticker),
                    CONSTRAINT fk_stocks_sector
                        FOREIGN KEY(sector_code) REFERENCES SECTOR_TB(sector_code)
                );
            """,
            "STOCK_TB": """
                CREATE TABLE STOCK_TB (
                    trade_date DATE NOT NULL,
                    ticker VARCHAR(10) NOT NULL,
                    stock_name VARCHAR(100),
                    open INT,
                    high INT,
                    low INT,
                    close INT,
                    volume BIGINT,
                    foreign_net_amt BIGINT,
                    inst_net_amt BIGINT,
                    ma5 DECIMAL(16,6),
                    ma20 DECIMAL(16,6),
                    ma60 DECIMAL(16,6),
                    ma120 DECIMAL(16,6),
                    bb_upper DECIMAL(16,6),
                    bb_lower DECIMAL(16,6),
                    bb_breakout TINYINT(1),
                    msci_event BOOLEAN,
                    rsi DECIMAL(16,6),
                    macd DECIMAL(16,6),
                    macd_signal DECIMAL(16,6),
                    golden_cross_5_20 BOOLEAN,
                    death_cross_5_20 BOOLEAN,
                    golden_cross_20_60 BOOLEAN,
                    death_cross_20_60 BOOLEAN,
                    PRIMARY KEY(trade_date, ticker),
                    CONSTRAINT fk_stock_ticker
                        FOREIGN KEY(ticker) REFERENCES KOSPI200_STOCKS_TB(ticker)
                );
            """,
            "MACROECONOMICS_TB": """
                CREATE TABLE MACROECONOMICS_TB (
                    trade_date DATE NOT NULL,
                    us_cpi DECIMAL(10,4),
                    us_core_cpi DECIMAL(10,4),
                    us_core_pce DECIMAL(10,4),
                    us_unrate DECIMAL(8,4),
                    us_init_claims INT,
                    us_policy_rate DECIMAL(8,4),
                    us_ust_3y DECIMAL(8,4),
                    us_ust_10y DECIMAL(8,4),
                    ktb3y DECIMAL(8,4),
                    ktb10y DECIMAL(8,4),
                    usdkrw DECIMAL(10,4),
                    base_rate DECIMAL(8,4),
                    wti DECIMAL(10,4),
                    brent DECIMAL(10,4),
                    kr_cpi DECIMAL(10,4),
                    unemployment_rate DECIMAL(8,4),
                    ccsi DECIMAL(10,2),
                    export_total BIGINT,
                    export_yoy DECIMAL(10,6),
                    import_total BIGINT,
                    import_yoy DECIMAL(10,6),
                    gdp_level DECIMAL(14,2),
                    gdp_qoq DECIMAL(10,6),
                    jpy3 DECIMAL(8,4),
                    jpy10 DECIMAL(8,4),
                    pmi DECIMAL(6,2),
                    rate_diff_policy DECIMAL(8,4),
                    rate_diff_3y DECIMAL(8,4),
                    rate_diff_10y DECIMAL(8,4),
                    PRIMARY KEY(trade_date)
                );
            """,
            "FUNDAMENTAL_TB": """
                CREATE TABLE FUNDAMENTAL_TB (
                    ticker VARCHAR(10) NOT NULL,
                    year SMALLINT NOT NULL,
                    reprt_code INT NOT NULL,
                    revenue BIGINT,
                    revenue_growth DECIMAL(10,6),
                    operating_income BIGINT,
                    operating_margin DECIMAL(10,6),
                    net_income BIGINT,
                    depreciation BIGINT,
                    ebitda BIGINT,
                    equity BIGINT,
                    assets BIGINT,
                    liabilities BIGINT,
                    cash BIGINT,
                    roe DECIMAL(10,6),
                    roa DECIMAL(10,6),
                    debt_ratio DECIMAL(10,6),
                    cfo BIGINT,
                    capex BIGINT,
                    fcf BIGINT,
                    end_date DATE NOT NULL,
                    price INT,
                    shares BIGINT,
                    market_cap BIGINT,
                    per DECIMAL(16,6),
                    pbr DECIMAL(16,6),
                    ev BIGINT,
                    ev_ebitda DECIMAL(16,6),
                    PRIMARY KEY(ticker, year, reprt_code),
                    CONSTRAINT fk_funda_ticker
                        FOREIGN KEY(ticker) REFERENCES KOSPI200_STOCKS_TB(ticker)
                );
            """,
            "COMMON_TB": """
                CREATE TABLE COMMON_TB (
                    trade_date DATE NOT NULL,
                    close_kospi200 DECIMAL(10,2),
                    ma200 DECIMAL(12,6),
                    bull_dummy BOOLEAN,
                    mkt_ret DECIMAL(18,12),
                    mkt_vol_20 DECIMAL(18,12),
                    vol_threshold DECIMAL(18,12),
                    high_vol_dummy BOOLEAN,
                    mkt_regime TINYINT,
                    cli DECIMAL(10,2),
                    cli_lag1 DECIMAL(10,2),
                    cli_lag3 DECIMAL(10,2),
                    cli_lag6 DECIMAL(10,2),
                    PRIMARY KEY(trade_date)
                );
            """,
            "COMM_TB": """
                CREATE TABLE COMM_TB (
                    trade_date DATE NOT NULL,
                    ticker VARCHAR(10) NOT NULL,
                    corr_ndx DECIMAL(18,12),
                    interest_beta DECIMAL(18,12),
                    z_score DECIMAL(18,12),
                    PRIMARY KEY(trade_date, ticker),
                    CONSTRAINT fk_comm_ticker
                        FOREIGN KEY(ticker) REFERENCES KOSPI200_STOCKS_TB(ticker)
                );
            """,
            "CONS_DISC_TB": """
                CREATE TABLE CONS_DISC_TB (
                    trade_date DATE NOT NULL,
                    ticker VARCHAR(10) NOT NULL,
                    purchasing_power_mom DECIMAL(18,12),
                    durables_ir_beta DECIMAL(18,12),
                    csi_sentiment DECIMAL(10,2),
                    cli_lag DECIMAL(10,2),
                    z_score DECIMAL(18,12),
                    PRIMARY KEY(trade_date, ticker),
                    CONSTRAINT fk_cons_disc_ticker
                        FOREIGN KEY(ticker) REFERENCES KOSPI200_STOCKS_TB(ticker)
                );
            """,
            "CONS_STAPLES_TB": """
                CREATE TABLE CONS_STAPLES_TB (
                    trade_date DATE NOT NULL,
                    ticker VARCHAR(10) NOT NULL,
                    real_revenue_growth DECIMAL(18,12),
                    ebitda_margin DECIMAL(18,12),
                    csi_sentiment DECIMAL(10,2),
                    z_score DECIMAL(18,12),
                    PRIMARY KEY(trade_date, ticker),
                    CONSTRAINT fk_cons_staples_ticker
                        FOREIGN KEY(ticker) REFERENCES KOSPI200_STOCKS_TB(ticker)
                );
            """,
            "CONSTRUCTION_TB": """
                CREATE TABLE CONSTRUCTION_TB (
                    trade_date DATE NOT NULL,
                    ticker VARCHAR(10) NOT NULL,
                    interest_beta DECIMAL(18,12),
                    fx_correlation DECIMAL(18,12),
                    bsi_momentum DECIMAL(10,4),
                    mfg_lag3 DECIMAL(10,2),
                    z_score DECIMAL(18,12),
                    PRIMARY KEY(trade_date, ticker),
                    CONSTRAINT fk_cons_ticker
                        FOREIGN KEY(ticker) REFERENCES KOSPI200_STOCKS_TB(ticker)
                );
            """,
            "ENER_CHEM_TB": """
                CREATE TABLE ENER_CHEM_TB (
                    trade_date DATE NOT NULL,
                    ticker VARCHAR(10) NOT NULL,
                    spread_momentum DECIMAL(18,12),
                    mfg_lag3 DECIMAL(10,2),
                    mfg_lag6 DECIMAL(10,2),
                    oil_beta DECIMAL(18,12),
                    z_score DECIMAL(18,12),
                    PRIMARY KEY(trade_date, ticker),
                    CONSTRAINT fk_ener_chem_ticker
                        FOREIGN KEY(ticker) REFERENCES KOSPI200_STOCKS_TB(ticker)
                );
            """,
            "FINANCE_TB": """
                CREATE TABLE FINANCE_TB (
                    trade_date DATE NOT NULL,
                    ticker VARCHAR(10) NOT NULL,
                    interest_beta DECIMAL(18,12),
                    vix_corr DECIMAL(18,12),
                    global_fin_beta DECIMAL(18,12),
                    z_score DECIMAL(18,12),
                    PRIMARY KEY(trade_date, ticker),
                    CONSTRAINT fk_fin_ticker
                        FOREIGN KEY(ticker) REFERENCES KOSPI200_STOCKS_TB(ticker)
                );
            """,
            "HEALTHCARE_TB": """
                CREATE TABLE HEALTHCARE_TB (
                    trade_date DATE NOT NULL,
                    ticker VARCHAR(10) NOT NULL,
                    rnd_ratio DECIMAL(18,12),
                    pbr_zscore DECIMAL(18,12),
                    is_pbr_overheated BOOLEAN,
                    vol_ratio DECIMAL(18,12),
                    is_high_vol_stock BOOLEAN,
                    z_score DECIMAL(18,12),
                    PRIMARY KEY(trade_date, ticker),
                    CONSTRAINT fk_heal_ticker
                        FOREIGN KEY(ticker) REFERENCES KOSPI200_STOCKS_TB(ticker)
                );
            """,
            "HEAVY_IND_TB": """
                CREATE TABLE HEAVY_IND_TB (
                    trade_date DATE NOT NULL,
                    ticker VARCHAR(10) NOT NULL,
                    fx_beta DECIMAL(18,12),
                    mfg_momentum DECIMAL(18,12),
                    mfg_lag3 DECIMAL(10,2),
                    energy_momentum DECIMAL(18,12),
                    z_score DECIMAL(18,12),
                    PRIMARY KEY(trade_date, ticker),
                    CONSTRAINT fk_heavy_ticker
                        FOREIGN KEY(ticker) REFERENCES KOSPI200_STOCKS_TB(ticker)
                );
            """,
            "INDUSTRIALS_TB": """
                CREATE TABLE INDUSTRIALS_TB (
                    trade_date DATE NOT NULL,
                    ticker VARCHAR(10) NOT NULL,
                    vol_ratio DECIMAL(18,12),
                    logistics_momentum DECIMAL(18,12),
                    ship_vol_lag3 INT,
                    mfg_lag3 DECIMAL(10,2),
                    mfg_lag6 DECIMAL(10,2),
                    z_score DECIMAL(18,12),
                    PRIMARY KEY(trade_date, ticker),
                    CONSTRAINT fk_ind_ticker
                        FOREIGN KEY(ticker) REFERENCES KOSPI200_STOCKS_TB(ticker)
                );
            """,
            "IT_TB": """
                CREATE TABLE IT_TB (
                    trade_date DATE NOT NULL,
                    ticker VARCHAR(10) NOT NULL,
                    soxx_corr DECIMAL(18,12),
                    apple_momentum DECIMAL(18,12),
                    mfg_cycle_momentum DECIMAL(18,12),
                    z_score DECIMAL(18,12),
                    PRIMARY KEY(trade_date, ticker),
                    CONSTRAINT fk_it_ticker
                        FOREIGN KEY(ticker) REFERENCES KOSPI200_STOCKS_TB(ticker)
                );
            """,
            "MATERIALS_TB": """
                CREATE TABLE MATERIALS_TB (
                    trade_date DATE NOT NULL,
                    ticker VARCHAR(10) NOT NULL,
                    china_momentum DECIMAL(18,12),
                    mfg_lag3 DECIMAL(10,2),
                    cli_lag3 DECIMAL(10,2),
                    copper_beta DECIMAL(18,12),
                    oil_beta DECIMAL(18,12),
                    steel_beta DECIMAL(18,12),
                    z_score DECIMAL(18,12),
                    PRIMARY KEY(trade_date, ticker),
                    CONSTRAINT fk_mate_ticker
                        FOREIGN KEY(ticker) REFERENCES KOSPI200_STOCKS_TB(ticker)
                );
            """,
            "RND_TB": """
                CREATE TABLE RND_TB (
                    ticker VARCHAR(10) NOT NULL,
                    year SMALLINT NOT NULL,
                    quarter ENUM('Q1','Q2','Q3','Q4') NOT NULL,
                    rnd_expense BIGINT,
                    PRIMARY KEY(ticker, year, quarter),
                    CONSTRAINT fk_rnd_ticker
                        FOREIGN KEY(ticker) REFERENCES KOSPI200_STOCKS_TB(ticker)
                );
            """,
            "NEWS_TB": """
                CREATE TABLE NEWS_TB (
                    trade_date DATE NOT NULL,
                    ticker VARCHAR(10) NOT NULL,
                    stock_name VARCHAR(100),
                    score DECIMAL(18,12),
                    PRIMARY KEY(trade_date, ticker),
                    CONSTRAINT fk_news_ticker
                        FOREIGN KEY(ticker) REFERENCES KOSPI200_STOCKS_TB(ticker)
                );
            """
        }
        
        with init_conn.cursor() as cur:
            for table_name, create_sql in tables.items():
                try:
                    cur.execute(create_sql)
                    print(f"Table '{table_name}' 생성 성공.")
                except Exception as table_err:
                    print(f"Table '{table_name}' 생성 중 에러 (이미 존재할 수 있음): {table_err}")
                    
    finally:
        init_conn.close()

if __name__ == "__main__":
    initialize_stock_db()