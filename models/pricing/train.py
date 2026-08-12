"""
Script d'entraînement du modèle de pricing.
"""
import argparse
import yaml
import joblib
import pandas as pd
from sklearn.model_selection import train_test_split
import mlflow
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

repo_root = Path(__file__).resolve().parents[2]
if str(repo_root) not in sys.path:
    sys.path.append(str(repo_root))

from models.pricing.features import FeatureEngineer
from models.pricing.model import PricingModel
from models.artifacts import create_version_dir, promote_version, write_manifest

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/pricing_config.yaml")
    parser.add_argument("--data", required=True, help="CSV avec les données")
    parser.add_argument("--output-dir", default="models/pricing/checkpoints",
                        help="Directory containing immutable version folders and latest.json.")
    args = parser.parse_args()
    
    with open(args.config, 'r') as f:
        config = yaml.safe_load(f)

    load_dotenv(repo_root / ".env")
    tracking_uri = os.getenv("MLFLOW_TRACKING_URI")
    if tracking_uri:
        mlflow.set_tracking_uri(tracking_uri)
    
    print(f"[INFO] Chargement des données: {args.data}")
    df = pd.read_csv(args.data)
    print(f"  {len(df)} échantillons, {len(df.columns)} colonnes")
    
    # --- MODIFICATION ICI : On extrait y AVANT le Feature Engineering ---
    y = df["sale_price"]
    
    print("[INFO] Feature engineering...")
    engineer = FeatureEngineer()
    df_features = engineer.fit_transform(df, y) # On passe y au Feature Engineer !
    
    feature_cols = engineer.get_feature_names()
    X = df_features[feature_cols]
    
    X_train, X_val, y_train, y_val = train_test_split(X, y, test_size=0.2, random_state=42)
    print(f"  Train: {len(X_train)}, Val: {len(X_val)}")
    
    experiment_name = os.getenv("MLFLOW_PRICING_EXPERIMENT", config["paths"]["mlflow_experiment"])
    mlflow.set_experiment(experiment_name)
    
    with mlflow.start_run() as run:
        artifact_root = Path(args.output_dir)
        version_id, version_dir = create_version_dir(artifact_root, "pricing")
        model_params = dict(config["model"]["params"])
        if "early_stopping_rounds" in config.get("training", {}):
            model_params["early_stopping_rounds"] = config["training"]["early_stopping_rounds"]
            
        mlflow.log_params({**model_params, "model_type": config["model"]["type"], "feature_count": len(feature_cols)})
        mlflow.set_tags({
            "pipeline": "pricing",
            "feature_engineering": "target-encoding-defects",
            "local_model_version": version_id,
        })
        
        model = PricingModel(model_type=config["model"]["type"], params=model_params)

        print("[INFO] Entraînement...")
        model.fit(X_train, y_train, X_val, y_val)
        
        metrics = model.evaluate(X_val, y_val)
        print(f"\n[RESULTATS]")
        print(f"  MAE:  {metrics['mae']:.2f}€")
        print(f"  RMSE: {metrics['rmse']:.2f}€")
        print(f"  MAPE: {metrics['mape']:.2f}%")
        
        mlflow.log_metrics({"mae": metrics["mae"], "rmse": metrics["rmse"], "mape": metrics["mape"]})
        
        importance = model.get_feature_importance()
        print(f"\n[FEATURE IMPORTANCE]")
        print(importance.head(10).to_string())
        
        model_output = version_dir / "model.pkl"
        model.save(model_output)
        print("[OK] Feature Engineer sauvegardé!")
        
        engineer_output = model_output.with_name("feature_engineer.pkl")
        joblib.dump(engineer, engineer_output)
        manifest_path = write_manifest(version_dir, {
            "version_id": version_id,
            "model_type": config["model"]["type"],
            "mlflow_run_id": run.info.run_id,
            "metrics": {name: float(metrics[name]) for name in ("mae", "rmse", "mape")},
            "feature_names": feature_cols,
            "artifacts": {"model": "model.pkl", "feature_engineer": "feature_engineer.pkl"},
        })
        promote_version(
            artifact_root, version_id,
            {"model": "model.pkl", "feature_engineer": "feature_engineer.pkl"},
        )
        print(f"[OK] Pricing model version saved: {version_dir}")
        mlflow.log_artifact(str(model_output), artifact_path="model")
        mlflow.log_artifact(str(engineer_output), artifact_path="model")
        mlflow.log_artifact(str(manifest_path), artifact_path="model")
        mlflow.log_artifact(args.config, artifact_path="config")
        mlflow.log_dict({"feature_names": feature_cols, "metrics": {k: float(metrics[k]) for k in ("mae", "rmse", "mape")}}, "training_summary.json")

if __name__ == "__main__":
    main()
