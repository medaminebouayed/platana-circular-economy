"""
Platana Main Service — Production-ready FastAPI microservice.
Responsible for: Authentication, product management, Dify AI integration, admin review, publication.
Port: 8003
"""
import os
import re
import uuid
import shutil
import hashlib
import logging
import mimetypes
from contextlib import asynccontextmanager
from pathlib import Path
from typing import List, Optional
from datetime import datetime, timedelta, timezone
import json

import jwt
import httpx
from bson import ObjectId
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Depends
from fastapi.responses import FileResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from passlib.context import CryptContext
from pydantic import BaseModel, ValidationError
from dotenv import load_dotenv

# ── Config ─────────────────────────────────────────────────────
import sys
sys.path.append(str(Path(__file__).resolve().parents[1]))

env_path = Path(__file__).resolve().parents[2] / '.env'
load_dotenv(dotenv_path=env_path)

from database.database import (products_collection, users_collection, workshops_collection,
                               product_catalog_collection, pricing_training_samples_collection)
from shared.models import AIPredictions, AdminReview, ModelDrift
from shared.defects import normalize_defect_list, get_defect_catalog
from shared.report_pdf import generate_product_report
from shared.training_export import (
    derive_decision,
    upsert_pricing_training_sample,
)
from shared.catalog_seed import ensure_product_catalog
from shared.workshop_seed import ensure_workshops

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | main_service | %(message)s")
logger = logging.getLogger(__name__)

# ── Dify Config ─────────────────────────────────────────────────
DIFY_API_URL = os.getenv("DIFY_API_URL", "http://host.docker.internal:80/v1")
DIFY_EVAL_API_KEY = os.getenv("DIFY_EVAL_API_KEY")
DIFY_PUBLISH_API_KEY = os.getenv("DIFY_PUBLISH_API_KEY")
DIFY_USER = "platana-backend"

# ── Internal Training Service Config ─────────────────────────────
TRAINING_SERVICE_URL = os.getenv("TRAINING_SERVICE_URL", "http://training-service:8010")
TRAINING_SERVICE_TOKEN = os.getenv("TRAINING_SERVICE_TOKEN", "")

# ── Internal AI Services (admin tooling proxies) ─────────────────
CV_SERVICE_URL = os.getenv("CV_SERVICE_URL", "http://cv-service:8001")
PRICING_SERVICE_URL = os.getenv("PRICING_SERVICE_URL", "http://pricing-service:8002")

# ── App ─────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: seed default accounts + indexes
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
                "created_at": datetime.now(timezone.utc),
            },
            {
                "email": "user@example.com",
                "password": hash_password("user"),
                "role": "USER",
                "name": "Utilisateur Test",
                "avatar": "https://api.dicebear.com/7.x/initials/svg?seed=User",
                "roleLabel": "Vendeur",
                "created_at": datetime.now(timezone.utc),
            },
        ])
        logger.info("Default accounts seeded.")
    await product_catalog_collection.create_index([("brand", 1), ("model", 1)], unique=True)
    await product_catalog_collection.create_index("brand")
    await ensure_product_catalog(product_catalog_collection)
    await pricing_training_samples_collection.create_index("source_product_id", unique=True, sparse=True)

    # Startup: seed default workshops (only when the collection is empty)
    await ensure_workshops(workshops_collection)

    yield

    # Shutdown: close MongoDB connection
    from database.database import client
    if client:
        client.close()
        logger.info("MongoDB connection closed.")


