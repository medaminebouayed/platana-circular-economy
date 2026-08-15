"""
Platana CV Service — Production-ready FastAPI microservice.
Responsible for: Visual grading of products from images.
Port: 8001
"""
import hmac
import os
import time
import uuid
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import List

from fastapi import FastAPI, File, UploadFile, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

# ── Config ─────────────────────────────────────────────────────
import sys
sys.path.append(str(Path(__file__).resolve().parents[1]))

env_path = Path(__file__).resolve().parents[2] / '.env'
load_dotenv(dotenv_path=env_path)

from shared.schemas import GradingResponse
from models.artifacts import resolve_latest_artifact

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | cv_service | %(message)s")
logger = logging.getLogger(__name__)

# ── App ─────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    _load_grader()
    yield


app = FastAPI(
    title="Platana CV Service",
    description="AI-powered visual grading service for used electronics.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

DEFAULT_ALLOWED_ORIGINS = [
    "http://localhost:8080",
    "http://127.0.0.1:8080",
    "http://localhost:4200",
    "http://127.0.0.1:4200",
    "http://localhost",
    "http://127.0.0.1",
    "http://orchestrator:8000",
    "http://main-service:8003",
    "http://cv-service:8001",
]
env_origins = os.getenv("ALLOWED_ORIGINS")
allowed_origins = [o.strip() for o in env_origins.split(",") if o.strip()] if env_origins else DEFAULT_ALLOWED_ORIGINS

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Model Loading ───────────────────────────────────────────────
CHECKPOINT_DIR = Path(__file__).resolve().parents[2] / "models" / "cv" / "checkpoints"
LEGACY_MODEL_PATH = CHECKPOINT_DIR / "best_multitask_model.onnx"
CONFIGURED_MODEL_PATH = os.getenv("CV_MODEL_PATH")
RELOAD_TOKEN = os.getenv("TRAINING_SERVICE_TOKEN", "")
grader = None
active_model_version = "not_loaded"


def _resolve_model_path() -> tuple[Path, str]:
    if CONFIGURED_MODEL_PATH:
        return Path(CONFIGURED_MODEL_PATH), "external-override"
    model_path, version_id = resolve_latest_artifact(CHECKPOINT_DIR, "model.onnx")
    return (model_path, version_id) if model_path else (LEGACY_MODEL_PATH, "legacy")


def _load_grader() -> None:
    global grader, active_model_version
    model_path, active_model_version = _resolve_model_path()
    if model_path.exists():
        try:
            from models.cv.inference import MultiViewGrader
            grader = MultiViewGrader(str(model_path))
            logger.info("CV model loaded from version %s: %s", active_model_version, model_path)
        except Exception as e:
            grader = None
            logger.error("Failed to load CV model %s: %s", model_path, e)
    else:
        grader = None
        logger.error("CV model not found at %s", model_path)

# ── Health Check ─────────────────────────────────────────────────
@app.get("/health", tags=["health"])
async def health():
    return {"status": "ok", "service": "cv_service", "model_loaded": grader is not None,
            "model_version": active_model_version}

@app.post("/internal/reload", tags=["internal"])
async def reload_model(x_training_service_token: str | None = Header(default=None)):
    """Hot-reload ONNX model after continuous training promotes a new version."""
    if not RELOAD_TOKEN or not x_training_service_token or not hmac.compare_digest(x_training_service_token, RELOAD_TOKEN):
        raise HTTPException(status_code=403, detail="Unauthorized reload request")
    _load_grader()
    return {"status": "ok", "model_loaded": grader is not None, "model_version": active_model_version}

# ── Endpoints ───────────────────────────────────────────────────
@app.post("/grade", response_model=GradingResponse, tags=["grading"])
async def grade_product(files: List[UploadFile] = File(...)):
    """Grade a product from 1-5 images. Returns grade (A-D) and detected defects."""
    start = time.time()

    if not 1 <= len(files) <= 5:
        raise HTTPException(status_code=400, detail="1 to 5 images are required.")

    # No mock/simulation fallback: fail loudly when the model is not loaded.
    if grader is None:
        raise HTTPException(
            status_code=503,
            detail="CV model is not loaded. Contact the admin or trigger a model reload.",
        )

    # Save files temporarily with unique names
    temp_dir = Path("temp_uploads")
    temp_dir.mkdir(exist_ok=True)
    temp_paths = []

    try:
        for f in files:
            file_ext = Path(f.filename).suffix if f.filename else ".jpg"
            temp_path = temp_dir / f"{uuid.uuid4().hex}{file_ext}"
            with open(temp_path, "wb") as out:
                out.write(await f.read())
            temp_paths.append(str(temp_path))

        grade, defects = grader.predict_defects_and_grade(temp_paths)
        logger.info("Grade result: %s | defects: %s | took %.2fs", grade, defects, time.time() - start)

        return GradingResponse(grade=grade, grade_confidence=1.0, detected_defects=defects)

    except Exception as e:
        logger.error("Grading failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Grading error: {e}")

    finally:
        for p in temp_paths:
            try:
                os.remove(p)
            except OSError:
                pass
