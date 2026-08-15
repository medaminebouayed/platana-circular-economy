import asyncio

from api.shared.catalog_seed import CATALOG_ENTRIES, ensure_product_catalog


class _FakeCollection:
    def __init__(self, count: int = 0):
        self.count = count
        self.docs = {}

    async def count_documents(self, _filter):
        return self.count

    async def update_one(self, query, update, upsert=False):
        key = (query["brand"], query["model"])
        self.docs[key] = update["$set"]
        if self.count == 0:
            self.count = len(self.docs)


def test_ensure_product_catalog_seeds_when_empty():
    collection = _FakeCollection(count=0)
    inserted = asyncio.run(ensure_product_catalog(collection))
    assert inserted == len(CATALOG_ENTRIES)
    assert len(collection.docs) == len(CATALOG_ENTRIES)


def test_ensure_product_catalog_skips_when_populated():
    collection = _FakeCollection(count=5)
    inserted = asyncio.run(ensure_product_catalog(collection))
    assert inserted == 0
    assert len(collection.docs) == 0
