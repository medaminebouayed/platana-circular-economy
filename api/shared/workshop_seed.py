"""Seed default workshops in MongoDB when empty (Docker startup).

The ``workshops`` collection is the single source of truth at runtime: the
main service CRUD endpoints (``/api/logistics/workshops``) and the orchestrator
optimizer both read from MongoDB. This module only bootstraps an empty
database so the logistics UI has realistic data on first boot.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

DEFAULT_WORKSHOPS = [
    {
        "name": "Atelier Platana Nord", "city": "Lille", "region": "Hauts-de-France",
        "capacity": 200, "occupancy": 62, "avg_cost": 48.0, "distance": 230,
        "specialties": ["Smartphone", "Ordinateur", "Tablette"],
        "status": "available", "min_profit_threshold": 20.0, "max_items_per_batch": 10,
    },
    {
        "name": "Centre Reconditionnement Est", "city": "Strasbourg", "region": "Grand Est",
        "capacity": 350, "occupancy": 87, "avg_cost": 52.0, "distance": 490,
        "specialties": ["TV", "Electroménager", "Outillage"],
        "status": "busy", "min_profit_threshold": 30.0, "max_items_per_batch": 15,
    },
    {
        "name": "Hub Reconditionnement Sud", "city": "Lyon", "region": "Auvergne-Rhône-Alpes",
        "capacity": 280, "occupancy": 45, "avg_cost": 44.0, "distance": 460,
        "specialties": ["Smartphone", "Audio", "Console de jeux"],
        "status": "available", "min_profit_threshold": 20.0, "max_items_per_batch": 12,
    },
    {
        "name": "Site Atlantique", "city": "Nantes", "region": "Pays de la Loire",
        "capacity": 180, "occupancy": 95, "avg_cost": 58.0, "distance": 380,
        "specialties": ["Aspirateur", "Electroménager"],
        "status": "full", "min_profit_threshold": 40.0, "max_items_per_batch": 8,
    },
]


async def ensure_workshops(collection) -> int:
    """Seed default workshops only when the collection is empty.

    Existing documents (including admin CRUD deletions/edits) are never
    touched, so the database remains the source of truth. Returns 1 when
    seeded, 0 when the collection already had data.
    """
    count = await collection.count_documents({})
    if count > 0:
        return 0

    logger.info("workshops collection is empty — seeding %d default workshops...", len(DEFAULT_WORKSHOPS))
    await collection.insert_many(DEFAULT_WORKSHOPS)
    logger.info("Workshops seeded successfully.")
    return 1
