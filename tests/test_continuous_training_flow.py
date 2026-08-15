"""Guard-rails for the continuous-training data loop (pricing + CV)."""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

repo_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo_root / "api"))

import pandas as pd
import pytest

from shared.training_export import _cv_split, product_to_pricing_sample


def test_cv_split_is_deterministic_across_calls():
    assert _cv_split("prodA") == _cv_split("prodA")
    splits = {_cv_split(f"prod{i}") for i in range(200)}
    assert splits == {"train", "val"}


def test_product_to_pricing_sample_carries_admin_corrections():
    review = {
        "grade": "C",
        "defects": ["screen_crack", "battery_weak"],
        "market_price": 320.0,
        "refurb_cost": 85.0,
        "reviewed_at": datetime(2026, 8, 1, tzinfo=timezone.utc),
    }
    product = {
        "_id": "66f0abcd1234",
        "brand": "Apple", "model": "iPhone 13", "category": "smartphone",
        "year": 2021, "original_price": 800.0,
    }
    sample = product_to_pricing_sample(product, review)
    assert sample["sale_price"] == 320.0
    assert sample["grade"] == "C"
    assert "screen_crack" in sample["exact_defects"]
    assert sample["repair_cost"] == 85.0


def test_pricing_snapshot_fits_feature_engineer_schema():
    """The snapshot written by continuous_train must satisfy train.py + FeatureEngineer."""
    from models.pricing.features import FeatureEngineer
    from models.pricing.model import PricingModel

    rows = [
        product_to_pricing_sample(
            {"_id": f"p{i}", "brand": "Apple", "model": "iPhone 13",
             "category": "smartphone", "year": 2021, "original_price": 800.0},
            {"grade": g, "defects": d, "market_price": p, "refurb_cost": c,
             "reviewed_at": datetime(2026, 8, 1, tzinfo=timezone.utc)},
        )
        for i, (g, d, p, c) in enumerate([
            ("A", ["no_defect"], 600.0, 5.0),
            ("B", ["cosmetic_scratch"], 500.0, 15.0),
            ("C", ["screen_crack"], 320.0, 85.0),
            ("D", ["screen_crack", "battery_weak"], 200.0, 130.0),
        ])
    ]
    df = pd.DataFrame(rows)
    y = df["sale_price"]
    engineer = FeatureEngineer()
    feats = engineer.fit_transform(df, y)
    assert set(engineer.get_feature_names()) == set(FeatureEngineer.DEFECT_AWARE_FEATURE_NAMES)

    model = PricingModel(model_type="xgboost",
                         params={"n_estimators": 10, "max_depth": 2, "learning_rate": 0.1})
    model.fit(feats[engineer.get_feature_names()], y)
    pred = float(model.predict(feats[engineer.get_feature_names()].head(1))[0])
    assert pred > 0


@pytest.mark.skipif(
    __import__("importlib.util").util.find_spec("torchvision") is None,
    reason="torchvision not installed",
)
def test_cv_sample_roundtrip_through_grading_dataset(tmp_path):
    """Uploaded image + admin review → processed dataset → GradingDataset sample."""
    from PIL import Image as PILImage

    from models.cv.dataset import GradingDataset, get_val_transforms
    from shared.training_export import export_cv_sample

    uploads = tmp_path / "uploads"
    uploads.mkdir()
    img = uploads / "photo.jpg"
    PILImage.new("RGB", (224, 224), color=(64, 128, 200)).save(img, "JPEG")

    product = {
        "_id": "66f0abcd1234", "status": "REVIEWED",
        "image_paths": [str(img)],
        "admin_review": {"grade": "C", "defects": ["screen_crack"]},
    }
    processed = tmp_path / "processed"
    assert export_cv_sample(product, uploads_dir=uploads, processed_root=processed) is True

    split = _cv_split("66f0abcd1234")
    ann_path = processed / f"annotations_{split}.json"
    ann = json.loads(ann_path.read_text(encoding="utf-8"))
    assert ann["66f0abcd1234"]["grade"] == "C"
    assert "screen_crack" in ann["66f0abcd1234"]["defects"]

    ds = GradingDataset(processed / "smartphone_grading" / split, ann_path,
                        transform=get_val_transforms())
    image, grade_idx, defect_vec = ds[0]
    assert tuple(image.shape) == (3, 224, 224)
    assert int(grade_idx) == 2
    assert int(defect_vec[1]) == 1
