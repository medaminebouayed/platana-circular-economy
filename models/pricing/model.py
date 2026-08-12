"""
Modèle de pricing prédictif avec XGBoost/LightGBM.
"""
from pathlib import Path
from typing import Optional
import numpy as np
import pandas as pd
import xgboost as xgb
import lightgbm as lgb
from sklearn.metrics import mean_absolute_error, mean_squared_error
import joblib

class PricingModel:
    def __init__(self, model_type: str = "xgboost", params: Optional[dict] = None):
        self.model_type = model_type
        self.params = params or self._default_params()
        self.model = None
        self.feature_names = None
    
    def _default_params(self) -> dict:
        if self.model_type == "xgboost":
            return {
                "n_estimators": 1000, "max_depth": 8, "learning_rate": 0.05,
                "subsample": 0.8, "colsample_bytree": 0.8,
                "objective": "reg:squarederror", "eval_metric": "mape",
                "early_stopping_rounds": 50, "random_state": 42
            }
        elif self.model_type == "lightgbm":
            return {
                "n_estimators": 1000, "max_depth": 8, "learning_rate": 0.05,
                "subsample": 0.8, "colsample_bytree": 0.8,
                "objective": "regression", "metric": "mape", "random_state": 42
            }
    
    def fit(self, X: pd.DataFrame, y: pd.Series, X_val: Optional[pd.DataFrame] = None, y_val: Optional[pd.Series] = None):
        self.feature_names = list(X.columns)
        if self.model_type == "xgboost":
            self.model = xgb.XGBRegressor(**self.params)
            eval_set = [(X, y)]
            if X_val is not None: eval_set.append((X_val, y_val))
            self.model.fit(X, y, eval_set=eval_set, verbose=False)
        elif self.model_type == "lightgbm":
            self.model = lgb.LGBMRegressor(**self.params)
            eval_set = [(X, y)]
            if X_val is not None: eval_set.append((X_val, y_val))
            self.model.fit(X, y, eval_set=eval_set, callbacks=[lgb.early_stopping(50), lgb.log_evaluation(0)])
        return self
    
    def predict(self, X: pd.DataFrame) -> np.ndarray:
        return self.model.predict(X)
    
    def evaluate(self, X: pd.DataFrame, y: pd.Series) -> dict:
        preds = self.predict(X)
        mae = mean_absolute_error(y, preds)
        rmse = np.sqrt(mean_squared_error(y, preds))
        mape = np.mean(np.abs((y - preds) / y)) * 100
        return {"mae": mae, "rmse": rmse, "mape": mape, "predictions": preds}
    
    def get_feature_importance(self) -> pd.DataFrame:
        importance = self.model.feature_importances_
        return pd.DataFrame({"feature": self.feature_names, "importance": importance}).sort_values("importance", ascending=False)
    
    def save(self, path: str):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        joblib.dump({"model": self.model, "params": self.params, "feature_names": self.feature_names, "model_type": self.model_type}, path)
    
    @classmethod
    def load(cls, path: str):
        data = joblib.load(path)
        instance = cls(model_type=data["model_type"], params=data["params"])
        instance.model = data["model"]
        instance.feature_names = data["feature_names"]
        return instance