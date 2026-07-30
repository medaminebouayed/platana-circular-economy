"""
API FastAPI pour le service de pricing.
"""

from contextlib import asynccontextmanager
from pathlib import Path
import os
import sys

import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

sys.path.append(str(Path(__file__).parent.parent.parent))

from models.pricing.model import PricingModel
from models.pricing.features import FeatureEngineer
from api.shared.schemas import PricingRequest, PricingResponse


MODEL_PATH = os.getenv("MODEL_PATH", "models/pricing/checkpoints/model.pkl")
model = None
engineer = None
is_simulated = False


@asynccontextmanager
async def lifespan(app: FastAPI):
    global model, engineer, is_simulated
    
    print(f"[INFO] Recherche du modèle de pricing à {MODEL_PATH}...")
    if not os.path.exists(MODEL_PATH):
        print(f"[WARN] Modèle de pricing absent à {MODEL_PATH}. Activation de la simulation.")
        is_simulated = True
        yield
        return

    try:
        model = PricingModel.load(MODEL_PATH)
        engineer = FeatureEngineer()  # Recréé, les encoders sont dans le modèle
        print("[OK] Modèle de pricing chargé!")
    except Exception as e:
        print(f"[ERROR] Échec du chargement du modèle de pricing : {e}. Activation de la simulation.")
        is_simulated = True

    yield
    print("[INFO] Arrêt du service pricing")


app = FastAPI(title="Platana Pricing Service", version="1.0.0", lifespan=lifespan)

# Enable CORS for frontend interaction
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {"status": "ok", "model_loaded": model is not None, "is_simulated": is_simulated}


@app.post("/predict", response_model=PricingResponse)
async def predict_price(request: PricingRequest):
    """Prédit le prix de revente."""
    
    if is_simulated or model is None:
        # High-fidelity regression simulation matching frontend pricing model
        basePrices = {
            'A': 0.80,
            'B': 0.68,
            'C': 0.52,
            'D': 0.35
        }
        gradeFactor = basePrices.get(request.grade, 0.60)
        
        # Linear aging decay (up to 60%)
        ageLossRatio = min(request.age_days * 0.0004, 0.60)
        
        predicted = request.original_price * gradeFactor * (1 - ageLossRatio)
        
        # Subtract repair cost with overhead factor
        repair_cost = request.repair_cost or 0.0
        predicted = max(predicted - (repair_cost * 1.15), request.original_price * 0.1)

        # Seasonal adjustments
        explanation = f"Estimation de pricing pour {request.brand} {request.model} en grade {request.grade}"
        if request.season == 'summer':
            predicted *= 0.95
            explanation += '. Ajustement de -5% appliqué pour la saison creuse estivale.'
        elif request.season == 'winter':
            predicted *= 1.05
            explanation += '. Ajustement de +5% appliqué pour la période des fêtes hivernales.'
        else:
            explanation += f". Modèle de décote linéaire appliqué pour l'âge de {request.age_days} jours."
            
        explanation += f" Rentabilité estimée après déduction de {repair_cost}€ de frais de remise en état."
        
        predicted = round(predicted, 2)
        interval = (round(predicted * 0.92, 2), round(predicted * 1.08, 2))
        ratio = round(predicted / request.original_price, 2) if request.original_price else 0.0

        return PricingResponse(
            predicted_price=predicted,
            confidence_interval=interval,
            price_ratio=ratio,
            explanation=explanation
        )

    # Real inference
    try:
        # Crée un DataFrame
        df = pd.DataFrame([{
            "grade": request.grade,
            "category": request.category,
            "brand": request.brand,
            "model": request.model,
            "original_price": request.original_price,
            "age_days": request.age_days,
            "repair_cost": request.repair_cost,
            "season": request.season or "unknown"
        }])
        
        # Features
        df_features = engineer.transform(df)
        X = df_features[engineer.get_feature_names()]
        
        # Prédiction
        price = model.predict(X)[0]
        
        # Intervalle de confiance (simplifié ±10%)
        interval = (price * 0.9, price * 1.1)
        
        # Explication
        explanation = (
            f"Prix de {price:.0f}€ estimé pour un {request.brand} {request.model} "
            f"grade {request.grade}, âge {request.age_days} jours."
        )
        
        return PricingResponse(
            predicted_price=round(price, 2),
            confidence_interval=(round(interval[0], 2), round(interval[1], 2)),
            price_ratio=round(price / request.original_price, 2) if request.original_price else 0.0,
            explanation=explanation
        )
    except Exception as e:
        # Fallback to simulated pricing if inference fails
        raise HTTPException(500, f"Erreur interne lors de l'inférence : {e}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)