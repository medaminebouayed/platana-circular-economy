import pandas as pd
import joblib
from pathlib import Path
from datetime import datetime
import sys
import argparse
# Ensure repository root is on PYTHONPATH for absolute imports
repo_root = Path(__file__).resolve().parents[1]
if str(repo_root) not in sys.path:
    sys.path.append(str(repo_root))

# Absolute imports
from models.cv.inference import MultiViewGrader
from models.pricing.model import PricingModel
from models.pricing.features import FeatureEngineer
from models.artifacts import resolve_latest_artifact, resolve_version_artifact
from models.genai.sheet_generator import ProductSheetGenerator

def _resolve_model_artifact(checkpoint_dir, artifact_name, version_id=None, model_path=None,
                            pointer_name="latest.json"):
    if version_id and model_path:
        raise ValueError(f"Choose either a version ID or an explicit path for {artifact_name}, not both.")
    if model_path:
        return Path(model_path), "external-override"
    if version_id:
        return resolve_version_artifact(checkpoint_dir, version_id, artifact_name), version_id
    active_path, active_version = resolve_latest_artifact(checkpoint_dir, artifact_name, pointer_name)
    return active_path or (checkpoint_dir / artifact_name), active_version or "legacy"


class RefurbDecisionEngine:
    def __init__(self, pricing_version_id=None, pricing_model_path=None, pricing_engineer_path=None):
        # Le dossier models/ actuel
        models_dir = Path(__file__).resolve().parent
        
        # Charger le modèle XGBoost et le Feature Engineer
        pricing_dir = models_dir / "pricing" / "checkpoints"
        model_path, version_id = _resolve_model_artifact(
            pricing_dir, "model.pkl", pricing_version_id, pricing_model_path
        )
        feature_engineer_path, engineer_version = _resolve_model_artifact(
            pricing_dir, "feature_engineer.pkl", pricing_version_id, pricing_engineer_path
        )
        if version_id != engineer_version:
            raise RuntimeError("Pricing model and feature engineer must come from the same promoted version.")
        self.pricing_version_id = version_id
        self.pricing_model = PricingModel.load(str(model_path))
        if feature_engineer_path.is_file():
            self.feature_engineer = joblib.load(feature_engineer_path)
        else:
            raise FileNotFoundError(
                f"Feature engineer not found at {feature_engineer_path}. "
                "Run the pricing training script (models/pricing/train.py) to generate it."
            )
        self.sheet_generator = ProductSheetGenerator()
        self.refurb_costs = {
            "screen_crack": 120.0, "cosmetic_scratch": 15.0,
            "back_glass_crack": 40.0, "battery_weak": 30.0, "no_defect": 5.0
        }
        self.min_margin = 30.0 

    def estimate_refurb_cost(self, defects):
        return sum(self.refurb_costs.get(d, 0) for d in defects)

    def predict_resale_price(self, model_name, grade, year):
        """Utilise XGBoost via FeatureEngineer pour prédire le prix."""
        brand = model_name.split()[0]
        
        # Calculer l'age en jours par rapport à aujourd'hui
        age_days = (datetime.now() - datetime(year, 1, 1)).days
        
        # Créer le DataFrame brut attendu par ton FeatureEngineer
        raw_data = pd.DataFrame([{
            "brand": brand,
            "model": model_name,
            "category": "smartphone",
            "grade": grade,
            "original_price": 800, # Valeur par défaut
            "age_days": age_days,
            "date": datetime.now().strftime("%Y-%m-%d")
        }])
        
        # Transformer en features
        features_df = self.feature_engineer.transform(raw_data)
        
        # Sélectionner les colonnes exactes attendues par le modèle
        feature_cols = self.pricing_model.feature_names
        X = features_df[feature_cols]
        
        # Prédire
        predicted_price = self.pricing_model.predict(X)[0]
        return round(predicted_price, 2)

    def make_decision(self, model_name, grade, defects, year):
        market_price = self.predict_resale_price(model_name, grade, year)
        refurb_cost = self.estimate_refurb_cost(defects)
        potential_profit = market_price - refurb_cost
        
        market_price = round(market_price, 2)
        refurb_cost = round(refurb_cost, 2)
        potential_profit = round(potential_profit, 2)
        
        # Orchestrator-aligned 3-tier decision logic
        if potential_profit >= 50.0:
            decision = "RESALE_DIRECT"
            action = f"Revente directe en l'état à {market_price}€"
            product_sheet = None
        elif potential_profit >= 20.0:
            decision = "RECONDITION"
            action = f"Reconditionnement rentable puis vente à {market_price}€"
            
            # --- GÉNÉRATION GenAI ET PDF (Uniquement pour RECONDITION) ---
            print("\n[GénAI] Génération de la fiche produit en cours...")
            product_sheet = self.sheet_generator.generate_sheet_text(
                model_name=model_name,
                grade=grade,
                repaired_defects=defects,
                price=market_price
            )
            
            # Chemin de sauvegarde du PDF
            pdf_path = Path(__file__).resolve().parents[1] / "data" / "output" / f"{model_name.replace(' ', '_')}_grade_{grade}.pdf"
            self.sheet_generator.generate_pdf(product_sheet, pdf_path)
            
            product_sheet["pdf_path"] = str(pdf_path)
            
        else:
            decision = "RECYCLE"
            action = f"Non rentable pour Platana (Profit estimé: {potential_profit}€)"
            product_sheet = None
            
        return {
            "Modèle": model_name, "Année": year, "Grade CV": grade,
            "Défauts CV": defects,
            "Coût Réparation": f"{refurb_cost}€",
            "Prix Prédit (XGBoost)": f"{market_price}€",
            "Profit Potentiel": f"{potential_profit}€",
            "Décision Finale": decision, 
            "Action": action,
            "Fiche Produit GenAI": product_sheet
        }

