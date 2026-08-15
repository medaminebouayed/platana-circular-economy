"""Workshop seed + logistics cost helpers (main-service pure logic)."""

import sys
from pathlib import Path

repo_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo_root))
sys.path.insert(0, str(repo_root / "api"))

from shared.workshop_seed import DEFAULT_WORKSHOPS, ensure_workshops


class FakeCollection:
    def __init__(self, docs=None):
        self.docs = list(docs or [])

    async def count_documents(self, _filter):
        return len(self.docs)

    async def insert_many(self, docs):
        self.docs.extend(docs)
        return None


def test_ensure_workshops_seeds_when_empty():
    col = FakeCollection([])
    assert len(DEFAULT_WORKSHOPS) >= 1
    assert all(w.get("name") and w.get("distance") and w.get("capacity") for w in DEFAULT_WORKSHOPS)
    result = asyncio_run(col)
    assert result == 1
    assert len(col.docs) == len(DEFAULT_WORKSHOPS)


def asyncio_run(col):
    import asyncio
    return asyncio.run(ensure_workshops(col))


def test_ensure_workshops_does_not_touch_existing_data():
    existing = [{"name": "Atelier Custom", "distance": 10, "capacity": 5}]
    col = FakeCollection(existing)
    result = asyncio_run(col)
    assert result == 0
    assert len(col.docs) == 1
    assert col.docs[0]["name"] == "Atelier Custom"


def test_transport_cost_helpers():
    from api.main_service.main import (
        BASE_ESTIMATED_DELAY,
        CHANNEL_BY_DECISION,
        _transport_cost,
    )

    # Recondition cost scales with the real workshop distance
    assert _transport_cost("RECONDITION", 0) == 0.0
    assert _transport_cost("RECONDITION", 230) == round(230 * 0.12, 2)
    assert _transport_cost("RECONDITION", -50) == 0.0  # no negative cost

    # Fixed per-unit costs for direct resale / recycling
    assert _transport_cost("RESALE_DIRECT") == 8.0
    assert _transport_cost("RECYCLE") == 22.0

    assert CHANNEL_BY_DECISION["RECONDITION"] == "Leboncoin"
    assert CHANNEL_BY_DECISION["RESALE_DIRECT"] == "BackMarket"
    assert CHANNEL_BY_DECISION["RECYCLE"] == "Filière D3E"
    assert BASE_ESTIMATED_DELAY["RESALE_DIRECT"] == 2
