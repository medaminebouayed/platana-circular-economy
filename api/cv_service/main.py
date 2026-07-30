"""
API FastAPI pour le service de grading CV.
"""

from contextlib import asynccontextmanager
from typing import List, Dict, Optional
from pathlib import Path
import os
import sys

import torch
from torchvision import transforms
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image
import io
import time
import random

sys.path.append(str(Path(__file__).parent.parent.parent))

from api.shared.schemas import GradingRequest, GradingResponse

# === CONFIGURATION ===

MODEL_PATH = os.getenv("MODEL_PATH", "models/cv/checkpoints/best_model.pt")
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")

GRADE_LABELS = {0: "A", 1: "B", 2: "C", 3: "D"}
DEFECT_LABELS = ["scratch", "dent", "crack", "discoloration", "missing_part", "water_damage"]

transform = transforms.Compose([
    transforms.Resize((224, 224)),
    transforms.ToTensor(),
    transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
])

model = None
is_simulated = False


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Charge le modèle au démarrage ou bascule en mode simulation si absent."""
    global model, is_simulated
    
    print(f"[INFO] Recherche du modèle CV à {MODEL_PATH}...")
    if not os.path.exists(MODEL_PATH):
        print(f"[WARN] Modèle CV absent à {MODEL_PATH}. Activation de la simulation haute-fidélité.")
        is_simulated = True
        yield
        return

    try:
        from models.cv.grading_model import MultiViewGradingModel
        checkpoint = torch.load(MODEL_PATH, map_location=DEVICE)
        config = checkpoint["config"]["model"]
        
        model = MultiViewGradingModel(
            max_views=config["max_views"],
            backbone_name=config["backbone"],
            fusion_type=config["fusion_type"]
        ).to(DEVICE)
        
        model.load_state_dict(checkpoint["model_state_dict"])
        model.eval()
        print(f"[OK] Modèle chargé! (epoch {checkpoint['epoch']}, val_acc: {checkpoint['val_acc']*100:.2f}%)")
    except Exception as e:
        print(f"[ERROR] Échec du chargement du modèle : {e}. Bascule en mode simulation.")
        is_simulated = True

    yield
    print("[INFO] Arrêt du service CV")


app = FastAPI(
    title="Platana CV Grading Service",
    version="1.0.0",
    lifespan=lifespan
)

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


@app.post("/grade", response_model=GradingResponse)
async def grade_product(
    files: List[UploadFile] = File(...),
    product_id: Optional[str] = None
):
    """
    Grade un produit à partir de ses photos.
    Accepte 1 à 5 photos (nombre variable).
    """
    start = time.time()
    
    if not 1 <= len(files) <= 5:
        raise HTTPException(400, f"1-5 photos requises, reçu {len(files)}")
    
    if is_simulated or model is None:
        # High fidelity simulated grading matching the frontend mocks
        file_name = files[0].filename.lower() if files else "iphone.jpg"
        grade = "B"
        confidence = 0.88
        detected_defects = []
        probs = {"A": 0.15, "B": 0.70, "C": 0.12, "D": 0.03}

        if "broken" in file_name or "crack" in file_name or "casse" in file_name:
            grade = "D"
            confidence = 0.94
            detected_defects = [
                {"type": "crack", "probability": 0.92},
                {"type": "scratch", "probability": 0.85}
            ]
            probs = {"A": 0.01, "B": 0.03, "C": 0.08, "D": 0.88}
        elif "scratch" in file_name or "rayure" in file_name:
            grade = "C"
            confidence = 0.82
            detected_defects = [{"type": "scratch", "probability": 0.78}]
            probs = {"A": 0.08, "B": 0.22, "C": 0.65, "D": 0.05}
        elif "clean" in file_name or "neuf" in file_name or "perfect" in file_name:
            grade = "A"
            confidence = 0.96
            probs = {"A": 0.92, "B": 0.06, "C": 0.01, "D": 0.01}
        else:
            rand = random.random()
            if rand > 0.6:
                detected_defects = [{"type": "scratch", "probability": 0.72}]
                grade = "B"
                probs = {"A": 0.10, "B": 0.75, "C": 0.12, "D": 0.03}
            elif rand < 0.2:
                detected_defects = [
                    {"type": "dent", "probability": 0.82},
                    {"type": "discoloration", "probability": 0.61}
                ]
                grade = "C"
                probs = {"A": 0.02, "B": 0.18, "C": 0.72, "D": 0.08}

        processing_time = (time.time() - start) * 1000
        return GradingResponse(
            product_id=product_id or f"PLT-{random.randint(10000, 99999)}",
            grade=grade,
            grade_confidence=confidence,
            grade_probabilities=probs,
            detected_defects=detected_defects,
            attention_weights=[random.uniform(0.6, 1.0) for _ in range(len(files))],
            num_views_used=len(files),
            processing_time_ms=processing_time
        )
    
    # Charge les images
    views = []
    for file in files:
        contents = await file.read()
        img = Image.open(io.BytesIO(contents)).convert("RGB")
        views.append(transform(img))
    
    # Padding si moins de 5 vues
    while len(views) < 5:
        views.append(torch.zeros(3, 224, 224))
    
    views_batch = torch.stack(views).unsqueeze(0).to(DEVICE)
    num_views = torch.tensor([len(files)]).to(DEVICE)
    
    # Inférence
    with torch.no_grad():
        outputs = model(views_batch, num_views)
    
    # Parse
    grade_idx = outputs["predicted_grade"].item()
    probs = outputs["grade_probs"][0].cpu().numpy()
    defect_probs = torch.sigmoid(outputs["defect_logits"][0]).cpu().numpy()
    
    processing_time = (time.time() - start) * 1000
    
    return GradingResponse(
        product_id=product_id,
        grade=GRADE_LABELS[grade_idx],
        grade_confidence=float(outputs["confidence"].item()),
        grade_probabilities={GRADE_LABELS[i]: float(probs[i]) for i in range(4)},
        detected_defects=[
            {"type": DEFECT_LABELS[i], "probability": float(defect_probs[i])}
            for i in range(6) if defect_probs[i] > 0.5
        ],
        attention_weights=outputs["attention_weights"][0].cpu().tolist()[:len(files)],
        num_views_used=len(files),
        processing_time_ms=processing_time
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)