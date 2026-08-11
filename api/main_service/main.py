"""
Platana Main Service — Production-ready FastAPI microservice.
Responsible for: Authentication, product management, Dify AI integration, admin review, publication.
Port: 8003
"""
import os
import uuid
import shutil
import hashlib
import logging
from pathlib import Path
from typing import List, Optional
from datetime import datetime, timedelta
import json

import jwt
import httpx
from bson import ObjectId
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from passlib.context import CryptContext
from pydantic import BaseModel, ValidationError
from dotenv import load_dotenv

# ── Config ─────────────────────────────────────────────────────
import sys
sys.path.append(str(Path(__file__).resolve().parents[1]))

env_path = Path(__file__).resolve().parents[2] / '.env'
load_dotenv(dotenv_path=env_path)

from database.database import products_collection, users_collection, workshops_collection
from shared.models import AIPredictions, AdminReview, ModelDrift

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | main_service | %(message)s")
logger = logging.getLogger(__name__)

# ── Dify Config ─────────────────────────────────────────────────
DIFY_API_URL = os.getenv("DIFY_API_URL", "http://host.docker.internal:80/v1")
DIFY_EVAL_API_KEY = os.getenv("DIFY_EVAL_API_KEY")
DIFY_PUBLISH_API_KEY = os.getenv("DIFY_PUBLISH_API_KEY")
DIFY_USER = "platana-backend"

# ── App ─────────────────────────────────────────────────────────
app = FastAPI(
    title="Platana Main Service",
    description="Core API: authentication, product lifecycle management, Dify orchestration, and admin review.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

UPLOAD_DIR = Path("data/uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# ── JWT Config ──────────────────────────────────────────────────
JWT_SECRET = os.getenv("JWT_SECRET", "platana-super-secret-change-in-production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_HOURS = {"USER": 8, "ADMIN": 12}

# ── Schemas ──────────────────────────────────────────────────────
class LoginRequest(BaseModel):
    email: str
    password: str
    role: str

class RegisterRequest(BaseModel):
    email: str
    password: str
    name: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    expires_in: int
    email: str
    role: str
    name: str
    avatar: str
    roleLabel: str

# ── Password Hashing ─────────────────────────────────────────────
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password_sha256(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain: str, stored: str) -> bool:
    try:
        if pwd_context.verify(plain, stored):
            return True
    except Exception:
        pass
    return hash_password_sha256(plain) == stored

# ── JWT Helpers ──────────────────────────────────────────────────
bearerScheme = HTTPBearer()

def create_token(payload: dict, role: str) -> str:
    expiry_hours = JWT_EXPIRY_HOURS.get(role, 8)
    to_encode = payload.copy()
    to_encode["exp"] = datetime.utcnow() + timedelta(hours=expiry_hours)
    to_encode["iat"] = datetime.utcnow()
    return jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)

def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(bearerScheme)) -> dict:
    return decode_token(credentials.credentials)

# ── Startup Seed ─────────────────────────────────────────────────
@app.on_event("startup")
async def startup_event():
    count = await users_collection.count_documents({})
    if count == 0:
        logger.info("Seeding default admin and user accounts...")
        await users_collection.insert_many([
            {
                "email": "thomas.dubois@platana.fr",
                "password": hash_password("admin"),
                "role": "ADMIN",
                "name": "Thomas Dubois",
                "avatar": "https://api.dicebear.com/7.x/initials/svg?seed=Thomas",
                "roleLabel": "Administrateur",
                "created_at": datetime.utcnow(),
            },
            {
                "email": "user@example.com",
                "password": hash_password("user"),
                "role": "USER",
                "name": "Utilisateur Test",
                "avatar": "https://api.dicebear.com/7.x/initials/svg?seed=User",
                "roleLabel": "Vendeur",
                "created_at": datetime.utcnow(),
            },
        ])
        logger.info("Default accounts seeded.")

# ── Health Check ─────────────────────────────────────────────────
@app.get("/health", tags=["health"])
async def health():
    return {
        "status": "ok",
        "service": "main_service",
        "dify_url": DIFY_API_URL,
        "dify_key_configured": bool(DIFY_EVAL_API_KEY),
    }

@app.on_event("shutdown")
async def shutdown_event():
    from database.database import client
    if client:
        client.close()
        logger.info("MongoDB connection closed.")

# ══════════════════════════════════════════════════════════════════
# AUTH
# ══════════════════════════════════════════════════════════════════
@app.post("/api/auth/login", response_model=TokenResponse, tags=["auth"])
async def login(req: LoginRequest):
    user = await users_collection.find_one({"email": req.email, "role": req.role})
    if not user or not verify_password(req.password, user.get("password", "")):
        raise HTTPException(status_code=401, detail="Identifiants invalides")
    expiry_hours = JWT_EXPIRY_HOURS.get(req.role, 8)
    token = create_token({"sub": user["email"], "role": user["role"], "name": user["name"]}, req.role)
    logger.info("User logged in: %s (%s)", req.email, req.role)
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in=expiry_hours * 3600,
        email=user["email"],
        role=user["role"],
        name=user["name"],
        avatar=user["avatar"],
        roleLabel=user["roleLabel"],
    )