app = FastAPI(
    title="Platana Main Service",
    description="Core API: authentication, product lifecycle management, Dify orchestration, and admin review.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
UPLOAD_DIR = REPO_ROOT / "data" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
REPORT_DIR = REPO_ROOT / "data" / "reports"
REPORT_DIR.mkdir(parents=True, exist_ok=True)

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
    to_encode["exp"] = datetime.now(timezone.utc) + timedelta(hours=expiry_hours)
    to_encode["iat"] = datetime.now(timezone.utc)
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


async def require_admin(current_user: dict = Depends(get_current_user)) -> dict:
    if current_user.get("role") != "ADMIN":
        raise HTTPException(status_code=403, detail="Administrateur requis")
    return current_user


def _resolve_image_path(stored_path: str) -> Path:
    """Resolve a stored image path safely inside UPLOAD_DIR (Docker: /app/data/uploads)."""
    candidate = Path(stored_path)
    if not candidate.is_absolute():
        candidate = REPO_ROOT / candidate
    resolved = candidate.resolve()
    upload_root = UPLOAD_DIR.resolve()
    if not str(resolved).startswith(str(upload_root)):
        raise HTTPException(status_code=403, detail="Accès image refusé")
    if not resolved.is_file():
        fallback = upload_root / Path(stored_path).name
        if fallback.is_file():
            return fallback
        raise HTTPException(status_code=404, detail="Image introuvable")
    return resolved


async def _get_product_or_404(product_id: str) -> dict:
    try:
        oid = ObjectId(product_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid product ID")
    product = await products_collection.find_one({"_id": oid})
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


def _can_access_product(product: dict, user: dict) -> bool:
    if user.get("role") == "ADMIN":
        return True
    return product.get("user_email") == user.get("sub")


def _product_report_path(product_id: str) -> Path:
    """Return the absolute report path for a product id."""
    return REPORT_DIR / f"{product_id}.pdf"


def _regenerate_report(product: dict) -> str | None:
    """Generate the evaluation report PDF and return its relative path (or None on failure)."""
    try:
        oid = product["_id"]
        rel_path = Path("data") / "reports" / f"{str(oid)}.pdf"
        generate_product_report(product, REPORT_DIR / f"{str(oid)}.pdf")
        return str(rel_path).replace("\\", "/")
    except Exception as exc:
        logger.error("Report generation failed for product %s: %s", product.get("_id"), exc)
        return None


def _resolve_report_path(stored_path: str) -> Path:
    """Resolve a stored report path safely inside REPORT_DIR."""
    candidate = Path(stored_path)
    if not candidate.is_absolute():
        candidate = REPO_ROOT / candidate
    resolved = candidate.resolve()
    report_root = REPORT_DIR.resolve()
    if not str(resolved).startswith(str(report_root)):
        raise HTTPException(status_code=403, detail="Accès rapport refusé")
    if not resolved.is_file():
        raise HTTPException(status_code=404, detail="Rapport PDF introuvable")
    return resolved

# ── Health Check ─────────────────────────────────────────────────
@app.get("/health", tags=["health"])
async def health():
    return {
        "status": "ok",
        "service": "main_service",
        "dify_url": DIFY_API_URL,
        "dify_key_configured": bool(DIFY_EVAL_API_KEY),
    }


# PRODUCT CATALOG
@app.get("/api/catalog/brands", tags=["catalog"])
async def search_catalog_brands(q: str = "", limit: int = 20):
    """Return searchable brand suggestions from the seeded pricing catalog."""
    limit = max(1, min(limit, 50))
    query = q.strip()
    match = {"brand": {"$regex": f"^{re.escape(query)}", "$options": "i"}} if query else {}
    brands = await product_catalog_collection.distinct("brand", match)
    return {"items": sorted(brands, key=str.casefold)[:limit]}


@app.get("/api/catalog/models", tags=["catalog"])
async def search_catalog_models(brand: str, q: str = "", limit: int = 30):
    """Return models for one selected brand, optionally filtered while typing."""
    brand = brand.strip()
    if not brand:
        raise HTTPException(status_code=422, detail="brand is required")
    limit = max(1, min(limit, 50))
    criteria = {"brand": brand}
    if q.strip():
        criteria["model"] = {"$regex": f"^{re.escape(q.strip())}", "$options": "i"}
    cursor = product_catalog_collection.find(
        criteria, {"_id": 0, "model": 1, "category": 1, "original_price": 1}
    ).sort("model", 1).limit(limit)
    return {"items": await cursor.to_list(length=limit)}

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
        "created_at": datetime.now(timezone.utc),
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
    maxAIFaults: Optional[int] = 10

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
    p = dict(p)
    p["id"] = str(p.pop("_id"))
    if p.get("status") == "REVIEW_READY":
        p["status"] = "PENDING_ADMIN_REVIEW"
    return p

@app.get("/api/defects/catalog", tags=["catalog"])
async def list_defect_catalog():
    """Return canonical defect ids for admin verification UI."""
    return {"items": get_defect_catalog()}

@app.get("/api/products/pending", tags=["products"])
async def get_pending_products(_admin: dict = Depends(require_admin)):
    cursor = products_collection.find({"status": {"$in": ["REVIEW_READY", "PENDING_EVALUATION", "PENDING_ADMIN_REVIEW"]}})
    products = await cursor.to_list(length=200)
    return [_serialize(p) for p in products]

@app.get("/api/products", tags=["products"])
async def get_all_products(_admin: dict = Depends(require_admin)):
    cursor = products_collection.find()
    products = await cursor.to_list(length=200)
    return [_serialize(p) for p in products]

@app.delete("/api/products/{product_id}", tags=["admin"])
async def delete_product(product_id: str, _admin: dict = Depends(require_admin)):
    """Permanently delete a product and its attached files (AI_ERROR orphans, ...)."""
    product = await _get_product_or_404(product_id)
    oid = product["_id"]
    for rel in product.get("image_paths") or []:
        try:
            img = _resolve_image_path(rel)
            if img.is_file():
                img.unlink()
        except Exception as exc:
            logger.warning("Could not delete image %s: %s", rel, exc)
    rel = product.get("report_path")
    if rel:
        try:
            rp = _resolve_report_path(rel)
            if rp.is_file():
                rp.unlink()
        except Exception as exc:
            logger.warning("Could not delete report %s: %s", rel, exc)
    await products_collection.delete_one({"_id": oid})
    logger.info("Admin deleted product %s", product_id)
    return {"status": "deleted", "id": product_id}

@app.get("/api/products/user/{email}", tags=["products"])
async def get_user_products(email: str, current_user: dict = Depends(get_current_user)):
    if current_user.get("role") != "ADMIN" and current_user.get("sub") != email:
        raise HTTPException(status_code=403, detail="Accès refusé")
    cursor = products_collection.find({"user_email": email}).sort("created_at", -1)
    products = await cursor.to_list(length=200)
    return [_serialize(p) for p in products]

@app.get("/api/products/{product_id}", tags=["products"])
async def get_product(product_id: str, current_user: dict = Depends(get_current_user)):
    product = await _get_product_or_404(product_id)
    if not _can_access_product(product, current_user):
        raise HTTPException(status_code=403, detail="Accès refusé")
    return _serialize(product)

@app.get("/api/products/{product_id}/images/{index}", tags=["products"])
async def get_product_image(product_id: str, index: int, current_user: dict = Depends(get_current_user)):
    product = await _get_product_or_404(product_id)
    if not _can_access_product(product, current_user):
        raise HTTPException(status_code=403, detail="Accès refusé")
    image_paths = product.get("image_paths") or []
    if index < 0 or index >= len(image_paths):
        raise HTTPException(status_code=404, detail="Image index out of range")
    image_path = _resolve_image_path(image_paths[index])
    media_type = mimetypes.guess_type(str(image_path))[0] or "application/octet-stream"
    return FileResponse(path=image_path, media_type=media_type, filename=image_path.name)

@app.get("/api/products/{product_id}/report", tags=["products"])
async def get_product_report(product_id: str, current_user: dict = Depends(get_current_user)):
    """Download the evaluation report PDF for a product (owner or admin).

    If the report was never generated (legacy products), it is produced on
    demand so both the admin and the product owner always get a PDF.
    """
    product = await _get_product_or_404(product_id)
    if not _can_access_product(product, current_user):
        raise HTTPException(status_code=403, detail="Accès refusé")
    stored_path = product.get("report_path")
    if not stored_path:
        report_path = _regenerate_report(product)
        if not report_path:
            raise HTTPException(status_code=404, detail="Rapport PDF indisponible")
        await products_collection.update_one(
            {"_id": product["_id"]},
            {"$set": {"report_path": report_path}},
        )
    else:
        report_path = stored_path
    pdf_path = _resolve_report_path(report_path)
    return FileResponse(
        path=pdf_path,
        media_type="application/pdf",
        filename=f"platana_report_{product_id}.pdf",
    )

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
    files: List[UploadFile] = File(...),
    current_user: dict = Depends(get_current_user),
):
    if not files:
        raise HTTPException(status_code=422, detail="Au moins une image est requise")
    effective_email = current_user.get("sub") or user_email

    saved_image_paths = []
    for f in files:
        ext = Path(f.filename).suffix if f.filename else ".jpg"
        path = UPLOAD_DIR / f"{uuid.uuid4().hex}{ext}"
        with open(path, "wb") as buf:
            shutil.copyfileobj(f.file, buf)
        saved_image_paths.append(str(path.relative_to(REPO_ROOT)).replace("\\", "/"))

    doc = {
        "brand": brand, "model": model, "year": year,
        "original_price": original_price,
        "image_paths": saved_image_paths,
        "status": "PENDING_EVALUATION",
        "user_email": effective_email,
        "created_at": datetime.now(timezone.utc),
    }
    result = await products_collection.insert_one(doc)
    product_id = str(result.inserted_id)
    logger.info("Product inserted: id=%s, user=%s", product_id, effective_email)

    from dify.dify_client import upload_file_to_dify, run_eval_workflow
    try:
        dify_file_ids = []
        for rel_path in saved_image_paths:
            abs_path = REPO_ROOT / rel_path
            file_id = await upload_file_to_dify(str(abs_path), abs_path.name)
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

    report_path = _regenerate_report(await products_collection.find_one({"_id": result.inserted_id}))
    if report_path:
        await products_collection.update_one(
            {"_id": result.inserted_id},
            {"$set": {"report_path": report_path}},
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
async def review_product(product_id: str, review: AdminReview, _admin: dict = Depends(require_admin)):
    product = await _get_product_or_404(product_id)
    oid = product["_id"]

    normalized_defects = normalize_defect_list(review.defects)
    decision = review.decision or derive_decision(
        review.grade, review.market_price, review.refurb_cost
    )
    review_payload = review.dict()
    review_payload["defects"] = normalized_defects
    review_payload["decision"] = decision
    if not review_payload.get("reviewed_by"):
        review_payload["reviewed_by"] = _admin.get("sub", "admin")
    review_payload["reviewed_at"] = datetime.now(timezone.utc)

    ai_pred = product.get("ai_predictions")
    model_drift = None
    if ai_pred:
        ai_defects = normalize_defect_list(ai_pred.get("defects", []))
        drift = ModelDrift(
            pricing_error_eur=round(review.market_price - ai_pred["market_price"], 2),
            grade_changed=ai_pred["grade"] != review.grade,
            defects_changed=set(ai_defects) != set(normalized_defects),
        )
        model_drift = drift.dict()

    await products_collection.update_one(
        {"_id": oid},
        {"$set": {
            "status": "REVIEWED",
            "admin_review": review_payload,
            "model_drift": model_drift,
            "reviewed_at": review_payload["reviewed_at"],
        }},
    )
    logger.info("Product %s reviewed by %s", product_id, review_payload["reviewed_by"])

    report_path = _regenerate_report(await products_collection.find_one({"_id": oid}))
    if report_path:
        await products_collection.update_one(
            {"_id": oid},
            {"$set": {"report_path": report_path}},
        )

    try:
        await upsert_pricing_training_sample(
            products_collection, pricing_training_samples_collection, product_id
        )
    except Exception as exc:
        logger.warning("Training export failed for product %s: %s", product_id, exc)

    return {"status": "REVIEWED", "message": "Review saved successfully.", "admin_review": review_payload}

class RejectRequest(BaseModel):
    reason: Optional[str] = "Rejeté par l'administrateur"
    rejected_by: Optional[str] = "admin"

@app.post("/api/products/{product_id}/reject", tags=["admin"])
async def reject_product(
    product_id: str,
    req: Optional[RejectRequest] = None,
    admin: dict = Depends(require_admin),
):
    product = await _get_product_or_404(product_id)
    oid = product["_id"]

    reason = req.reason if req else "Rejeté par l'administrateur"
    rejected_by = (req.rejected_by if req else None) or admin.get("sub", "admin")

    await products_collection.update_one(
        {"_id": oid},
        {"$set": {
            "status": "REJECTED",
            "rejection_reason": reason,
            "rejected_by": rejected_by,
            "rejected_at": datetime.now(timezone.utc)
        }}
    )
    logger.info("Product %s rejected by %s", product_id, rejected_by)
    return {"status": "REJECTED", "message": "Produit rejeté avec succès."}

@app.post("/api/products/{product_id}/re-evaluate", tags=["admin"])
async def re_evaluate_product(product_id: str, _admin: dict = Depends(require_admin)):
    product = await _get_product_or_404(product_id)
    oid = product["_id"]

    saved_image_paths = product.get("image_paths", [])
    brand = product.get("brand", "")
    model = product.get("model", "")
    year = product.get("year", 2023)
    original_price = product.get("original_price", 0.0)

    from dify.dify_client import upload_file_to_dify, run_eval_workflow
    try:
        dify_file_ids = []
        for rel_path in saved_image_paths:
            abs_path = REPO_ROOT / rel_path if not Path(rel_path).is_absolute() else Path(rel_path)
            file_id = await upload_file_to_dify(str(abs_path), abs_path.name)
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
                "updated_at": datetime.now(timezone.utc)
            }}
        )
        report_path = _regenerate_report(await products_collection.find_one({"_id": oid}))
        if report_path:
            await products_collection.update_one(
                {"_id": oid},
                {"$set": {"report_path": report_path}},
            )
        return {"status": "REVIEW_READY", "ai_predictions": ai_predictions.dict(), "message": "Ré-évaluation effectuée avec succès."}
    except Exception as e:
        logger.error("Re-evaluation failed for %s: %s", product_id, e)
        raise HTTPException(status_code=502, detail=f"Échec de la ré-évaluation: {str(e)}")

