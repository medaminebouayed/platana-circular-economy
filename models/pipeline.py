import pandas as pd
import joblib
from pathlib import Path
from datetime import datetime
import sys
# Ensure repository root is on PYTHONPATH for absolute imports
repo_root = Path(__file__).resolve().parents[1]
if str(repo_root) not in sys.path:
    sys.path.append(str(repo_root))

# Absolute imports
from models.cv.inference import MultiViewGrader
from models.pricing.model import PricingModel
from models.pricing.features import FeatureEngineer
from models.genai.sheet_generator import ProductSheetGenerator

class RefurbDecisionEngine:
    def __init__(self):
        # Le dossier models/ actuel
        models_dir = Path(__file__).resolve().parent
        
        # Charger le modèle XGBoost et le Feature Engineer
        pricing_dir = models_dir / "pricing" / "checkpoints"
        self.pricing_model = PricingModel.load(str(pricing_dir / "model.pkl"))
        feature_engineer_path = pricing_dir / "feature_engineer.pkl"
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
    # models_dir est le dossier où se trouve pipeline.py
    models_dir = Path(__file__).resolve().parent
    # repo_root est le dossier parent (la racine du projet)
    repo_root = models_dir.parent
    
    model_path = models_dir / "cv" / "checkpoints" / "best_multitask_model.onnx"
    
    print("Initialisation du modèle de Vision...")
    grader = MultiViewGrader(str(model_path))
    engine = RefurbDecisionEngine()
    
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