@app.post("/api/auth/register", response_model=TokenResponse, tags=["auth"])
async def register(req: RegisterRequest):
    if await users_collection.find_one({"email": req.email}):
        raise HTTPException(status_code=400, detail="L'utilisateur existe déjà")
    new_user = {
        "email": req.email,
        "password": hash_password(req.password),
        "role": "USER",
        "name": req.name,
        "avatar": f"https://api.dicebear.com/7.x/initials/svg?seed={req.name}",
        "roleLabel": "Vendeur",
        "created_at": datetime.utcnow(),
    }
    await users_collection.insert_one(new_user)
    token = create_token({"sub": req.email, "role": "USER", "name": req.name}, "USER")
    logger.info("New user registered: %s", req.email)
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in=JWT_EXPIRY_HOURS["USER"] * 3600,
        email=new_user["email"],
        role=new_user["role"],
        name=new_user["name"],
        avatar=new_user["avatar"],
        roleLabel=new_user["roleLabel"],
    )

@app.get("/api/auth/verify", tags=["auth"])
async def verify_token(current_user: dict = Depends(get_current_user)):
    return {"valid": True, "user": current_user}

@app.get("/api/auth/me", tags=["auth"])
async def get_me(current_user: dict = Depends(get_current_user)):
    user = await users_collection.find_one({"email": current_user["sub"]})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {
        "email": user["email"],
        "name": user["name"],
        "role": user["role"],
        "avatar": user.get("avatar", ""),
        "roleLabel": user.get("roleLabel", ""),
        "preferences": user.get("preferences", {}),
    }

class UserPreferences(BaseModel):
    isDarkTheme: Optional[bool] = False
    notificationsEnabled: Optional[bool] = True
    emailNotifs: Optional[bool] = True
    language: Optional[str] = "fr"
    autoRefreshQueue: Optional[bool] = True
    gradeDriftAlert: Optional[bool] = True
    driftThreshold: Optional[int] = 15

@app.put("/api/auth/preferences", tags=["auth"])
async def update_preferences(prefs: UserPreferences, current_user: dict = Depends(get_current_user)):
    user = await users_collection.find_one({"email": current_user["sub"]})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    await users_collection.update_one(
        {"email": current_user["sub"]},
        {"$set": {"preferences": prefs.dict()}}
    )
    return {"status": "success", "preferences": prefs.dict()}

class UpdateProfileRequest(BaseModel):
    name: str

class UpdatePasswordRequest(BaseModel):
    current_password: str
    new_password: str

@app.put("/api/auth/profile", tags=["auth"])
async def update_profile(req: UpdateProfileRequest, current_user: dict = Depends(get_current_user)):
    user = await users_collection.find_one({"email": current_user["sub"]})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    new_avatar = f"https://api.dicebear.com/7.x/initials/svg?seed={req.name}"
    await users_collection.update_one(
        {"email": current_user["sub"]},
        {"$set": {"name": req.name, "avatar": new_avatar}}
    )
    role = user["role"]
    expiry_hours = JWT_EXPIRY_HOURS.get(role, 8)
    new_token = create_token({"sub": user["email"], "role": role, "name": req.name}, role)
    logger.info("Profile updated for %s → name=%s", current_user["sub"], req.name)
    return TokenResponse(
        access_token=new_token,
        token_type="bearer",
        expires_in=expiry_hours * 3600,
        email=user["email"],
        role=role,
        name=req.name,
        avatar=new_avatar,
        roleLabel=user.get("roleLabel", ""),
    )

