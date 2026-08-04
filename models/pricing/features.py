"""
Feature engineering pour le modèle de pricing.
"""

import pandas as pd
import numpy as np
from sklearn.preprocessing import LabelEncoder


class FeatureEngineer:
    """
    Transforme les données brutes en features exploitables par le modèle.
    """
    
    SEASON_MAP = {
        1: "winter", 2: "winter", 3: "spring",
        4: "spring", 5: "spring", 6: "summer",
        7: "summer", 8: "summer", 9: "fall",
        10: "fall", 11: "fall", 12: "winter"
    }
    
    def __init__(self):
        self.label_encoders = {}
        self.fitted = False
    
    def fit(self, df: pd.DataFrame):
        """Fit les encodeurs sur les données d'entraînement."""
        df = df.copy()
        
        # Il faut générer 'season' AVANT de fitter les encodeurs
        if "date" in df.columns:
            df["month"] = pd.to_datetime(df["date"]).dt.month
            df["season"] = df["month"].map(self.SEASON_MAP)
        else:
            df["season"] = "winter" # Défaut si pas de date
            
        categorical = ["grade", "category", "brand", "model", "season"]
        
        for col in categorical:
            if col in df.columns:
                le = LabelEncoder()
                le.fit(df[col].astype(str))
                self.label_encoders[col] = le
        
        self.fitted = True
        return self
    
    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        """Transforme un DataFrame en features."""
        df = df.copy()
        
        # Saisonnalité (doit être fait avant l'encodage)
        if "date" in df.columns:
            df["month"] = pd.to_datetime(df["date"]).dt.month
            df["season"] = df["month"].map(self.SEASON_MAP)
            df["is_holiday_season"] = df["month"].isin([11, 12]).astype(int)
        else:
            df["season"] = "winter"
            df["is_holiday_season"] = 0
        
        # Features catégorielles
        for col, le in self.label_encoders.items():
            if col in df.columns:
                df[f"{col}_encoded"] = df[col].astype(str).apply(
                    lambda x: le.transform([x])[0] if x in le.classes_ else -1
                )
            else:
                # Si la colonne manque au moment de la prédiction
                df[f"{col}_encoded"] = -1
        
        # Features numériques
        if "age_days" in df.columns:
            df["age_months"] = df["age_days"] / 30.44
        else:
            df["age_months"] = 0
            
        if "original_price" in df.columns:
            # Utilise market_avg_price si disponible, sinon estimated_price, sinon 0
            ref_price = df.get("market_avg_price", df.get("estimated_price", 0))
            df["price_ratio"] = ref_price / df["original_price"].clip(lower=1)
        else:
            df["price_ratio"] = 0
        
        # Interactions
        if "grade_encoded" in df.columns and "category_encoded" in df.columns:
            df["grade_x_category"] = df["grade_encoded"] * df["category_encoded"]
        else:
            df["grade_x_category"] = 0
            
        return df
    
    def fit_transform(self, df: pd.DataFrame) -> pd.DataFrame:
        return self.fit(df).transform(df)
    
    def get_feature_names(self) -> list:
        """Retourne la liste des noms de features."""
        return [
            "grade_encoded", "category_encoded", "brand_encoded",
            "model_encoded", "season_encoded", "age_months",
            "price_ratio", "is_holiday_season", "grade_x_category"
        ]