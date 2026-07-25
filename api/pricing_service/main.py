"""
API FastAPI pour le service de pricing.
"""

from contextlib import asynccontextmanager
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, HTTPException

import sys
sys.path.append(str(Path(__file__).parent.parent.parent))

from models.pricing.model import PricingModel
from models.pricing.features import FeatureEngineer
from api.shared.schemas import PricingRequest, PricingResponse


MODEL_PATH = "models/pricing/checkpoints/model.pkl"
model = None
engineer = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global model, engineer
    
    print("[INFO] Chargement du modèle de pricing...")
    model = PricingModel.load(MODEL_PATH)
    engineer = FeatureEngineer()  # Recréé, les encoders sont dans le modèle
    
    print("[OK] Modèle de pricing chargé!")
    yield
    print("[INFO] Arrêt du service pricing")


app = FastAPI(title="Platana Pricing Service", version="1.0.0", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok", "model_loaded": model is not None}


@app.post("/predict", response_model=PricingResponse)
async def predict_price(request: PricingRequest):
    """Prédit le prix de revente."""
    
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
        f"grade {request.grade}, âge {request.age_days} jours"
    )
    
    return PricingResponse(
        predicted_price=round(price, 2),
        confidence_interval=(round(interval[0], 2), round(interval[1], 2)),
        price_ratio=round(price / request.original_price, 2) if request.original_price else 0,
        explanation=explanation
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)