# ══════════════════════════════════════════════════════════════════
# PUBLICATION VIA DIFY
# ══════════════════════════════════════════════════════════════════
@app.post("/api/products/{product_id}/publish", tags=["admin"])
async def publish_product(product_id: str, _admin: dict = Depends(require_admin)):
    product = await _get_product_or_404(product_id)
    oid = product["_id"]
    
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
        {"$set": {"status": "PUBLISHED", "shopify_url": shopify_url, "published_at": datetime.now(timezone.utc)}},
    )
    logger.info("Product %s published: %s", product_id, shopify_url)
    return {"status": "PUBLISHED", "shopify_url": shopify_url}


# ── Dashboard & Logistics APIs ───────────────────────────────────

# Named constants for the sales/recycling channels (business rules, not data).
# Workshop capacity/cost/distance always come from the `workshops` collection.
TRANSPORT_COST_PER_KM = 0.12
CHANNEL_BY_DECISION = {
    "RECONDITION": "Leboncoin",
    "RESALE_DIRECT": "BackMarket",
    "RECYCLE": "Filière D3E",
}
BASE_TRANSPORT_COST = {"RESALE_DIRECT": 8.0, "RECYCLE": 22.0}
BASE_ESTIMATED_DELAY = {"RECONDITION": 5, "RESALE_DIRECT": 2, "RECYCLE": 7}


