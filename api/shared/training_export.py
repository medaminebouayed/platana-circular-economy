"""Export admin-reviewed products into ML training datasets (pricing + CV)."""

from __future__ import annotations

import json
import shutil
import zlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from shared.defects import defects_to_exact_string, normalize_defect_list, to_cv_defects

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_UPLOAD_DIR = REPO_ROOT / "data" / "uploads"
CV_TRAIN_ROOT = REPO_ROOT / "data" / "processed" / "smartphone_grading" / "train"
CV_VAL_ROOT = REPO_ROOT / "data" / "processed" / "smartphone_grading" / "val"
CV_TRAIN_ANN = REPO_ROOT / "data" / "processed" / "annotations_train.json"
CV_VAL_ANN = REPO_ROOT / "data" / "processed" / "annotations_val.json"


def derive_decision(grade: str, market_price: float, refurb_cost: float) -> str:
    """Match RefurbDecisionEngine thresholds from models/pipeline.py."""
    profit = market_price - refurb_cost
    if profit >= 50.0:
        return "RESALE_DIRECT"
    if profit >= 20.0:
        return "RECONDITION"
    return "RECYCLE"


def _age_days_from_year(year: int | None) -> int:
    if not year:
        return 365 * 2
    return max(30, (datetime.now(timezone.utc).year - int(year)) * 365)


def product_to_pricing_sample(product: dict, review: dict) -> dict:
    """Build one pricing_training_samples document from a reviewed product."""
    defects = normalize_defect_list(review.get("defects", []))
    exact = defects_to_exact_string(defects)
    defect_count = len([d for d in defects if d != "no_defect"])
    original_price = float(product.get("original_price") or 0)
    market_price = float(review.get("market_price") or 0)
    refurb_cost = float(review.get("refurb_cost") or 0)
    reviewed_at = review.get("reviewed_at") or product.get("reviewed_at") or datetime.now(timezone.utc)
    if isinstance(reviewed_at, datetime):
        date_str = reviewed_at.strftime("%Y-%m-%d")
    else:
        date_str = str(reviewed_at)[:10]

    category = product.get("category") or "smartphone"
    return {
        "brand": product.get("brand", ""),
        "model": product.get("model", ""),
        "category": category,
        "grade": review.get("grade", "C"),
        "original_price": original_price,
        "sale_price": market_price,
        "age_days": _age_days_from_year(product.get("year")),
        "date": date_str,
        "market_avg_price": round(original_price * 0.6, 2) if original_price else 0.0,
        "repair_cost": round(refurb_cost, 2),
        "defect_count": defect_count,
        "exact_defects": exact,
        "source": "admin-review",
        "source_product_id": str(product.get("_id", product.get("id", ""))),
    }


async def upsert_pricing_training_sample(products_collection, samples_collection, product_id: str) -> bool:
    """Upsert admin-reviewed product into pricing_training_samples."""
    from bson import ObjectId

    oid = ObjectId(product_id)
    product = await products_collection.find_one({"_id": oid})
    if not product or not product.get("admin_review"):
        return False

    review = product["admin_review"]
    if product.get("status") not in ("REVIEWED", "PUBLISHED"):
        return False

    sample = product_to_pricing_sample(product, review)
    await samples_collection.update_one(
        {"source_product_id": sample["source_product_id"]},
        {"$set": sample},
        upsert=True,
    )
    await samples_collection.create_index("source_product_id", unique=True, sparse=True)
    return True


def _cv_split(product_id: str) -> str:
    """Deterministic 90/10 train/val split.

    Uses a CRC32 of the product id instead of ``hash()``, which is randomised
    per process in CPython and would otherwise move the same product between
    splits on every run (train/val data leakage).
    """
    return "val" if zlib.crc32(product_id.encode("utf-8")) % 10 == 0 else "train"


def export_cv_sample(
    product: dict,
    uploads_dir: Path | None = None,
    processed_root: Path | None = None,
) -> bool:
    """Copy product image + annotation into CV processed dataset."""
    review = product.get("admin_review")
    if not review:
        return False
    if product.get("status") not in ("REVIEWED", "PUBLISHED"):
        return False

    image_paths = product.get("image_paths") or []
    if not image_paths:
        return False

    uploads_dir = uploads_dir or DEFAULT_UPLOAD_DIR
    processed_root = processed_root or (REPO_ROOT / "data" / "processed")
    train_root = processed_root / "smartphone_grading" / "train"
    val_root = processed_root / "smartphone_grading" / "val"
    train_ann_path = processed_root / "annotations_train.json"
    val_ann_path = processed_root / "annotations_val.json"

    product_id = str(product.get("_id", product.get("id", "")))
    split = _cv_split(product_id)
    dest_root = val_root if split == "val" else train_root
    ann_path = val_ann_path if split == "val" else train_ann_path

    src = Path(image_paths[0])
    if not src.is_absolute():
        src = REPO_ROOT / src
    if not src.is_file():
        src = uploads_dir / Path(image_paths[0]).name
    if not src.is_file():
        return False

    prod_dir = dest_root / product_id
    prod_dir.mkdir(parents=True, exist_ok=True)
    dest_img = prod_dir / "view_00.png"
    shutil.copy2(src, dest_img)

    annotations: dict[str, Any] = {}
    if ann_path.is_file():
        annotations = json.loads(ann_path.read_text(encoding="utf-8"))

    cv_defects = to_cv_defects(review.get("defects", []))
    if cv_defects == ["no_defect"]:
        cv_defects = []

    annotations[product_id] = {
        "grade": review.get("grade", "C"),
        "defects": cv_defects,
    }
    ann_path.parent.mkdir(parents=True, exist_ok=True)
    ann_path.write_text(json.dumps(annotations, indent=2, ensure_ascii=False), encoding="utf-8")
    return True


async def export_all_reviewed_cv(products_collection, uploads_dir: Path | None = None) -> int:
    """Batch-export all reviewed products into CV training data."""
    cursor = products_collection.find({
        "status": {"$in": ["REVIEWED", "PUBLISHED"]},
        "admin_review": {"$exists": True},
        "image_paths.0": {"$exists": True},
    })
    count = 0
    async for product in cursor:
        if export_cv_sample(product, uploads_dir=uploads_dir):
            count += 1
    return count


async def export_all_reviewed_pricing(products_collection, samples_collection) -> int:
    """Batch-export all reviewed products into pricing_training_samples."""
    cursor = products_collection.find({
        "status": {"$in": ["REVIEWED", "PUBLISHED"]},
        "admin_review": {"$exists": True},
    })
    count = 0
    async for product in cursor:
        pid = str(product["_id"])
        if await upsert_pricing_training_sample(products_collection, samples_collection, pid):
            count += 1
    return count
