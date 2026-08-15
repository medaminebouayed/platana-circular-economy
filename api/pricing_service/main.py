"""
Platana Pricing Service — Production-ready FastAPI microservice.
Responsible for: ML-based market price prediction for used electronics.
Port: 8002
"""
import os
import hmac
import logging
import hashlib
import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Iterable

from fastapi import FastAPI, HTTPException, Header
from dotenv import load_dotenv
import redis.asyncio as redis
from redis.exceptions import RedisError

# ── Config ─────────────────────────────────────────────────────
import sys
sys.path.append(str(Path(__file__).resolve().parents[1]))

env_path = Path(__file__).resolve().parents[2] / '.env'
load_dotenv(dotenv_path=env_path)

from shared.schemas import PricingRequest, PricingResponse
from models.artifacts import resolve_latest_artifact

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | pricing_service | %(message)s")
logger = logging.getLogger(__name__)

# ── App ─────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    global model, engineer, redis_client, cache_fingerprint, active_model_version
    model_path, engineer_path, active_model_version = _resolve_model_paths()
    try:
        import joblib
        if model_path.exists() and engineer_path.exists():
            from models.pricing.model import PricingModel
            model = PricingModel.load(model_path)
            engineer = joblib.load(engineer_path)
            logger.info("Pricing model loaded from version %s: %s", active_model_version, model_path)
        else:
            logger.error("Pricing model not found at %s or %s. Service will answer 503.", model_path, engineer_path)
    except Exception as e:
        logger.error("Failed to load pricing model: %s. Service will answer 503.", e)

    feature_source = Path(__file__).resolve().parents[2] / "models" / "pricing" / "features.py"
    cache_fingerprint = _hash_files([model_path, engineer_path, feature_source])
    logger.info("Pricing cache fingerprint: %s", cache_fingerprint)

    try:
        candidate = redis.from_url(REDIS_URL, encoding="utf-8", decode_responses=True,
                                   socket_connect_timeout=1, socket_timeout=1)
        await candidate.ping()
        redis_client = candidate
        logger.info("Redis pricing cache connected: %s", REDIS_URL)
    except RedisError as exc:
        logger.warning("Redis unavailable; pricing cache disabled: %s", exc)

    yield

    if redis_client is not None:
        await redis_client.aclose()