def _transport_cost(decision: str, distance_km: float = 0.0) -> float:
    """Transport estimate per product.

    Reconditioned units ship to the assigned workshop, so the cost scales with
    its real distance from the hub. Direct resale and recycling use fixed
    collection/handling costs.
    """
    if decision == "RECONDITION":
        return round(max(0.0, distance_km) * TRANSPORT_COST_PER_KM, 2)
    return BASE_TRANSPORT_COST.get(decision, 8.0)


async def _fetch_available_workshops() -> list[dict]:
    """Non-full workshops from MongoDB (the runtime source of truth)."""
    cursor = workshops_collection.find({"status": {"$ne": "full"}})
    return await cursor.to_list(length=200)

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

    grade_distribution = {"A": 0, "B": 0, "C": 0, "D": 0}
    prices = []
    profits = []
    ai_grade_before_admin = 0
    ai_price_before_admin = 0

    for p in all_prods:
        dec = (p.get("admin_review", {}) or {}).get("decision") or (p.get("ai_predictions", {}) or {}).get("decision")
        if dec == "RECONDITION":
            for_recondition += 1
        elif dec == "RESALE_DIRECT":
            for_resale += 1
        elif dec == "RECYCLE":
            for_recycle += 1

        review = (p.get("admin_review") or {}) if (p.get("admin_review") or {}).get("market_price") else None
        if review:
            grade_distribution[review.get("grade", "C")] = grade_distribution.get(review.get("grade", "C"), 0) + 1
            prices.append(review.get("market_price", 0))
        else:
            ai = (p.get("ai_predictions") or {})
            grade_distribution[ai.get("grade", "C")] = grade_distribution.get(ai.get("grade", "C"), 0) + 1
            if ai.get("market_price"):
                prices.append(ai.get("market_price"))
        if review and p.get("model_drift"):
            if p["model_drift"].get("grade_changed"):
                ai_grade_before_admin += 1
            if p["model_drift"].get("pricing_error_eur"):
                ai_price_before_admin += 1
        profit = (p.get("admin_review") or {}).get("market_price") or (p.get("ai_predictions") or {}).get("profit")
        if review:
            profits.append(review.get("market_price", 0) - (review.get("refurb_cost") or (p.get("ai_predictions") or {}).get("refurb_cost") or 0))
        elif (p.get("ai_predictions") or {}).get("profit") is not None:
            profits.append((p.get("ai_predictions") or {}).get("profit"))

    avg_price = round(sum(prices) / len(prices), 2) if prices else 0.0
    total_revenue = round(sum(prices), 2)
    total_profit = round(sum(profits), 2)

    delay_diffs = []
    cursor = products_collection.find(
        {"reviewed_at": {"$exists": True, "$ne": None}, "created_at": {"$exists": True, "$ne": None}},
        {"reviewed_at": 1, "created_at": 1},
    )
    async for p in cursor:
        diff_hours = (p["reviewed_at"] - p["created_at"]).total_seconds() / 3600.0
        if diff_hours >= 0:
            delay_diffs.append(diff_hours)
    avg_delay = round(sum(delay_diffs) / len(delay_diffs), 2) if delay_diffs else 0.0

    # Transport estimate driven by the real workshops collection: reconditioned
    # units ship to the average-distance available workshop, direct resale and
    # recycling use the fixed per-unit handling costs.
    workshops = await _fetch_available_workshops()
    avg_distance = (
        round(sum(w.get("distance", 0) for w in workshops) / len(workshops), 2)
        if workshops else 0.0
    )
    total_transport_cost = round(
        for_recondition * _transport_cost("RECONDITION", avg_distance)
        + for_resale * _transport_cost("RESALE_DIRECT")
        + for_recycle * _transport_cost("RECYCLE"),
        2,
    )

    return {
        "totalPending": total_pending,
        "published": published,
        "rejected": rejected,
        "totalProcessed": total_processed,
        "forRecondition": for_recondition,
        "forResale": for_resale,
        "forRecycle": for_recycle,
        "gradeDistribution": grade_distribution,
        "avgPrice": avg_price,
        "totalRevenue": total_revenue,
        "totalProfit": total_profit,
        "aiGradeCorrections": ai_grade_before_admin,
        "aiPriceCorrections": ai_price_before_admin,
        "avgDelay": avg_delay,
        "totalTransportCost": total_transport_cost,
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
    workshop.pop("_id", None)
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

    available_workshops = await _fetch_available_workshops()
    workshop_by_name = {w.get("name"): w for w in available_workshops if w.get("name")}
    fallback_workshop = available_workshops[0] if available_workshops else None

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
                workshop = workshop_by_name.get(alloc["workshop"], {})
                transport_cost = _transport_cost("RECONDITION", workshop.get("distance", 0))
                enriched.append({
                    "productId": pid,
                    "productName": f"{prod.get('brand')} {prod.get('model')}",
                    "grade": grade,
                    "decision": "RECONDITION",
                    "workshop": alloc["workshop"],
                    "channel": CHANNEL_BY_DECISION["RECONDITION"],
                    "estimatedDelay": BASE_ESTIMATED_DELAY["RECONDITION"],
                    "transportCost": transport_cost,
                    "totalCost": round(transport_cost + cost, 2)
                })

        other_prods = [p for p in all_prods if str(p["_id"]) not in [a["productId"] for a in enriched]]
        for op in other_prods:
            ai = op.get("ai_predictions") or {}
            ar = op.get("admin_review") or {}
            decision = ar.get("decision") or ai.get("decision", "RESALE_DIRECT")
            transport_cost = _transport_cost(decision)
            enriched.append({
                "productId": str(op["_id"]),
                "productName": f"{op.get('brand')} {op.get('model')}",
                "grade": ar.get("grade") or ai.get("grade", "C"),
                "decision": decision,
                "workshop": None,
                "channel": CHANNEL_BY_DECISION.get(decision, "Leboncoin"),
                "estimatedDelay": BASE_ESTIMATED_DELAY.get(decision, 2),
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
            distance = (fallback_workshop or {}).get("distance", 0) if dec == "RECONDITION" else 0
            transport_cost = _transport_cost(dec, distance)
            workshop_name = fallback_workshop.get("name") if (dec == "RECONDITION" and fallback_workshop) else None
            enriched.append({
                "productId": str(p["_id"]),
                "productName": f"{p.get('brand')} {p.get('model')}",
                "grade": ar.get("grade") or ai.get("grade", "C"),
                "decision": dec,
                "workshop": workshop_name,
                "channel": CHANNEL_BY_DECISION.get(dec, "Leboncoin"),
                "estimatedDelay": BASE_ESTIMATED_DELAY.get(dec, 2),
                "transportCost": transport_cost,
                "totalCost": round(transport_cost + (ai.get("refurb_cost", 0) if dec == "RECONDITION" else 0), 2)
            })
        return {"allocations": enriched, "status": "OPTIMAL_FALLBACK", "total_profit": sum(p.get("ai_predictions", {}).get("profit", 0) for p in all_prods)}

# ══════════════════════════════════════════════════════════════════
# CONTINUOUS LEARNING — ADMIN RETRAIN TRIGGER (proxied to training-service)
# ══════════════════════════════════════════════════════════════════
class TrainingJobRequest(BaseModel):
    model: str

@app.post("/api/training/jobs", status_code=202, tags=["training"])
async def create_training_job(request: TrainingJobRequest, _admin: dict = Depends(require_admin)):
    """Queue a guarded continuous-training run (pricing or cv) on the internal service."""
    if request.model not in ("pricing", "cv"):
        raise HTTPException(status_code=422, detail="model must be pricing or cv")
    if not TRAINING_SERVICE_TOKEN:
        raise HTTPException(status_code=503, detail="TRAINING_SERVICE_TOKEN not configured on main-service")
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            res = await client.post(
                f"{TRAINING_SERVICE_URL}/jobs",
                json={"model": request.model},
                headers={"X-Training-Service-Token": TRAINING_SERVICE_TOKEN},
            )
            if res.status_code >= 400:
                logger.error("Training-service rejected job request: %s", res.text)
                raise HTTPException(status_code=res.status_code, detail=res.text)
            return res.json()
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Could not reach training-service: %s", e)
        raise HTTPException(status_code=503, detail=f"Training service unreachable: {e}")

@app.get("/api/training/jobs", tags=["training"])
async def list_training_jobs(limit: int = 20, _admin: dict = Depends(require_admin)):
    """List recent training jobs from the internal training service."""
    if not TRAINING_SERVICE_TOKEN:
        raise HTTPException(status_code=503, detail="TRAINING_SERVICE_TOKEN not configured on main-service")
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            res = await client.get(
                f"{TRAINING_SERVICE_URL}/jobs",
                params={"limit": limit},
                headers={"X-Training-Service-Token": TRAINING_SERVICE_TOKEN},
            )
            if res.status_code >= 400:
                raise HTTPException(status_code=res.status_code, detail=res.text)
            return res.json()
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Could not reach training-service: %s", e)
        raise HTTPException(status_code=503, detail=f"Training service unreachable: {e}")

# ══════════════════════════════════════════════════════════════════
# ADMIN TOOLING PROXIES — CV grading / pricing prediction
# ══════════════════════════════════════════════════════════════════
@app.post("/api/cv/grade", tags=["admin"])
async def proxy_cv_grade(files: List[UploadFile] = File(...), _admin: dict = Depends(require_admin)):
    """Forward uploaded photos to the internal CV service and return the grade."""
    if not 1 <= len(files) <= 5:
        raise HTTPException(status_code=400, detail="1 to 5 images are required.")
    try:
        payload = []
        for i, f in enumerate(files):
            payload.append((f.filename or f"view{i}.jpg", await f.read(), f.content_type or "image/jpeg"))
        async with httpx.AsyncClient(timeout=60.0) as client:
            res = await client.post(
                f"{CV_SERVICE_URL}/grade",
                files=[("files", item) for item in payload],
            )
            if res.status_code >= 400:
                raise HTTPException(status_code=res.status_code, detail=res.text)
            return res.json()
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Could not reach cv-service: %s", e)
        raise HTTPException(status_code=503, detail=f"CV service unreachable: {e}")

@app.post("/api/pricing/predict", tags=["admin"])
async def proxy_pricing_predict(request: dict, _admin: dict = Depends(require_admin)):
    """Forward a pricing prediction request to the internal pricing service."""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            res = await client.post(f"{PRICING_SERVICE_URL}/predict", json=request)
            if res.status_code >= 400:
                raise HTTPException(status_code=res.status_code, detail=res.text)
            return res.json()
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Could not reach pricing-service: %s", e)
        raise HTTPException(status_code=503, detail=f"Pricing service unreachable: {e}")

_SHEET_DEFECT_LABELS = {
    "scratch": "Rayure cosmétique",
    "dent": "Enfoncement / choc",
    "crack": "Fissure",
    "discoloration": "Décoloration",
    "missing_part": "Pièce manquante",
    "water_damage": "Dégât des eaux",
    "screen_crack": "Écran fissuré",
    "cosmetic_scratch": "Rayure cosmétique",
    "back_glass_crack": "Vitre arrière fissurée",
    "battery_weak": "Batterie faible",
    "no_defect": "Aucun défaut",
}

@app.post("/api/sheet/generate", tags=["admin"])
async def generate_sheet(request: dict, _admin: dict = Depends(require_admin)):
    """Generate a product sheet (decision + marketing copy) from a freeform form.

    Uses the same RefurbDecisionEngine thresholds as the training pipeline, so the
    decision shown here always matches the backend business rules. The copy itself is
    produced locally (deterministic template) — the Dify-based variant lives behind
    `POST /api/products/{id}/publish`.
    """
    grade = str(request.get("grade") or "C").upper()
    brand = str(request.get("brand") or "").strip() or "Produit"
    model = str(request.get("model") or "").strip() or ""
    category = str(request.get("category") or "").strip() or "Produit"
    original_price = float(request.get("originalPrice") or 0.0)
    predicted_price = float(request.get("predictedPrice") or 0.0)
    repair_cost = float(request.get("repairCost") or 0.0)
    defects = [str(d) for d in (request.get("defects") or []) if str(d) and str(d) != "no_defect"]

    decision = derive_decision(grade, predicted_price, repair_cost)
    channels = CHANNEL_BY_DECISION.get(decision, ["Leboncoin"])

    defect_lines = [_SHEET_DEFECT_LABELS.get(d, d) for d in defects]
    margin = round(predicted_price - repair_cost, 2)

    name = f"{brand} {model}".strip()
    title = f"{name or category} reconditionné — Grade {grade}"
    description_lines = [
        f"{name or category} d'occasion contrôlée, grade {grade} attribué par notre IA de vision.",
        f"Prix de revente estimé : {predicted_price:g} € (neuf : {original_price:g} €).",
    ]
    if defect_lines:
        description_lines.append("Défauts signalés : " + ", ".join(defect_lines) + ".")
    else:
        description_lines.append("Aucun défaut majeur détecté.")
    description_lines.append("Garantie 6 mois incluse, livraison suivie et paiement sécurisé.")
    description = "\n".join(description_lines)

    highlights = [
        f"Grade {grade} validé par notre pipeline de vision multi-vues",
        f"Rapport de revente : {predicted_price:g} € vs neuf {original_price:g} €",
        f"Remise en état estimée : {repair_cost:g} € — marge nette {margin:g} €",
        "Garantie 6 mois + assistance à la revente",
    ]

    attention_points = defect_lines if defect_lines else ["Prévoir un contrôle qualité complet avant mise en vente"]

    rationale_by_decision = {
        "RESALE_DIRECT": "Marge ≥ 50 € : vente directe sans remise en état.",
        "RECONDITION": "Marge ≥ 20 € : reconditionnement avant revente.",
        "RECYCLE": "Marge < 20 € : recyclage via la filière D3E.",
    }

    return {
        "product_id": str(request.get("productId") or ""),
        "title": title,
        "description": description,
        "highlights": highlights,
        "attention_points": attention_points,
        "decision": decision,
        "decision_rationale": rationale_by_decision.get(decision, ""),
        "recommended_channels": channels,
    }

# ══════════════════════════════════════════════════════════════════
# AI FAULT / DRIFT ALERT — banner threshold counter
# ══════════════════════════════════════════════════════════════════
def assess_drift(reviews, max_faults: int, price_threshold_pct: int, window_days: int,
                 grade_drift_enabled: bool = True, price_drift_enabled: bool = True) -> dict:
    """Compute drift counters from a list of reviewed products (pure logic).

    Grade changes only count toward the alert when `grade_drift_enabled` is set;
    price deviations only when `price_drift_enabled` is set. Counters are always
    computed so the UI can display them regardless of toggle state.
    """
    grade_changes = defect_changes = price_drifts = 0
    for r in reviews:
        drift = r.get("model_drift") or {}
        if drift.get("grade_changed"):
            grade_changes += 1
        if drift.get("defects_changed"):
            defect_changes += 1
        error_eur = drift.get("pricing_error_eur") or 0
        base_price = (r.get("admin_review") or {}).get("market_price")
        if base_price:
            pct = abs(error_eur) / base_price * 100
            if pct > price_threshold_pct:
                price_drifts += 1

    _MIN = datetime.min.replace(tzinfo=timezone.utc)
    recent = []
    for r in sorted(reviews, key=lambda x: x.get("reviewed_at") or _MIN, reverse=True)[:10]:
        recent.append({
            "id": str(r["_id"]),
            "brand": r.get("brand"),
            "model": r.get("model"),
            "grade": (r.get("admin_review") or {}).get("grade"),
            "reviewed_at": (r.get("reviewed_at") or _MIN).isoformat(),
            "model_drift": r.get("model_drift"),
        })

    total_faults = len(reviews)
    reportable_grade = grade_changes if grade_drift_enabled else 0
    reportable_price = price_drifts if price_drift_enabled else 0
    return {
        "window_days": window_days,
        "evaluations": total_faults,
        "grade_changes": grade_changes,
        "defect_changes": defect_changes,
        "price_drifts": price_drifts,
        "max_faults": max_faults,
        "price_threshold_pct": price_threshold_pct,
        "grade_drift_enabled": grade_drift_enabled,
        "price_drift_enabled": price_drift_enabled,
        "alert": reportable_grade >= max_faults or reportable_price >= max_faults,
        "recent": recent,
    }


@app.get("/api/stats/drift", tags=["admin"])
async def get_drift_stats(window_days: int = 30, _admin: dict = Depends(require_admin)):
    """Count model corrections since the admin flag was last reviewed and compare
    them against the admin-configured max-AI-faults threshold (maxAIFaults)."""
    user = await users_collection.find_one({"email": _admin["sub"]})
    prefs = (user or {}).get("preferences", {})
    max_faults = int(prefs.get("maxAIFaults", 10) or 10)
    price_threshold_pct = int(prefs.get("driftThreshold", 15) or 15)
    grade_drift_enabled = bool(prefs.get("gradeDriftAlert", True))
    window_days = max(1, min(window_days, 365))
    since = datetime.now(timezone.utc) - timedelta(days=window_days)

    cursor = products_collection.find(
        {"model_drift": {"$exists": True, "$ne": None}, "reviewed_at": {"$gte": since}}
    )
    reviews = await cursor.to_list(length=1000)

    return assess_drift(reviews, max_faults, price_threshold_pct, window_days,
                        grade_drift_enabled=grade_drift_enabled)
