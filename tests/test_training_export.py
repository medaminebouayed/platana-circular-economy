"""Unit tests for admin-review → training export helpers."""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

repo_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo_root / "api"))

from shared.training_export import (
    derive_decision,
    product_to_pricing_sample,
    export_cv_sample,
)


def test_derive_decision_thresholds():
    assert derive_decision("A", 200, 100) == "RESALE_DIRECT"
    assert derive_decision("B", 40, 10) == "RECONDITION"
    assert derive_decision("D", 10, 5) == "RECYCLE"


def test_product_to_pricing_sample_maps_admin_review():
    product = {
        "_id": "abc123",
        "brand": "Apple",
        "model": "iPhone 13",
        "category": "smartphone",
        "year": 2022,
        "original_price": 800,
    }
    review = {
        "grade": "B",
        "defects": ["screen_crack"],
        "market_price": 350,
        "refurb_cost": 80,
        "reviewed_at": datetime(2026, 1, 15, tzinfo=timezone.utc),
    }
    sample = product_to_pricing_sample(product, review)
    assert sample["sale_price"] == 350
    assert sample["source"] == "admin-review"
    assert sample["source_product_id"] == "abc123"
    assert sample["exact_defects"] == "screen_crack"
    assert sample["repair_cost"] == 80.0


def test_export_cv_sample_writes_annotation(tmp_path):
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    img = uploads / "photo.jpg"
    img.write_bytes(b"fake-image")

    processed = tmp_path / "processed"
    product = {
        "_id": "prod001",
        "status": "REVIEWED",
        "image_paths": [str(img)],
        "admin_review": {"grade": "C", "defects": ["screen_crack"]},
    }
    assert export_cv_sample(product, uploads_dir=uploads, processed_root=processed) is True

    found = False
    for split in ("train", "val"):
        ann_path = processed / f"annotations_{split}.json"
        if ann_path.is_file():
            data = json.loads(ann_path.read_text(encoding="utf-8"))
            if "prod001" in data:
                assert data["prod001"]["grade"] == "C"
                assert "screen_crack" in data["prod001"]["defects"]
                img = processed / "smartphone_grading" / split / "prod001" / "view_00.png"
                assert img.is_file()
                found = True
    assert found
