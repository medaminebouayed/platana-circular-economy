"""Seed product_catalog in MongoDB when empty (Docker startup).

Mirrors the distinct brand/model rows from models/pricing/prepare_pricing_data.py
so the user portal brand/model selector works without a manual seed script.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Same product universe as generate_market_dataset()
CATALOG_ENTRIES = [
    {"brand": "Apple", "model": "iPhone 13", "category": "smartphone", "original_price": 800},
    {"brand": "Apple", "model": "iPhone 11", "category": "smartphone", "original_price": 500},
    {"brand": "Samsung", "model": "Galaxy S21", "category": "smartphone", "original_price": 600},
    {"brand": "Apple", "model": "MacBook Pro 2020", "category": "laptop", "original_price": 1500},
    {"brand": "Dell", "model": "Dell XPS 13", "category": "laptop", "original_price": 1200},
    {"brand": "Apple", "model": "iPad Air", "category": "tablet", "original_price": 600},
    {"brand": "Sony", "model": 'Bravia 50"', "category": "tv", "original_price": 800},
]


async def ensure_product_catalog(collection) -> int:
    """Insert catalog rows when the collection is empty. Returns rows upserted."""
    count = await collection.count_documents({})
    if count > 0:
        return 0

    logger.info("product_catalog is empty — seeding default pricing catalog (%d items)...", len(CATALOG_ENTRIES))
    for item in CATALOG_ENTRIES:
        await collection.update_one(
            {"brand": item["brand"], "model": item["model"]},
            {"$set": {**item, "source": "startup-seed"}},
            upsert=True,
        )
    logger.info("product_catalog seeded successfully.")
    return len(CATALOG_ENTRIES)