@app.put("/api/auth/password", tags=["auth"])
async def change_password(req: UpdatePasswordRequest, current_user: dict = Depends(get_current_user)):
    user = await users_collection.find_one({"email": current_user["sub"]})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if not verify_password(req.current_password, user.get("password", "")):
        raise HTTPException(status_code=400, detail="Mot de passe actuel incorrect")
    if len(req.new_password) < 6:
        raise HTTPException(status_code=400, detail="Le nouveau mot de passe doit contenir au moins 6 caractères")
    await users_collection.update_one(
        {"email": current_user["sub"]},
        {"$set": {"password": hash_password(req.new_password)}}
    )
    logger.info("Password changed for %s", current_user["sub"])
    return {"status": "success", "message": "Mot de passe mis à jour avec succès"}

# ══════════════════════════════════════════════════════════════════
# PRODUCTS
# ══════════════════════════════════════════════════════════════════
def _serialize(p: dict) -> dict:
    p["id"] = str(p.pop("_id"))
    if p.get("status") == "REVIEW_READY":
        p["status"] = "PENDING_ADMIN_REVIEW"
    return p

@app.get("/api/products/pending", tags=["products"])
async def get_pending_products():
    cursor = products_collection.find({"status": {"$in": ["REVIEW_READY", "PENDING_EVALUATION", "PENDING_ADMIN_REVIEW"]}})
    products = await cursor.to_list(length=200)
    return [_serialize(p) for p in products]

@app.get("/api/products", tags=["products"])
async def get_all_products():
    cursor = products_collection.find()
    products = await cursor.to_list(length=200)
    return [_serialize(p) for p in products]

@app.get("/api/products/user/{email}", tags=["products"])
async def get_user_products(email: str):
    cursor = products_collection.find({"user_email": email}).sort("created_at", -1)
    products = await cursor.to_list(length=200)
    return [_serialize(p) for p in products]

# ══════════════════════════════════════════════════════════════════
# UPLOAD & AI EVALUATION (via Dify)
# ══════════════════════════════════════════════════════════════════
def _extract_dify_outputs(raw: dict) -> dict:
    """Extracts and parses the outputs from Dify response."""
    logger.debug(f"[DIFY RAW RESPONSE] {raw}")
    if "body_reject" in raw and isinstance(raw["body_reject"], str):
        return json.loads(raw["body_reject"])
    elif "body" in raw and isinstance(raw["body"], str):
        return json.loads(raw["body"])
    elif "data" in raw and "outputs" in raw.get("data", {}):
        return raw["data"]["outputs"]
    return raw

