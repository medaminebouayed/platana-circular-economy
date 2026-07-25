"""
API FastAPI pour le service de grading CV.
"""

from contextlib import asynccontextmanager
from typing import List

import torch
from torchvision import transforms
from fastapi import FastAPI, File, UploadFile, HTTPException
from PIL import Image
import io
import time

import sys
sys.path.append(str(Path(__file__).parent.parent.parent))

from models.cv.grading_model import MultiViewGradingModel
from api.shared.schemas import GradingRequest, GradingResponse


# === CONFIGURATION ===

MODEL_PATH = "models/cv/checkpoints/best_model.pt"
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")

GRADE_LABELS = {0: "A", 1: "B", 2: "C", 3: "D"}
DEFECT_LABELS = ["scratch", "dent", "crack", "discoloration", "missing_part", "water_damage"]

transform = transforms.Compose([
    transforms.Resize((224, 224)),
    transforms.ToTensor(),
    transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
])

model = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Charge le modèle au démarrage."""
    global model
    
    print("[INFO] Chargement du modèle CV...")
    checkpoint = torch.load(MODEL_PATH, map_location=DEVICE)
    config = checkpoint["config"]["model"]
    
    model = MultiViewGradingModel(
        max_views=config["max_views"],
        backbone_name=config["backbone"],
        fusion_type=config["fusion_type"]
    ).to(DEVICE)
    
    model.load_state_dict(checkpoint["model_state_dict"])
    model.eval()
    
    print(f"[OK] Modèle chargé! (epoch {checkpoint['epoch']}, "
          f"val_acc: {checkpoint['val_acc']*100:.2f}%)")
    
    yield
    
    print("[INFO] Arrêt du service CV")


app = FastAPI(
    title="Platana CV Grading Service",
    version="1.0.0",
    lifespan=lifespan
)


@app.get("/health")
async def health():
    return {"status": "ok", "model_loaded": model is not None}


@app.post("/grade", response_model=GradingResponse)
async def grade_product(
    files: List[UploadFile] = File(...),
    product_id: str = None
):
    """
    Grade un produit à partir de ses photos.
    Accepte 1 à 5 photos (nombre variable).
    """
    start = time.time()
    
    if not 1 <= len(files) <= 5:
        raise HTTPException(400, f"1-5 photos requises, reçu {len(files)}")
    
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
        attention_weights=outputs["attention_weights"][0].cpu().tolist(),
        num_views_used=len(files),
        processing_time_ms=processing_time
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)