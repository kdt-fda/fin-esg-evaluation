import warnings
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from xgboost import XGBRegressor

from modeling.data_joiner import StockDataJoiner
from modeling.feature_selector import FeatureSelector

from dotenv import load_dotenv

load_dotenv()

# ============================================================
# 1. 기존 사용자 클래스 확장/활용
# ============================================================

class ModelingFeatureBuilder:
    """
    StockDataJoiner로 가져온 원본 데이터프레임에
    단기 예측용 lag / volatility / rolling feature를 추가한다.
    """

    def __init__(self):
        self.required_price_cols = ["trade_date", "close", "volume"]

    def validate(self, df: pd.DataFrame):
        missing = [c for c in self.required_price_cols if c not in df.columns]
        if missing:
            raise ValueError(f"필수 컬럼 누락: {missing}")

    def add_time_features(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()
        out["trade_date"] = pd.to_datetime(out["trade_date"])
        out["dayofweek"] = out["trade_date"].dt.dayofweek
        out["month"] = out["trade_date"].dt.month
        out["weekofyear"] = out["trade_date"].dt.isocalendar().week.astype(int)
        out["is_month_start"] = out["trade_date"].dt.is_month_start.astype(int)
        out["is_month_end"] = out["trade_date"].dt.is_month_end.astype(int)
        return out

    def add_return_features(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()

        out["ret_1"] = out["close"].pct_change(1)
        out["ret_2"] = out["close"].pct_change(2)
        out["ret_3"] = out["close"].pct_change(3)
        out["ret_5"] = out["close"].pct_change(5)
        out["ret_10"] = out["close"].pct_change(10)
        out["ret_20"] = out["close"].pct_change(20)

        out["log_ret_1"] = np.log(out["close"]).diff(1)

        return out

    def add_volatility_features(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()

        if "ret_1" not in out.columns:
            out["ret_1"] = out["close"].pct_change(1)

        out["vol_5"] = out["ret_1"].rolling(5).std()
        out["vol_10"] = out["ret_1"].rolling(10).std()
        out["vol_20"] = out["ret_1"].rolling(20).std()

        out["down_vol_10"] = out["ret_1"].where(out["ret_1"] < 0, 0).rolling(10).std()
        out["up_vol_10"] = out["ret_1"].where(out["ret_1"] > 0, 0).rolling(10).std()

        return out

    def add_price_position_features(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()

        out["price_ma5_ratio"] = out["close"] / out["close"].rolling(5).mean()
        out["price_ma10_ratio"] = out["close"] / out["close"].rolling(10).mean()
        out["price_ma20_ratio"] = out["close"] / out["close"].rolling(20).mean()
        out["price_ma60_ratio"] = out["close"] / out["close"].rolling(60).mean()

        out["rolling_high_20_ratio"] = out["close"] / out["high"].rolling(20).max()
        out["rolling_low_20_ratio"] = out["close"] / out["low"].rolling(20).min()

        return out

    def add_volume_features(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()

        vol_mean_5 = out["volume"].rolling(5).mean()
        vol_mean_20 = out["volume"].rolling(20).mean()
        vol_std_20 = out["volume"].rolling(20).std()

        out["vol_chg_1"] = out["volume"].pct_change(1)
        out["volume_ma5_ratio"] = out["volume"] / vol_mean_5
        out["volume_ma20_ratio"] = out["volume"] / vol_mean_20
        out["volume_zscore_20"] = (out["volume"] - vol_mean_20) / vol_std_20

        return out

    def add_range_features(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()

        if {"open", "high", "low", "close"}.issubset(out.columns):
            out["intraday_range"] = (out["high"] - out["low"]) / out["close"]
            out["open_close_change"] = (out["close"] - out["open"]) / out["open"]
            out["high_close_gap"] = (out["high"] - out["close"]) / out["close"]
            out["close_low_gap"] = (out["close"] - out["low"]) / out["low"]

        return out

    def add_lagged_features(self, df: pd.DataFrame, lag_cols: Optional[List[str]] = None, lags: List[int] = [1, 2, 3, 5]) -> pd.DataFrame:
        out = df.copy()
        if lag_cols is None:
            lag_cols = ["close", "ret_1", "vol_5", "volume_zscore_20", "news_score"]

        for col in lag_cols:
            if col in out.columns:
                for lag in lags:
                    out[f"{col}_lag{lag}"] = out[col].shift(lag)
        return out

    def build(self, df: pd.DataFrame) -> pd.DataFrame:
        self.validate(df)
        out = df.copy()
        out = out.sort_values("trade_date").reset_index(drop=True)

        out = self.add_time_features(out)
        out = self.add_return_features(out)
        out = self.add_volatility_features(out)
        out = self.add_price_position_features(out)
        out = self.add_volume_features(out)
        out = self.add_range_features(out)
        out = self.add_lagged_features(out)

        out = out.replace([np.inf, -np.inf], np.nan)
        return out


class FeatureSelectorExtended:
    """
    기존 FeatureSelector 철학을 유지하면서,
    short 모델에 성능 개선용 engineered feature를 추가한다.
    """

    def __init__(self, base_selector):
        self.base_selector = base_selector

        self.engineered_short_features = [
            "dayofweek", "month", "weekofyear", "is_month_start", "is_month_end",
            "ret_1", "ret_2", "ret_3", "ret_5", "ret_10", "ret_20", "log_ret_1",
            "vol_5", "vol_10", "vol_20", "down_vol_10", "up_vol_10",
            "price_ma5_ratio", "price_ma10_ratio", "price_ma20_ratio", "price_ma60_ratio",
            "rolling_high_20_ratio", "rolling_low_20_ratio",
            "vol_chg_1", "volume_ma5_ratio", "volume_ma20_ratio", "volume_zscore_20",
            "intraday_range", "open_close_change", "high_close_gap", "close_low_gap",
            "close_lag1", "close_lag2", "close_lag3", "close_lag5",
            "ret_1_lag1", "ret_1_lag2", "ret_1_lag3", "ret_1_lag5",
            "vol_5_lag1", "vol_5_lag2", "vol_5_lag3", "vol_5_lag5",
            "volume_zscore_20_lag1", "volume_zscore_20_lag2", "volume_zscore_20_lag3", "volume_zscore_20_lag5",
            "news_score_lag1", "news_score_lag2", "news_score_lag3", "news_score_lag5",
        ]

    def create_target(self, df: pd.DataFrame, horizon: int = 1) -> pd.DataFrame:
        out = df.sort_values("trade_date").copy()
        out["target_return"] = out["close"].shift(-horizon) / out["close"] - 1
        return out.dropna(subset=["target_return"])

    def get_features(self, df: pd.DataFrame, mode: str = "short") -> Tuple[pd.DataFrame, pd.Series]:
        X_base, y = self.base_selector.get_features(df, mode=mode)

        if mode == "short":
            extra_cols = [c for c in self.engineered_short_features if c in df.columns]
            X_extra = df[extra_cols].copy()
            X = pd.concat([X_base, X_extra], axis=1)
            X = X.loc[:, ~X.columns.duplicated()]
        else:
            X = X_base.copy()

        # 모델 입력 불가능 컬럼 제거
        drop_non_numeric = [c for c in ["trade_date", "ticker", "stock_name"] if c in X.columns]
        X = X.drop(columns=drop_non_numeric, errors="ignore")

        # bool -> int 변환
        for c in X.columns:
            if X[c].dtype == bool:
                X[c] = X[c].astype(int)

        # 숫자형만 사용
        X = X.select_dtypes(include=[np.number]).copy()

        return X, y


# ============================================================
# 2. 평가/시각화/예측 클래스
# ============================================================

@dataclass
class TrainResult:
    model: XGBRegressor
    train_df: pd.DataFrame
    test_df: pd.DataFrame
    X_train: pd.DataFrame
    X_test: pd.DataFrame
    y_train: pd.Series
    y_test: pd.Series
    y_pred: np.ndarray
    metrics: Dict[str, float]
    feature_importance: pd.DataFrame


class XGBoostStockForecaster:
    def __init__(self, random_state: int = 42):
        self.random_state = random_state
        self.model = None
        self.feature_columns = None

    @staticmethod
    def _direction_accuracy(y_true: np.ndarray, y_pred: np.ndarray) -> float:
        return float(np.mean(np.sign(y_true) == np.sign(y_pred)))

    @staticmethod
    def evaluate(y_true: np.ndarray, y_pred: np.ndarray) -> Dict[str, float]:
        return {
            "r2": float(r2_score(y_true, y_pred)),
            "mae": float(mean_absolute_error(y_true, y_pred)),
            "rmse": float(np.sqrt(mean_squared_error(y_true, y_pred))),
            "direction_accuracy": float(np.mean(np.sign(y_true) == np.sign(y_pred))),
        }

    def train_test_split_by_date(
        self,
        df: pd.DataFrame,
        X: pd.DataFrame,
        y: pd.Series,
        test_size: float = 0.2,
    ) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.Series, pd.Series]:
        n = len(df)
        split_idx = int(n * (1 - test_size))

        train_df = df.iloc[:split_idx].copy()
        test_df = df.iloc[split_idx:].copy()

        X_train = X.iloc[:split_idx].copy()
        X_test = X.iloc[split_idx:].copy()
        y_train = y.iloc[:split_idx].copy()
        y_test = y.iloc[split_idx:].copy()

        return train_df, test_df, X_train, X_test, y_train, y_test

    def fit(
        self,
        df: pd.DataFrame,
        X: pd.DataFrame,
        y: pd.Series,
        test_size: float = 0.2,
        model_params: Optional[Dict] = None,
    ) -> TrainResult:
        if model_params is None:
            model_params = {
                "n_estimators": 500,
                "max_depth": 5,
                "learning_rate": 0.03,
                "subsample": 0.8,
                "colsample_bytree": 0.8,
                "reg_alpha": 0.5,
                "reg_lambda": 1.0,
                "min_child_weight": 3,
                "objective": "reg:squarederror",
                "random_state": self.random_state,
            }

        mask = X.notna().all(axis=1) & y.notna()
        df_clean = df.loc[mask].reset_index(drop=True)
        X_clean = X.loc[mask].reset_index(drop=True)
        y_clean = y.loc[mask].reset_index(drop=True)

        train_df, test_df, X_train, X_test, y_train, y_test = self.train_test_split_by_date(
            df_clean, X_clean, y_clean, test_size=test_size
        )

        model = XGBRegressor(**model_params)
        model.fit(
            X_train,
            y_train,
            eval_set=[(X_train, y_train), (X_test, y_test)],
            verbose=False,
        )

        y_pred = model.predict(X_test)
        metrics = self.evaluate(y_test.values, y_pred)

        fi = pd.DataFrame(
            {
                "feature": X_train.columns,
                "importance": model.feature_importances_,
            }
        ).sort_values("importance", ascending=False)

        self.model = model
        self.feature_columns = list(X_train.columns)

        return TrainResult(
            model=model,
            train_df=train_df,
            test_df=test_df,
            X_train=X_train,
            X_test=X_test,
            y_train=y_train,
            y_test=y_test,
            y_pred=y_pred,
            metrics=metrics,
            feature_importance=fi,
        )

    def plot_actual_vs_predicted_return(self, result: TrainResult, figsize=(14, 5)):
        plt.figure(figsize=figsize)
        plt.plot(result.test_df["trade_date"], result.y_test.values, label="Actual Return")
        plt.plot(result.test_df["trade_date"], result.y_pred, label="Predicted Return")
        plt.axhline(0, linestyle="--")
        plt.title("Actual vs Predicted Return")
        plt.xlabel("Date")
        plt.ylabel("Return")
        plt.legend()
        plt.tight_layout()
        plt.show()

    def plot_actual_vs_predicted_price(self, result: TrainResult, figsize=(14, 6)):
        test_df = result.test_df.copy().reset_index(drop=True)
        pred_returns = pd.Series(result.y_pred, index=test_df.index)

        pred_prices = []
        for i in range(len(test_df)):
            base_close = test_df.loc[i, "close"]
            pred_price = base_close * (1 + pred_returns.loc[i])
            pred_prices.append(pred_price)

        future_realized_price = test_df["close"].shift(-1)

        plt.figure(figsize=figsize)
        plt.plot(test_df["trade_date"], future_realized_price, label="Actual Next Close")
        plt.plot(test_df["trade_date"], pred_prices, label="Predicted Next Close")
        plt.title("Actual vs Predicted Next-Day Price")
        plt.xlabel("Date")
        plt.ylabel("Price")
        plt.legend()
        plt.tight_layout()
        plt.show()

    def plot_feature_importance(self, result: TrainResult, top_n: int = 20, figsize=(10, 7)):
        fi = result.feature_importance.head(top_n).sort_values("importance", ascending=True)
        plt.figure(figsize=figsize)
        plt.barh(fi["feature"], fi["importance"])
        plt.title(f"Top {top_n} Feature Importance")
        plt.tight_layout()
        plt.show()

    def forecast_next_20_business_days(
        self,
        raw_df: pd.DataFrame,
        feature_builder,
        feature_selector,
        horizon: int = 20,
    ) -> pd.DataFrame:
        """
        다음 20영업일 예측.
        주의: 외생변수(뉴스/매크로/수급)는 미래값을 모르므로 마지막 값 유지 가정.
        단기 데모/운영 초안으로는 충분하지만,
        실제 성능 향상을 위해서는 외생변수 시나리오 예측이 추가되어야 한다.
        """
        if self.model is None or self.feature_columns is None:
            raise ValueError("모델이 먼저 학습되어야 합니다.")

        future_df = raw_df.copy().sort_values("trade_date").reset_index(drop=True)
        future_prices = []
        future_returns = []
        future_dates = []

        last_date = pd.to_datetime(future_df["trade_date"].iloc[-1])

        for step in range(1, horizon + 1):
            next_date = last_date + pd.offsets.BDay(step)
            new_row = future_df.iloc[-1].copy()
            new_row["trade_date"] = next_date

            # 외생변수는 마지막 값 유지
            future_df = pd.concat([future_df, pd.DataFrame([new_row])], ignore_index=True)

            rebuilt = feature_builder.build(future_df)
            rebuilt_targetless = rebuilt.copy()
            rebuilt_targetless["target_return"] = np.nan

            X_all, _ = feature_selector.get_features(rebuilt_targetless, mode="short")
            X_last = X_all.iloc[[-1]].copy()

            # 학습 당시 feature 정렬 일치
            X_last = X_last.reindex(columns=self.feature_columns, fill_value=0)
            X_last = X_last.fillna(method="ffill").fillna(0)

            pred_ret = float(self.model.predict(X_last)[0])
            prev_close = float(future_df.loc[future_df.index[-2], "close"])
            pred_close = prev_close * (1 + pred_ret)

            future_df.loc[future_df.index[-1], "close"] = pred_close
            if "open" in future_df.columns:
                future_df.loc[future_df.index[-1], "open"] = prev_close
            if "high" in future_df.columns:
                future_df.loc[future_df.index[-1], "high"] = max(prev_close, pred_close)
            if "low" in future_df.columns:
                future_df.loc[future_df.index[-1], "low"] = min(prev_close, pred_close)

            future_prices.append(pred_close)
            future_returns.append(pred_ret)
            future_dates.append(next_date)

        return pd.DataFrame(
            {
                "trade_date": future_dates,
                "pred_return": future_returns,
                "pred_close": future_prices,
            }
        )

    def plot_full_price_forecast(
        self,
        raw_df: pd.DataFrame,
        future_pred_df: pd.DataFrame,
        lookback: int = 120,
        figsize=(15, 7),
    ):
        hist = raw_df.copy().sort_values("trade_date").reset_index(drop=True)
        hist["trade_date"] = pd.to_datetime(hist["trade_date"])
        hist_plot = hist.tail(lookback)

        plt.figure(figsize=figsize)
        plt.plot(hist_plot["trade_date"], hist_plot["close"], label="Historical Close")
        plt.plot(future_pred_df["trade_date"], future_pred_df["pred_close"], label="Forecasted Close")
        plt.axvline(hist_plot["trade_date"].iloc[-1], linestyle="--")
        plt.title("Historical Price + Next 20 Business Days Forecast")
        plt.xlabel("Date")
        plt.ylabel("Price")
        plt.legend()
        plt.tight_layout()
        plt.show()


# ============================================================
# 3. 실행 함수
# ============================================================

def run_stock_xgboost_pipeline(
    stock_name: str,
    stock_data_joiner,
    base_feature_selector,
    start_date: str = "2022-01-01",
    end_date: Optional[str] = None,
    target_horizon: int = 1,
    test_size: float = 0.2,
):
    """
    사용 흐름
    1) 데이터 로드
    2) feature engineering
    3) 타겟 생성
    4) XGBoost 학습
    5) 평가 지표 출력
    6) 시각화
    7) 미래 20영업일 예측
    """

    # 1. 데이터 로드
    raw_df = stock_data_joiner.get_modeling_dataset(
        stock_name=stock_name,
        start_date=start_date,
        end_date=end_date,
    )

    if raw_df is None or raw_df.empty:
        raise ValueError(f"{stock_name} 데이터가 비어 있습니다.")

    raw_df = raw_df.sort_values("trade_date").reset_index(drop=True)

    # 2. feature engineering
    builder = ModelingFeatureBuilder()
    feat_df = builder.build(raw_df)

    # 3. target 생성
    selector = FeatureSelectorExtended(base_feature_selector)
    feat_df = selector.create_target(feat_df, horizon=target_horizon)

    # 4. X/y 구성
    X, y = selector.get_features(feat_df, mode="short")

    # 5. 모델 학습
    forecaster = XGBoostStockForecaster(random_state=42)
    result = forecaster.fit(
        df=feat_df,
        X=X,
        y=y,
        test_size=test_size,
    )

    # 6. 평가 출력
    print("\n[평가 결과]")
    for k, v in result.metrics.items():
        print(f"- {k}: {v:.6f}")

    print("\n[상위 중요 피쳐 20개]")
    print(result.feature_importance.head(20).to_string(index=False))

    # 7. 시각화
    forecaster.plot_actual_vs_predicted_return(result)
    forecaster.plot_actual_vs_predicted_price(result)
    forecaster.plot_feature_importance(result, top_n=20)

    # 8. 미래 20영업일 예측
    future_pred_df = forecaster.forecast_next_20_business_days(
        raw_df=raw_df,
        feature_builder=builder,
        feature_selector=selector,
        horizon=20,
    )

    print("\n[향후 20영업일 예측]")
    print(future_pred_df.to_string(index=False))

    # 9. 전체 주가 + 미래 예측 시각화
    forecaster.plot_full_price_forecast(raw_df, future_pred_df, lookback=120)

    return {
        "raw_df": raw_df,
        "feature_df": feat_df,
        "X": X,
        "y": y,
        "result": result,
        "future_pred_df": future_pred_df,
        "forecaster": forecaster,
        "feature_builder": builder,
        "feature_selector": selector,
    }


# ============================================================
# 4. 사용 예시
# ============================================================

if __name__ == "__main__":
    # 아래 두 클래스는 사용자가 이미 가지고 있는 클래스라고 가정
    # from your_module import StockDataJoiner, FeatureSelector

    stock_data_joiner = StockDataJoiner()
    base_feature_selector = FeatureSelector()

    output = run_stock_xgboost_pipeline(
        stock_name="삼성전자",
        stock_data_joiner=stock_data_joiner,
        base_feature_selector=base_feature_selector,
        start_date="2022-01-01",
        end_date=None,
        target_horizon=1,   # 다음날 수익률 예측
        test_size=0.2,
    )