def main():
    parser = argparse.ArgumentParser(description="Run the local CV + pricing decision pipeline.")
    cv_group = parser.add_mutually_exclusive_group()
    cv_group.add_argument("--cv-version-id", help="Immutable ONNX CV version")
    cv_group.add_argument("--cv-model-path", help="Explicit ONNX CV model path")
    pricing_group = parser.add_mutually_exclusive_group()
    pricing_group.add_argument("--pricing-version-id", help="Immutable pricing version")
    pricing_group.add_argument("--pricing-model-path", help="Explicit pricing model (.pkl) path")
    parser.add_argument("--pricing-engineer-path", help="Feature-engineer .pkl required with --pricing-model-path")
    args = parser.parse_args()
    if bool(args.pricing_model_path) != bool(args.pricing_engineer_path):
        parser.error("--pricing-model-path and --pricing-engineer-path must be supplied together.")
    # models_dir est le dossier où se trouve pipeline.py
    models_dir = Path(__file__).resolve().parent
    # repo_root est le dossier parent (la racine du projet)
    repo_root = models_dir.parent
    
    cv_checkpoint_dir = models_dir / "cv" / "checkpoints"
    model_path, cv_version = _resolve_model_artifact(
        cv_checkpoint_dir, "model.onnx", args.cv_version_id, args.cv_model_path
    )
    
    print("Initialisation du modèle de Vision...")
    grader = MultiViewGrader(str(model_path))
    engine = RefurbDecisionEngine(
        args.pricing_version_id, args.pricing_model_path, args.pricing_engineer_path
    )
    print(f"CV version: {cv_version}; pricing version: {engine.pricing_version_id}")
    
    # Les données sont à la racine du projet
    val_dir = repo_root / "data" / "processed" / "smartphone_grading" / "val"
    user_uploaded_images = [
        str(val_dir / "ds2_good_0000" / "view_00.png"),    
        str(val_dir / "ds2_good_0008" / "view_00.png"), 
        str(val_dir / "ds2_good_0003" / "view_00.png")  
    ]
    
    user_declared_model = "iPhone 13"
    user_declared_year = 2021
    
    print("\nAnalyse des photos en cours...")
    final_grade, detected_defects = grader.predict_defects_and_grade(user_uploaded_images)
    
    # print("\n" + "="*60)
    # print(" RAPPORT DE DÉCISION SYSTÈME (CV + PRICING ML)")
    # print("="*60)
    
    # result = engine.make_decision(user_declared_model, final_grade, detected_defects, user_declared_year)
    
    # for key, value in result.items():
    #     print(f"{key:25}: {value}")
    # print("="*60)
    print("\n" + "="*60)
    print(" RAPPORT DE DÉCISION SYSTÈME (CV + PRICING ML)")
    print("="*60)
    
    result = engine.make_decision(user_declared_model, final_grade, detected_defects, user_declared_year)
    
    for key, value in result.items():
        if key == "Fiche Produit GenAI" and value is not None:
            print(f"\n{'-'*25}")
            print(f"🤖 FICHE PRODUIT GÉNÉRÉE (GenAI) 🤖")
            print(f"Titre : {value.get('title')}")
            print(f"Description : {value.get('description')}")
            print(f"Points Forts : {', '.join(value.get('highlights', []))}")
            print(f"Points d'Attention : {', '.join(value.get('warnings', []))}")
            print(f"📄 PDF sauvegardé à : {value.get('pdf_path')}")
            print(f"{'-'*25}")
        elif key == "Fiche Produit GenAI":
            print(f"{key:25}: Non générée (Produud recyclé)")
        else:
            print(f"{key:25}: {value}")
    print("="*60)

if __name__ == "__main__":
    main()