@app.post("/api/products/upload", tags=["products"])
async def upload_and_evaluate(
    brand: str = Form(...),
    model: str = Form(...),
    year: int = Form(...),
    original_price: float = Form(...),
    user_email: str = Form("anonymous@platana.fr"),
    files: List[UploadFile] = File(...)
):
    saved_image_paths = []
    for f in files:
        ext = Path(f.filename).suffix if f.filename else ".jpg"
        path = UPLOAD_DIR / f"{uuid.uuid4().hex}{ext}"
        with open(path, "wb") as buf:
            shutil.copyfileobj(f.file, buf)
        saved_image_paths.append(str(path))

    doc = {
        "brand": brand, "model": model, "year": year,
        "original_price": original_price,
        "image_paths": saved_image_paths,
        "status": "PENDING_EVALUATION",
        "user_email": user_email,
        "created_at": datetime.utcnow(),
    }
    result = await products_collection.insert_one(doc)
    product_id = str(result.inserted_id)
    logger.info("Product inserted: id=%s, user=%s", product_id, user_email)

    from dify.dify_client import upload_file_to_dify, run_eval_workflow
    try:
        dify_file_ids = []
        for path in saved_image_paths:
            file_id = await upload_file_to_dify(path, Path(path).name)
            dify_file_ids.append(file_id)

        ai_outputs_raw = await run_eval_workflow(brand, model, year, original_price, dify_file_ids)
        ai_outputs = _extract_dify_outputs(ai_outputs_raw)
        
        logger.info(f"[DIFY PARSED OUTPUTS] {ai_outputs}")
        
        if not ai_outputs or "grade" not in ai_outputs:
            logger.error(f"Dify returned empty or invalid outputs: {ai_outputs_raw}")
            raise HTTPException(status_code=502, detail="Dify evaluation failed: No valid AI predictions returned. Check Dify workflow logs.")

        ai_predictions = AIPredictions(**ai_outputs)
        logger.info("Dify evaluation complete for product %s: grade=%s", product_id, ai_predictions.grade)

    except httpx.HTTPStatusError as e:
        logger.error("Dify HTTP error for product %s: %s - %s", product_id, e, e.response.text)
        await products_collection.update_one(
            {"_id": result.inserted_id},
            {"$set": {"status": "AI_ERROR", "error_detail": f"HTTP {e.response.status_code}: {e.response.text}"}},
        )
        raise HTTPException(
            status_code=502,
            detail=f"Dify AI workflow failed. Product saved (id: {product_id}) but eval failed. Error: {e.response.text}"
        )
    except (ValidationError, json.JSONDecodeError) as e:
        logger.error("Pydantic/JSON Error for product %s: %s", product_id, e)
        await products_collection.update_one(
            {"_id": result.inserted_id},
            {"$set": {"status": "AI_ERROR", "error_detail": str(e)}},
        )
        raise HTTPException(
            status_code=502,
            detail=f"Dify AI workflow failed. Product saved (id: {product_id}) but eval failed. Error: {str(e)}"
        )
    except Exception as e:
        logger.error("Dify evaluation failed for product %s: %s", product_id, e)
        await products_collection.update_one(
            {"_id": result.inserted_id},
            {"$set": {"status": "AI_ERROR", "error_detail": str(e)}},
        )
        raise HTTPException(
            status_code=502,
            detail=f"Dify AI workflow failed. Product saved (id: {product_id}) but eval failed. Error: {str(e)}"
        )

    await products_collection.update_one(
        {"_id": result.inserted_id},
        {"$set": {"status": "REVIEW_READY", "ai_predictions": ai_predictions.dict()}},
    )

    return {
        "product_id": product_id,
        "status": "REVIEW_READY",
        "ai_predictions": ai_predictions.dict(),
    }