app = FastAPI(
    title="Platana Pricing Service",
    description="ML-based market price prediction for used electronics.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# ── Model Loading ───────────────────────────────────────────────
CHECKPOINT_DIR = Path(__file__).resolve().parents[2] / "models" / "pricing" / "checkpoints"
LEGACY_MODEL_PATH = CHECKPOINT_DIR / "model.pkl"
LEGACY_ENGINEER_PATH = CHECKPOINT_DIR / "feature_engineer.pkl"
CONFIGURED_MODEL_PATH = os.getenv("PRICING_MODEL_PATH")
CONFIGURED_ENGINEER_PATH = os.getenv("PRICING_FEATURE_ENGINEER_PATH")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
CACHE_TTL_SECONDS = int(os.getenv("PRICING_CACHE_TTL_SECONDS", "3600"))
CACHE_SCHEMA_VERSION = os.getenv("PRICING_CACHE_SCHEMA_VERSION", "v1")
RELOAD_TOKEN = os.getenv("TRAINING_SERVICE_TOKEN", "")

model = None
engineer = None
redis_client: redis.Redis | None = None
cache_fingerprint = "not_loaded"
active_model_version = "not_loaded"


def _resolve_model_paths() -> tuple[Path, Path, str]:
    """Use an explicit deployment override or the atomically promoted version."""
    if CONFIGURED_MODEL_PATH or CONFIGURED_ENGINEER_PATH:
        return (
            Path(CONFIGURED_MODEL_PATH or LEGACY_MODEL_PATH),
            Path(CONFIGURED_ENGINEER_PATH or LEGACY_ENGINEER_PATH),
            "external-override",
        )
    model_path, version_id = resolve_latest_artifact(CHECKPOINT_DIR, "model.pkl")
    engineer_path, engineer_version = resolve_latest_artifact(CHECKPOINT_DIR, "feature_engineer.pkl")
    if model_path and engineer_path and version_id == engineer_version:
        return model_path, engineer_path, version_id
    return LEGACY_MODEL_PATH, LEGACY_ENGINEER_PATH, "legacy"


def _hash_files(paths: Iterable[Path]) -> str:
    """Return a stable fingerprint for model artifacts and pricing logic."""
    digest = hashlib.sha256()
    for path in paths:
        digest.update(str(path.name).encode("utf-8"))
        if not path.is_file():
            digest.update(b"<missing>")
            continue
        with path.open("rb") as artifact:
            for chunk in iter(lambda: artifact.read(1024 * 1024), b""):
                digest.update(chunk)
    return digest.hexdigest()[:20]


def build_pricing_cache_key(request: PricingRequest, fingerprint: str) -> str:
    """Build a deterministic, collision-resistant key for every price input.

    Defect order has no impact on the current feature engineering, so defects
    are sorted while duplicates are retained because they affect defect_count.
    The fingerprint changes when the model, feature engineer, or pricing
    feature code changes, automatically isolating stale values after retraining.
    """
    payload = request.model_dump(mode="json")
    payload["defects"] = sorted(str(defect).strip() for defect in payload.get("defects", []))
    canonical_payload = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    request_digest = hashlib.sha256(canonical_payload.encode("utf-8")).hexdigest()
    return f"platana:pricing:{CACHE_SCHEMA_VERSION}:{fingerprint}:{request_digest}"


async def _get_cached_prediction(key: str) -> PricingResponse | None:
    if redis_client is None:
        return None
    try:
        cached = await redis_client.get(key)
        return PricingResponse.model_validate_json(cached) if cached else None
    except (RedisError, ValueError) as exc:
        logger.warning("Redis cache read failed; continuing without cache: %s", exc)
        return None


async def _cache_prediction(key: str, prediction: PricingResponse) -> None:
    if redis_client is None or CACHE_TTL_SECONDS <= 0:
        return
    try:
        await redis_client.set(key, prediction.model_dump_json(), ex=CACHE_TTL_SECONDS)
    except RedisError as exc:
        logger.warning("Redis cache write failed; continuing without cache: %s", exc)

# ── Health Check ─────────────────────────────────────────────────
@app.get("/health", tags=["health"])
async def health():
    return {
        "status": "ok",
        "service": "pricing_service",
        "model_loaded": model is not None,
        "model_version": active_model_version,
        "redis_cache_connected": redis_client is not None,
        "cache_fingerprint": cache_fingerprint,
    }

@app.post("/internal/reload", tags=["internal"])
async def reload_model(x_training_service_token: str | None = Header(default=None)):
    """Hot-reload the pricing model + feature engineer after a promotion."""
    if not RELOAD_TOKEN or not x_training_service_token or not hmac.compare_digest(x_training_service_token, RELOAD_TOKEN):
        raise HTTPException(status_code=403, detail="Unauthorized reload request")

    global model, engineer, cache_fingerprint, active_model_version
    model_path, engineer_path, active_model_version = _resolve_model_paths()
    try:
        import joblib
        from models.pricing.model import PricingModel
        model = PricingModel.load(model_path)
        engineer = joblib.load(engineer_path)
        feature_source = Path(__file__).resolve().parents[2] / "models" / "pricing" / "features.py"
        cache_fingerprint = _hash_files([model_path, engineer_path, feature_source])
        logger.info("Pricing model hot-reloaded from version %s: %s", active_model_version, model_path)
    except Exception as e:
        model = None
        engineer = None
        cache_fingerprint = "not_loaded"
        logger.error("Failed to reload pricing model %s: %s. Service will answer 503.", model_path, e)
        raise HTTPException(status_code=500, detail=f"Pricing model reload failed: {e}")

    return {"status": "ok", "model_loaded": model is not None, "model_version": active_model_version}

# ── Endpoints ───────────────────────────────────────────────────
@app.post("/predict", response_model=PricingResponse, tags=["pricing"])
async def predict_price(request: PricingRequest):
    """Predict the resale market price for a product based on grade, defects, and characteristics."""

    # No mock/simulation fallback: fail loudly when the model is not loaded.
    if model is None or engineer is None:
        raise HTTPException(
            status_code=503,
            detail="Pricing model is not loaded. Contact the admin or trigger a model reload.",
        )

    cache_key = build_pricing_cache_key(request, cache_fingerprint)
    cached_prediction = await _get_cached_prediction(cache_key)
    if cached_prediction is not None:
        logger.info("Pricing cache hit: fingerprint=%s", cache_fingerprint)
        return cached_prediction

    try:
        import pandas as pd

        # 1. On convertit la liste de défauts en chaîne séparée par des virgules
        defects_str = ",".join(request.defects) if request.defects else "no_defect"
        defect_count = len(request.defects)

        # 2. On crée le DataFrame exactement comme l'attend ton FeatureEngineer
        df = pd.DataFrame([{
            "grade": request.grade,
            "category": request.category,
            "brand": request.brand,
            "model": request.model,
            "original_price": request.original_price,
            "age_days": request.age_days,
            "repair_cost": request.repair_cost,
            "defect_count": defect_count,
            "exact_defects": defects_str  # <-- La colonne qui va être Target Encodée
        }])

        # 3. Transformation et prédiction
        df_features = engineer.transform(df)
        X = df_features[engineer.get_feature_names()]
        price = float(model.predict(X)[0])

        logger.info("Pricing result: grade=%s, defects=%d, predicted=%.2f", request.grade, defect_count, price)

        prediction = PricingResponse(
            predicted_price=round(price, 2),
            confidence_interval=(round(price * 0.9, 2), round(price * 1.1, 2)),
            price_ratio=round(price / request.original_price, 2) if request.original_price else 0.0
        )
        await _cache_prediction(cache_key, prediction)
        return prediction
    except Exception as e:
        logger.error("Pricing prediction failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Pricing error: {e}")
