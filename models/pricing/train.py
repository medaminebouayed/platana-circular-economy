"""
Script d'entraînement du modèle de pricing.
"""

import argparse
import yaml

import pandas as pd
from sklearn.model_selection import train_test_split

from features import FeatureEngineer
from model import PricingModel
import mlflow


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/pricing_config.yaml")
    parser.add_argument("--data", required=True, help="CSV avec les données")
    parser.add_argument("--output", default="models/pricing/checkpoints/model.pkl")
    args = parser.parse_args()
    
    # Config
    with open(args.config, 'r') as f:
        config = yaml.safe_load(f)
    
    # Chargement des données
    print(f"[INFO] Chargement des données: {args.data}")
    df = pd.read_csv(args.data)
    print(f"  {len(df)} échantillons, {len(df.columns)} colonnes")
    
    # Feature engineering
    print("[INFO] Feature engineering...")
    engineer = FeatureEngineer()
    df_features = engineer.fit_transform(df)
    
    feature_cols = engineer.get_feature_names()
    X = df_features[feature_cols]
    y = df["sale_price"]  # Prix de vente réel
    
    # Split
    X_train, X_val, y_train, y_val = train_test_split(
        X, y, test_size=0.2, random_state=42
    )
    print(f"  Train: {len(X_train)}, Val: {len(X_val)}")
    
    # Entraînement
    mlflow.set_experiment(config["paths"]["mlflow_experiment"])
    
    with mlflow.start_run():
        mlflow.log_params(config["model"]["params"])
        
        model = PricingModel(
            model_type=config["model"]["type"],
            params=config["model"]["params"]
        )
        
        print("[INFO] Entraînement...")
        model.fit(X_train, y_train, X_val, y_val)
        
        # Évaluation
        metrics = model.evaluate(X_val, y_val)
        print(f"\n[RESULTATS]")
        print(f"  MAE:  {metrics['mae']:.2f}€")
        print(f"  RMSE: {metrics['rmse']:.2f}€")
        print(f"  MAPE: {metrics['mape']:.2f}%")
        
        mlflow.log_metrics({
            "mae": metrics["mae"],
            "rmse": metrics["rmse"],
            "mape": metrics["mape"]
        })
        
        # Feature importance
        importance = model.get_feature_importance()
        print(f"\n[FEATURE IMPORTANCE]")
        print(importance.head(10).to_string())
        
        # Sauvegarde
        model.save(args.output)
        mlflow.log_artifact(args.output)


if __name__ == "__main__":
    main()