# ══════════════════════════════════════════════════════════════════
# ADMIN REVIEW & REJECTION / RE-EVALUATION
# ══════════════════════════════════════════════════════════════════
@app.patch("/api/products/{product_id}/review", tags=["admin"])
async def review_product(product_id: str, review: AdminReview):
    try:
        oid = ObjectId(product_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid product ID")

    product = await products_collection.find_one({"_id": oid})
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    ai_pred = product.get("ai_predictions")
    model_drift = None
    if ai_pred:
        drift = ModelDrift(
            pricing_error_eur=round(review.market_price - ai_pred["market_price"], 2),
            grade_changed=ai_pred["grade"] != review.grade,
            defects_changed=set(ai_pred.get("defects", [])) != set(review.defects),
        )
        model_drift = drift.dict()

    await products_collection.update_one(
        {"_id": oid},
        {"$set": {
            "status": "REVIEWED",
            "admin_review": review.dict(),
            "model_drift": model_drift,
            "reviewed_at": datetime.utcnow(),
        }},
    )
    logger.info("Product %s reviewed by %s", product_id, review.reviewed_by)
    return {"status": "REVIEWED", "message": "Review saved successfully."}

class RejectRequest(BaseModel):
    reason: Optional[str] = "Rejeté par l'administrateur"
    rejected_by: Optional[str] = "admin"

@app.post("/api/products/{product_id}/reject", tags=["admin"])
async def reject_product(product_id: str, req: Optional[RejectRequest] = None):
    try:
        oid = ObjectId(product_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid product ID")

    product = await products_collection.find_one({"_id": oid})
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    reason = req.reason if req else "Rejeté par l'administrateur"
    rejected_by = req.rejected_by if req else "admin"

    await products_collection.update_one(
        {"_id": oid},
        {"$set": {
            "status": "REJECTED",
            "rejection_reason": reason,
            "rejected_by": rejected_by,
            "rejected_at": datetime.utcnow()
        }}
    )
    logger.info("Product %s rejected by %s", product_id, rejected_by)
    return {"status": "REJECTED", "message": "Produit rejeté avec succès."}

@app.post("/api/products/{product_id}/re-evaluate", tags=["admin"])
async def re_evaluate_product(product_id: str):
    try:
        oid = ObjectId(product_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid product ID")

    product = await products_collection.find_one({"_id": oid})
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    saved_image_paths = product.get("image_paths", [])
    brand = product.get("brand", "")
    model = product.get("model", "")
    year = product.get("year", 2023)
    original_price = product.get("original_price", 0.0)

    from dify.dify_client import upload_file_to_dify, run_eval_workflow
    try:
        dify_file_ids = []
        for path in saved_image_paths:
            file_id = await upload_file_to_dify(path, Path(path).name)
            dify_file_ids.append(file_id)

        ai_outputs_raw = await run_eval_workflow(brand, model, year, original_price, dify_file_ids)
        ai_outputs = _extract_dify_outputs(ai_outputs_raw)
        
        if not ai_outputs or "grade" not in ai_outputs:
            logger.error(f"Re-evaluation failed. Dify returned empty or invalid outputs: {ai_outputs_raw}")
            raise HTTPException(status_code=502, detail="Ré-évaluation échouée: Dify n'a pas renvoyé de prédictions valides.")

        ai_predictions = AIPredictions(**ai_outputs)

        await products_collection.update_one(
            {"_id": oid},
            {"$set": {
                "status": "REVIEW_READY",
                "ai_predictions": ai_predictions.dict(),
                "admin_review": None,
                "updated_at": datetime.utcnow()
            }}
        )
        return {"status": "REVIEW_READY", "ai_predictions": ai_predictions.dict(), "message": "Ré-évaluation effectuée avec succès."}
    except Exception as e:
        logger.error("Re-evaluation failed for %s: %s", product_id, e)
        raise HTTPException(status_code=502, detail=f"Échec de la ré-évaluation: {str(e)}")

# ══════════════════════════════════════════════════════════════════
# PUBLICATION VIA DIFY
# ══════════════════════════════════════════════════════════════════
@app.post("/api/products/{product_id}/publish", tags=["admin"])
async def publish_product(product_id: str):
    try:
        oid = ObjectId(product_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid product ID")

    product = await products_collection.find_one({"_id": oid})
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    admin_data = product.get("admin_review") or product.get("ai_predictions")
    if not admin_data:
        raise HTTPException(status_code=400, detail="Product has no evaluation or review data.")

    try:
        from dify.dify_client import run_publish_workflow
        outputs_raw = await run_publish_workflow(
            title=admin_data["title"],
            description=admin_data["description"],
            price=admin_data.get("market_price", 0.0),
            grade=admin_data["grade"]
        )
        outputs = _extract_dify_outputs(outputs_raw)
        
        logger.info(f"[DIFY PUBLISH OUTPUTS] {outputs}")
        
        shopify_url = outputs.get("listing_url")
        if not shopify_url:
            logger.error(f"Dify publish workflow did not return a listing_url. Outputs: {outputs}")
            raise HTTPException(status_code=502, detail="Publish workflow succeeded but no listing_url was returned.")

    except Exception as e:
        logger.error("Dify publish workflow failed for product %s: %s", product_id, e)
        await products_collection.update_one({"_id": oid}, {"$set": {"status": "PUBLISH_ERROR"}})
        raise HTTPException(status_code=502, detail=f"Publish workflow failed: {str(e)}")

    await products_collection.update_one(
        {"_id": oid},
        {"$set": {"status": "PUBLISHED", "shopify_url": shopify_url, "published_at": datetime.utcnow()}},
    )
    logger.info("Product %s published: %s", product_id, shopify_url)
    return {"status": "PUBLISHED", "shopify_url": shopify_url}


# ── Dashboard & Logistics APIs ───────────────────────────────────

DEFAULT_WORKSHOPS = [
    {
        "name": "Atelier Platana Nord", "city": "Lille", "region": "Hauts-de-France",
        "capacity": 200, "occupancy": 62, "avg_cost": 48.0, "distance": 230,
        "specialties": ["Smartphone", "Ordinateur", "Tablette"],
        "status": "available", "min_profit_threshold": 20.0, "max_items_per_batch": 10
    },
    {
        "name": "Centre Reconditionnement Est", "city": "Strasbourg", "region": "Grand Est",
        "capacity": 350, "occupancy": 87, "avg_cost": 52.0, "distance": 490,
        "specialties": ["TV", "Electroménager", "Outillage"],
        "status": "busy", "min_profit_threshold": 30.0, "max_items_per_batch": 15
    },
    {
        "name": "Hub Reconditionnement Sud", "city": "Lyon", "region": "Auvergne-Rhône-Alpes",
        "capacity": 280, "occupancy": 45, "avg_cost": 44.0, "distance": 460,
        "specialties": ["Smartphone", "Audio", "Console de jeux"],
        "status": "available", "min_profit_threshold": 20.0, "max_items_per_batch": 12
    },
    {
        "name": "Site Atlantique", "city": "Nantes", "region": "Pays de la Loire",
        "capacity": 180, "occupancy": 95, "avg_cost": 58.0, "distance": 380,
        "specialties": ["Aspirateur", "Electroménager"],
        "status": "full", "min_profit_threshold": 40.0, "max_items_per_batch": 8
    },
]

@app.on_event("startup")
async def seed_workshops():
    count = await workshops_collection.count_documents({})
    if count == 0:
        logger.info("Seeding %d default workshops into MongoDB...", len(DEFAULT_WORKSHOPS))
        await workshops_collection.insert_many(DEFAULT_WORKSHOPS)
        logger.info("Workshops seeded successfully.")

@app.get("/api/stats/dashboard", tags=["stats"])
async def get_dashboard_stats():
    total_pending = await products_collection.count_documents({"status": {"$in": ["PENDING_EVALUATION", "AI_EVALUATED", "REVIEW_READY", "PENDING_ADMIN_REVIEW"]}})
    published = await products_collection.count_documents({"status": "PUBLISHED"})
    rejected = await products_collection.count_documents({"status": "REJECTED"})
    total_processed = await products_collection.count_documents({})

    all_prods = await products_collection.find({"status": {"$ne": "REJECTED"}}).to_list(length=500)
    for_recondition = 0
    for_resale = 0
    for_recycle = 0

    for p in all_prods:
        dec = (p.get("admin_review", {}) or {}).get("decision") or (p.get("ai_predictions", {}) or {}).get("decision")
        if dec == "RECONDITION":
            for_recondition += 1
        elif dec == "RESALE_DIRECT":
            for_resale += 1
        elif dec == "RECYCLE":
            for_recycle += 1

    return {
        "totalPending": total_pending,
        "published": published,
        "rejected": rejected,
        "totalProcessed": total_processed,
        "forRecondition": for_recondition,
        "forResale": for_resale,
        "forRecycle": for_recycle,
        "avgDelay": 4.2,
        "totalTransportCost": (for_recondition * 15) + (for_resale * 8) + (for_recycle * 22)
    }

# ── Workshop CRUD ─────────────────────────────────────────────────
@app.get("/api/logistics/workshops", tags=["logistics"])
async def get_workshops():
    cursor = workshops_collection.find({})
    workshops = await cursor.to_list(length=200)
    result = []
    for w in workshops:
        w["id"] = str(w.pop("_id"))
        result.append(w)
    return result

@app.post("/api/logistics/workshops", tags=["logistics"], status_code=201)
async def create_workshop(workshop: dict):
    res = await workshops_collection.insert_one(workshop)
    return {"id": str(res.inserted_id), **workshop}

@app.put("/api/logistics/workshops/{workshop_id}", tags=["logistics"])
async def update_workshop(workshop_id: str, workshop: dict):
    oid = ObjectId(workshop_id)
    workshop.pop("_id", None)
    workshop.pop("id", None)
    result = await workshops_collection.update_one({"_id": oid}, {"$set": workshop})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Workshop not found")
    return {"status": "updated", "id": workshop_id}

@app.delete("/api/logistics/workshops/{workshop_id}", tags=["logistics"])
async def delete_workshop(workshop_id: str):
    oid = ObjectId(workshop_id)
    result = await workshops_collection.delete_one({"_id": oid})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Workshop not found")
    return {"status": "deleted"}

# ── Logistics Optimization ────────────────────────────────────────
@app.post("/api/logistics/optimize", tags=["logistics"])
async def optimize_logistics():
    cursor = products_collection.find({
        "status": {"$ne": "REJECTED"},
        "$or": [
            {"ai_predictions": {"$ne": None}},
            {"admin_review": {"$ne": None}}
        ]
    })
    all_prods = await cursor.to_list(length=200)

    if not all_prods:
        return {"allocations": [], "status": "NO_PRODUCTS", "total_profit": 0.0}

    recondition_prods = []
    for p in all_prods:
        admin_dec = p.get("admin_review", {}).get("decision") if p.get("admin_review") else None
        ai_dec = p.get("ai_predictions", {}).get("decision") if p.get("ai_predictions") else None
        dec = admin_dec or ai_dec or "RECONDITION"
        if dec == "RECONDITION":
            recondition_prods.append(p)

    target_prods = recondition_prods if recondition_prods else all_prods

    payload = {
        "products": [
            {
                "product_id": str(p["_id"]),
                "grade": (p.get("admin_review") or {}).get("grade") or (p.get("ai_predictions") or {}).get("grade", "C"),
                "profit": (p.get("ai_predictions") or {}).get("profit", 30.0)
            } for p in target_prods
        ]
    }

    try:
        ORCHESTRATOR_URL = os.getenv("ORCHESTRATOR_URL", "http://127.0.0.1:8000")
        async with httpx.AsyncClient() as client:
            res = await client.post(f"{ORCHESTRATOR_URL}/optimize-logistics", json=payload, timeout=30.0)
            res.raise_for_status()
            optimization = res.json()

        allocations = optimization.get("allocations", [])
        enriched = []
        for alloc in allocations:
            pid = alloc["product_id"]
            prod = next((p for p in target_prods if str(p["_id"]) == pid), None)
            if prod:
                ai = prod.get("ai_predictions") or {}
                ar = prod.get("admin_review") or {}
                grade = ar.get("grade") or ai.get("grade", "C")
                cost = ar.get("refurb_cost") or ai.get("refurb_cost", 0)
                enriched.append({
                    "productId": pid,
                    "productName": f"{prod.get('brand')} {prod.get('model')}",
                    "grade": grade,
                    "decision": "RECONDITION",
                    "workshop": alloc["workshop"],
                    "channel": "Leboncoin",
                    "estimatedDelay": 5,
                    "transportCost": 15,
                    "totalCost": round(15 + cost, 2)
                })

        other_prods = [p for p in all_prods if str(p["_id"]) not in [a["productId"] for a in enriched]]
        for op in other_prods:
            ai = op.get("ai_predictions") or {}
            ar = op.get("admin_review") or {}
            decision = ar.get("decision") or ai.get("decision", "RESALE_DIRECT")
            transport_cost = 8 if decision == "RESALE_DIRECT" else 22
            enriched.append({
                "productId": str(op["_id"]),
                "productName": f"{op.get('brand')} {op.get('model')}",
                "grade": ar.get("grade") or ai.get("grade", "C"),
                "decision": decision,
                "workshop": None,
                "channel": "BackMarket" if decision == "RESALE_DIRECT" else "Filière D3E",
                "estimatedDelay": 2 if decision == "RESALE_DIRECT" else 7,
                "transportCost": transport_cost,
                "totalCost": transport_cost
            })

        return {
            "allocations": enriched,
            "status": optimization.get("status", "OPTIMAL"),
            "total_profit": optimization.get("total_expected_profit", 0.0)
        }
    except Exception as e:
        logger.error("Optimization failed: %s", e)
        enriched = []
        for p in all_prods:
            ai = p.get("ai_predictions") or {}
            ar = p.get("admin_review") or {}
            dec = ar.get("decision") or ai.get("decision", "RECONDITION")
            enriched.append({
                "productId": str(p["_id"]),
                "productName": f"{p.get('brand')} {p.get('model')}",
                "grade": ar.get("grade") or ai.get("grade", "C"),
                "decision": dec,
                "workshop": "Atelier Platana Nord" if dec == "RECONDITION" else None,
                "channel": "Leboncoin" if dec == "RECONDITION" else ("BackMarket" if dec == "RESALE_DIRECT" else "Filière D3E"),
                "estimatedDelay": 5 if dec == "RECONDITION" else 2,
                "transportCost": 15 if dec == "RECONDITION" else 8,
                "totalCost": 15 + ai.get("refurb_cost", 0)
            })
        return {"allocations": enriched, "status": "OPTIMAL_FALLBACK", "total_profit": sum(p.get("ai_predictions", {}).get("profit", 0) for p in all_prods)}