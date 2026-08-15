"""Guard-rails for the internal training-service job endpoints.

Regression test for the 500 on POST /jobs: pymongo's insert_one() mutates the
input document by adding an ObjectId "_id" key, and returning that dict made
FastAPI fail with "TypeError: 'ObjectId' object is not iterable".
"""

import asyncio
import sys
from pathlib import Path

repo_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo_root / "api"))

from fastapi import BackgroundTasks

from training_service.main import TrainingJobRequest, create_job


class FakeInsertResult:
    inserted_id = "66f0abc0-0000-0000-0000-000000000000"


class FakeJobs:
    def __init__(self, existing=None):
        self.existing = existing
        self.inserted = None

    async def find_one(self, query):
        return self.existing

    async def insert_one(self, doc):
        doc["_id"] = "mongo-added-objectid"
        self.inserted = doc
        return FakeInsertResult()


def _run(coro):
    return asyncio.run(coro)


def test_create_job_new_job_does_not_leak_objectid(monkeypatch):
    from training_service import main as ts
    monkeypatch.setattr(ts, "SERVICE_TOKEN", "test-token")
    monkeypatch.setattr(ts, "jobs", FakeJobs(existing=None))
    tasks = BackgroundTasks()
    res = _run(create_job(
        TrainingJobRequest(model="cv"),
        tasks,
        x_training_service_token="test-token",
    ))
    assert res["created"] is True
    assert res["job"]["job_id"]
    assert res["job"]["model"] == "cv"
    assert res["job"]["status"] == "QUEUED"
    assert "_id" not in res["job"]
    assert tasks is not None


def test_create_job_existing_job_strips_objectid(monkeypatch):
    from training_service import main as ts
    monkeypatch.setattr(ts, "SERVICE_TOKEN", "test-token")
    existing = {
        "_id": "some-objectid",
        "job_id": "job-1",
        "model": "pricing",
        "status": "QUEUED",
        "requested_at": "2026-08-14T12:00:00Z",
        "command": ["python", "scripts/continuous_train.py", "pricing"],
    }
    monkeypatch.setattr(ts, "jobs", FakeJobs(existing=existing))
    res = _run(create_job(
        TrainingJobRequest(model="pricing"),
        BackgroundTasks(),
        x_training_service_token="test-token",
    ))
    assert res["created"] is False
    assert res["job"]["job_id"] == "job-1"
    assert "_id" not in res["job"]
