"""
Feature engineering pour le modèle de pricing.
"""
import pandas as pd
import numpy as np
from sklearn.preprocessing import LabelEncoder

class FeatureEngineer:
    LEGACY_FEATURE_NAMES = [
        "grade_encoded", "category_encoded", "brand_encoded",
        "model_encoded", "season_encoded", "age_months", "price_ratio",
        "is_holiday_season", "grade_x_category",
    ]
    DEFECT_AWARE_FEATURE_NAMES = LEGACY_FEATURE_NAMES + [
        "repair_cost", "defect_count", "defect_impact",
    ]

    def __init__(self):
        self.label_encoders = {}
        self.defect_target_map = {}
        self.global_mean_price = 0.0
        self.fitted = False
        
    SEASON_MAP = {
        1: "winter", 2: "winter", 3: "spring", 4: "spring", 5: "spring", 6: "summer",
        7: "summer", 8: "summer", 9: "fall", 10: "fall", 11: "fall", 12: "winter"
    }
    
    def fit(self, df: pd.DataFrame, y: pd.Series):
        """Fit les encodeurs. y (prix de vente) est obligatoire pour le Target Encoding."""
        df = df.copy()
        
        if "date" in df.columns:
            df["month"] = pd.to_datetime(df["date"]).dt.month
            df["season"] = df["month"].map(self.SEASON_MAP)
        else:
            df["season"] = "winter"
            
        categorical = ["grade", "category", "brand", "model", "season"]
        for col in categorical:
            if col in df.columns:
                le = LabelEncoder()
                le.fit(df[col].astype(str))
                self.label_encoders[col] = le
                
        # --- TARGET ENCODING MANUEL POUR LES DÉFAUTS MULTIPLES ---
        self.global_mean_price = y.mean()
        if "exact_defects" in df.columns:
            # 1. On ajoute la colonne de prix au DataFrame AVANT d'exploser
            df["sale_price"] = y.values
            
            # 2. On explode les défauts (le DataFrame va s'agrandir)
            exploded = df.assign(defect=df["exact_defects"].str.split(',')).explode("defect")
            
            # 3. On calcule le prix de vente moyen pour chaque défaut spécifique
            defect_means = exploded.groupby("defect")["sale_price"].mean()
            self.defect_target_map = defect_means.to_dict()
        
        self.fitted = True
        return self
    
    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        
        if "date" in df.columns:
            df["month"] = pd.to_datetime(df["date"]).dt.month
            df["season"] = df["month"].map(self.SEASON_MAP)
            df["is_holiday_season"] = df["month"].isin([11, 12]).astype(int)
        else:
            df["season"] = "winter"
            df["is_holiday_season"] = 0
            
        for col, le in self.label_encoders.items():
            if col in df.columns:
                df[f"{col}_encoded"] = df[col].astype(str).apply(
                    lambda x: le.transform([x])[0] if x in le.classes_ else -1
                )
            else:
                df[f"{col}_encoded"] = -1
                
        if "age_days" in df.columns:
            df["age_months"] = df["age_days"] / 30.44
        else:
            df["age_months"] = 0
            
        if "original_price" in df.columns:
            ref_price = df.get("market_avg_price", df.get("estimated_price", 0))
            df["price_ratio"] = ref_price / df["original_price"].clip(lower=1)
        else:
            df["price_ratio"] = 0
            
        if "grade_encoded" in df.columns and "category_encoded" in df.columns:
            df["grade_x_category"] = df["grade_encoded"] * df["category_encoded"]
        else:
            df["grade_x_category"] = 0

        # Artifacts saved before defect-aware pricing have only the original
        # nine inputs. Do not add a new schema to a model that never saw it.
        if not self.uses_defect_target_encoding():
            return df

        if "repair_cost" not in df.columns:
            df["repair_cost"] = 0.0
        if "defect_count" not in df.columns:
            df["defect_count"] = 0
            
        # --- APPLICATION DU TARGET ENCODING MULTIPLE ---
        if "exact_defects" not in df.columns:
            df["exact_defects"] = "no_defect"
            
        def calculate_impact(defects_str):
            if not isinstance(defects_str, str) or defects_str == "no_defect":
                return self.global_mean_price
            defects = defects_str.split(',')
            # Somme des prix de vente moyens historiques pour chaque défaut
            impacts = [self.defect_target_map.get(d, self.global_mean_price) for d in defects]
            return sum(impacts)
            
        df["defect_impact"] = df["exact_defects"].apply(calculate_impact)
            
        return df
    
    def fit_transform(self, df: pd.DataFrame, y: pd.Series = None) -> pd.DataFrame:
        if y is None:
            raise ValueError("y (target) est requis pour le Target Encoding")
        return self.fit(df, y).transform(df)
    
    def get_feature_names(self) -> list:
        return (
            self.DEFECT_AWARE_FEATURE_NAMES
            if self.uses_defect_target_encoding()
            else self.LEGACY_FEATURE_NAMES
        )

    def uses_defect_target_encoding(self) -> bool:
        """Return whether this persisted artifact uses the defect-aware schema.

        Joblib restores only attributes present when an instance was saved.
        Earlier engineers therefore lack these attributes and must keep their
        original input shape for reproducible inference.
        """
        return hasattr(self, "defect_target_map") and hasattr(self, "global_mean_price")
