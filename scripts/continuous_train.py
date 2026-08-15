"""Controlled continuous-training entrypoint for Pricing and CV.

Run this manually, with Windows Task Scheduler, or from CI. It never overwrites
artifacts: each run creates a candidate version and only promotes it when the
configured validation metric improves over the active version.
"""

import argparse
import asyncio
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

repo_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo_root))
sys.path.insert(0, str(repo_root / "api"))


async def _prepare_pricing_training_data(min_samples: int) -> None:
    """Ensure admin-reviewed products are in pricing_training_samples before export."""
    load_dotenv(repo_root / ".env")
    client = AsyncIOMotorClient(os.getenv("MONGO_URL", "mongodb://localhost:27017"))
    try:
        db = client.platana_circular_economy
        from shared.training_export import export_all_reviewed_pricing
        count = await export_all_reviewed_pricing(db.products, db.pricing_training_samples)
        if count:
            print(f"[INFO] Synced {count} admin-reviewed pricing samples into MongoDB.")
    finally:
        client.close()


async def _prepare_cv_training_data() -> int:
    """Export admin-reviewed product images/labels into CV processed dataset."""
    load_dotenv(repo_root / ".env")
    client = AsyncIOMotorClient(os.getenv("MONGO_URL", "mongodb://localhost:27017"))
    try:
        db = client.platana_circular_economy
        from shared.training_export import export_all_reviewed_cv
        uploads = repo_root / "data" / "uploads"
        return await export_all_reviewed_cv(db.products, uploads_dir=uploads)
    finally:
        client.close()


def active_version(checkpoint_dir: Path, pointer_name: str = "latest.json") -> str | None:
    try:
        return json.loads((checkpoint_dir / pointer_name).read_text(encoding="utf-8"))["version_id"]
    except (OSError, ValueError, KeyError):
        return None


async def export_pricing_snapshot(min_samples: int) -> Path:
    load_dotenv(repo_root / ".env")
    client = AsyncIOMotorClient(os.getenv("MONGO_URL", "mongodb://localhost:27017"))
    try:
        records = await client.platana_circular_economy.pricing_training_samples.find(
            {}, {"_id": 0, "source_row": 0, "source": 0, "source_product_id": 0}
        ).to_list(length=None)
    finally:
        client.close()
    if len(records) < min_samples:
        raise RuntimeError(
            f"Only {len(records)} pricing samples are available; need at least {min_samples}. "
            "Run scripts/seed_pricing_catalog.py first or collect more labelled sales."
        )
    snapshot_dir = repo_root / "data" / "processed" / "training_snapshots"
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    snapshot = snapshot_dir / f"pricing-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.csv"
    pd.DataFrame(records).to_csv(snapshot, index=False)
    return snapshot


def run(command: list[str], dry_run: bool) -> None:
    print("[RUN]", " ".join(command))
    if not dry_run:
        subprocess.run(command, cwd=repo_root, check=True)


def train_pricing(args) -> None:
    asyncio.run(_prepare_pricing_training_data(args.min_samples))
    snapshot = asyncio.run(export_pricing_snapshot(args.min_samples))
    checkpoint_dir = repo_root / "models" / "pricing" / "checkpoints"
    previous = active_version(checkpoint_dir)
    run([
        sys.executable, "-m", "models.pricing.train", "--data", str(snapshot),
        "--promotion-policy", "if-better", "--min-mape-improvement", str(args.min_mape_improvement),
    ], args.dry_run)
    current = active_version(checkpoint_dir)
    print(f"[RESULT] Pricing active version: {current or previous}; promoted={current != previous}")


def train_cv(args) -> None:
    exported = asyncio.run(_prepare_cv_training_data())
    if exported:
        print(f"[INFO] Exported {exported} admin-reviewed CV samples before training.")
    checkpoint_dir = repo_root / "models" / "cv" / "checkpoints"
    previous = active_version(checkpoint_dir, "latest_training.json")
    run([
        sys.executable, "-m", "models.cv.train", "--mode", "continue",
        "--promotion-policy", "if-better", "--min-f1-improvement", str(args.min_f1_improvement),
    ], args.dry_run)
    current = active_version(checkpoint_dir, "latest_training.json")
    if not args.dry_run and current and current != previous:
        run([sys.executable, "scripts/export_cv_onnx.py", "--version-id", current], False)
    print(f"[RESULT] CV active training version: {current or previous}; promoted={current != previous}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run guarded continuous training.")
    parser.add_argument("model", choices=["pricing", "cv"])
    parser.add_argument("--min-samples", type=int, default=500)
    parser.add_argument("--min-mape-improvement", type=float, default=0.05)
    parser.add_argument("--min-f1-improvement", type=float, default=0.002)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    train_pricing(args) if args.model == "pricing" else train_cv(args)


if __name__ == "__main__":
    main()
