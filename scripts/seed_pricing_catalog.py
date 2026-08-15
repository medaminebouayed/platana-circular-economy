"""Generate deterministic pricing examples and seed them into MongoDB.

The catalog is used by the searchable brand/model selector. Training examples
are stored separately so a later pricing training run can export them without
mixing application data with model artifacts.
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

repo_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo_root))
from models.pricing.prepare_pricing_data import generate_market_dataset


async def seed(dataset_path: Path, regenerate: bool) -> None:
    load_dotenv(repo_root / ".env")
    if regenerate or not dataset_path.is_file():
        generate_market_dataset(output_path=dataset_path)
    dataframe = pd.read_csv(dataset_path)
    required = {"brand", "model", "category", "original_price", "sale_price"}
    missing = required - set(dataframe.columns)
    if missing:
        raise ValueError(f"Dataset misses required columns: {sorted(missing)}")

    client = AsyncIOMotorClient(os.getenv("MONGO_URL", "mongodb://localhost:27017"))
    db = client.platana_circular_economy
    try:
        catalog = db.product_catalog
        samples = db.pricing_training_samples
        await catalog.create_index([("brand", 1), ("model", 1)], unique=True)
        await samples.create_index("source_row", unique=True)

        catalog_rows = (
            dataframe[["brand", "model", "category", "original_price"]]
            .groupby(["brand", "model", "category"], as_index=False)["original_price"].median()
            .to_dict("records")
        )
        for item in catalog_rows:
            await catalog.update_one(
                {"brand": item["brand"], "model": item["model"]},
                {"$set": {**item, "source": "synthetic-pricing-dataset"}},
                upsert=True,
            )

        for index, record in enumerate(dataframe.to_dict("records")):
            record["source_row"] = index
            record["source"] = "synthetic-pricing-dataset"
            await samples.update_one({"source_row": index}, {"$set": record}, upsert=True)

        print(f"[OK] Seeded {len(catalog_rows)} catalog entries and {len(dataframe)} pricing samples.")
    finally:
        client.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="data/processed/pricing_dataset.csv")
    parser.add_argument("--regenerate", action="store_true", help="Regenerate the deterministic synthetic dataset first")
    args = parser.parse_args()
    asyncio.run(seed(repo_root / args.dataset, args.regenerate))


if __name__ == "__main__":
    main()
