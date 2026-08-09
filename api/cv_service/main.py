"""
Platana CV Service — Production-ready FastAPI microservice.
Responsible for: Visual grading of products from images.
Port: 8001
"""
import os
import time
import uuid
import logging
from pathlib import Path
from typing import List

from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

# ── Config ─────────────────────────────────────────────────────
import sys
sys.path.append(str(Path(__file__).resolve().parents[1]))

env_path = Path(__file__).resolve().parents[2] / '.env'
load_dotenv(dotenv_path=env_path)

from shared.schemas import GradingResponse

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | cv_service | %(message)s")
logger = logging.getLogger(__name__)

# ── App ─────────────────────────────────────────────────────────
app = FastAPI(
    title="Platana CV Service",
    description="AI-powered visual grading service for used electronics.",
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
MODEL_PATH = os.getenv(
    "CV_MODEL_PATH",
    str(Path(__file__).resolve().parents[2] / "models" / "cv" / "checkpoints" / "best_multitask_model.pth")
)
grader = None

@app.on_event("startup")
async def startup():
    global grader
    if Path(MODEL_PATH).exists():
        try:
            from models.cv.inference import MultiViewGrader
            grader = MultiViewGrader(MODEL_PATH)
            logger.info("CV Model loaded from: %s", MODEL_PATH)
        except Exception as e:
            logger.warning("Failed to load CV model: %s. Running in simulation mode.", e)
    else:
        logger.warning("CV Model not found at %s. Running in simulation mode.", MODEL_PATH)

# ── Health Check ─────────────────────────────────────────────────
@app.get("/health", tags=["health"])
async def health():
    return {"status": "ok", "service": "cv_service", "model_loaded": grader is not None}

# ── Endpoints ───────────────────────────────────────────────────
@app.post("/grade", response_model=GradingResponse, tags=["grading"])
async def grade_product(files: List[UploadFile] = File(...)):
    """Grade a product from 1-5 images. Returns grade (A-D) and detected defects."""
    start = time.time()

    if not 1 <= len(files) <= 5:
        raise HTTPException(status_code=400, detail="1 to 5 images are required.")

    # Simulation mode when model is not available
    if grader is None:
        logger.info("Simulation mode: returning mock grading result.")
        return GradingResponse(grade="B", grade_confidence=0.85, detected_defects=["cosmetic_scratch"])

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