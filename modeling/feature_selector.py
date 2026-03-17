class FeatureSelector:
    def __init__(self):
        # 1. 공통 피쳐
        self.common_base = [
            'trade_date', 'ticker', 'stock_name', 'open', 'high', 'low', 'close', 
            'volume', 'short_balance', 'news_score', 'usdkrw', 'wti', 'brent', 
            'close_kospi200', 'bull_dummy', 'mkt_ret', 'mkt_vol_20', 'vol_threshold', 
            'high_vol_dummy', 'mkt_regime', 'cli', 'cli_lag1', 'cli_lag3', 'cli_lag6'
        ]

        # 2. 단기 예측 피쳐 (기술적 지표 + 수급)
        self.short_term_list = [
            'ma5', 'ma20', 'foreign_net_amt', 'inst_net_amt', 'rsi', 'macd', 
            'macd_signal', 'bb_upper', 'bb_lower', 'bb_breakout', 
            'golden_cross_5_20', 'death_cross_5_20', 'msci_event'
        ]

        # 3. 중장기 예측 피쳐 (장기 추세 + 펀더멘털 + 매크로)
        self.long_term_list = [
            'ma60', 'ma120', 'ma200', 'golden_cross_20_60', 'death_cross_20_60',
            'revenue', 'revenue_growth', 'operating_income', 'operating_margin', 
            'net_income', 'depreciation', 'rnd_expense', 'roe', 'roa', 'debt_ratio', 
            'shares', 'market_cap', 'per', 'pbr', 'ebitda', 'ev_ebitda',
            'us_cpi', 'us_core_cpi', 'us_core_pce', 'us_unrate', 'us_init_claims',
            'us_policy_rate', 'base_rate', 'us_ust_3y', 'us_ust_10y', 'ktb3y', 'ktb10y', 
            'kr_cpi', 'unemployment_rate', 'ccsi', 'export_total', 'export_yoy', 
            'import_total', 'import_yoy', 'gdp_level', 'gdp_qoq', 'jpy3', 'jpy10', 
            'pmi', 'rate_diff_policy', 'rate_diff_3y', 'rate_diff_10y'
        ]

    def _get_sector_derivative_features(self, df):
        """통합된 데이터에서 섹터별 파생 지표를 동적으로 추출"""
        try:
            cols = list(df.columns)
            start_idx = cols.index('cli_lag6') + 1
            end_idx = cols.index('revenue')
            
            if start_idx < end_idx:
                sector_features = cols[start_idx:end_idx]
                return sector_features
            return []
        except (ValueError, IndexError):
            return []

    def get_features(self, df, mode='short'):
        """모드에 따른 학습용 피처셋(X) 반환"""
        # 섹터 파생 지표 동적 추출
        sector_features = self._get_sector_derivative_features(df)
        
        # 공통 피쳐 결합 (기본 + 섹터 파생)
        common_total = self.common_base + sector_features
        
        if mode == 'short':
            # 단기 모델용: 공통 + 단기 리스트
            selected_features = common_total + self.short_term_list
        elif mode == 'long':
            # 중장기 모델용: 공통 + 중장기 리스트
            selected_features = common_total + self.long_term_list
        else:
            # 전체 피쳐
            selected_features = list(set(common_total + self.short_term_list + self.long_term_list))

        # 실제 존재하는 컬럼만 필터링
        final_cols = [c for c in selected_features if c in df.columns]
        
        X = df[final_cols]
        
        return X