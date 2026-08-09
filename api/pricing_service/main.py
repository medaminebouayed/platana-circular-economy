"""
Platana Pricing Service — Production-ready FastAPI microservice.
Responsible for: ML-based market price prediction for used electronics.
Port: 8002
"""
import os
import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

# ── Config ─────────────────────────────────────────────────────
import sys
sys.path.append(str(Path(__file__).resolve().parents[1]))

env_path = Path(__file__).resolve().parents[2] / '.env'
load_dotenv(dotenv_path=env_path)

from shared.schemas import PricingRequest, PricingResponse

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | pricing_service | %(message)s")
logger = logging.getLogger(__name__)

# ── App ─────────────────────────────────────────────────────────
app = FastAPI(
    title="Platana Pricing Service",
    description="ML-based market price prediction for used electronics.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:4200", "http://localhost", "http://orchestrator:8000", "http://main-service:8003"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Model Loading ───────────────────────────────────────────────
MODEL_PATH = os.getenv("PRICING_MODEL_PATH", str(
    Path(__file__).resolve().parents[2] / "models" / "pricing" / "checkpoints" / "model.pkl"
))
FE_PATH = os.getenv("PRICING_FEATURE_ENGINEER_PATH", str(
    Path(__file__).resolve().parents[2] / "models" / "pricing" / "checkpoints" / "feature_engineer.pkl"
))

model = None
engineer = None

@app.on_event("startup")
async def startup():
    global model, engineer
    try:
        import joblib
        if Path(MODEL_PATH).exists() and Path(FE_PATH).exists():
            from models.pricing.model import PricingModel
            model = PricingModel.load(MODEL_PATH)
            engineer = joblib.load(FE_PATH)
            logger.info("Pricing model loaded from: %s", MODEL_PATH)
        else:
            logger.warning("Pricing model not found. Running in simulation mode.")
    except Exception as e:
        logger.warning("Failed to load pricing model: %s. Simulation mode active.", e)

# ── Health Check ─────────────────────────────────────────────────
@app.get("/health", tags=["health"])
async def health():
    return {"status": "ok", "service": "pricing_service", "model_loaded": model is not None}

# ── Grade-to-ratio mapping (simulation fallback) ─────────────────
_GRADE_RATIOS = {'A': 0.80, 'A+': 0.90, 'B': 0.65, 'C': 0.50, 'D': 0.32}

# ── Endpoints ───────────────────────────────────────────────────
@app.post("/predict", response_model=PricingResponse, tags=["pricing"])
async def predict_price(request: PricingRequest):
    """Predict the resale market price for a product based on grade and characteristics."""

    # Simulation fallback
    if model is None or engineer is None:
        ratio = _GRADE_RATIOS.get(request.grade, 0.5)
        price = round(request.original_price * ratio, 2)
        logger.info("Simulation mode: grade=%s, original=%.2f, predicted=%.2f", request.grade, request.original_price, price)
        return PricingResponse(predicted_price=price, confidence_interval=(round(price * 0.9, 2), round(price * 1.1, 2)))

    try:
        import pandas as pd
        df = pd.DataFrame([{
            "grade": request.grade,
            "category": request.category,
            "brand": request.brand,
            "model": request.model,
            "original_price": request.original_price,
            "age_days": request.age_days,
        }])
        df_features = engineer.transform(df)
        X = df_features[engineer.get_feature_names()]
        price = float(model.predict(X)[0])
        logger.info("Pricing result: grade=%s, predicted=%.2f", request.grade, price)
        return PricingResponse(
            predicted_price=round(price, 2),
            confidence_interval=(round(price * 0.9, 2), round(price * 1.1, 2))
        )
    except Exception as e:
        logger.error("Pricing prediction failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Pricing error: {e}")