"""Internal asynchronous model-training runner.

It is not publicly exposed. The main API authenticates an admin and calls this
service using an internal token. Job state is persisted in MongoDB so the UI
can recover after refreshes or service restarts.
"""

import asyncio
import hmac
import os
import sys
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, Header, HTTPException
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel

repo_root = Path(__file__).resolve().parents[2]
load_dotenv(repo_root / ".env")

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    mongo_client.close()


app = FastAPI(title="Platana Internal Training Service", docs_url=None, redoc_url=None,
              lifespan=lifespan)
mongo_client = AsyncIOMotorClient(os.getenv("MONGO_URL", "mongodb://mongodb:27017"))
jobs = mongo_client.platana_circular_economy.training_jobs
SERVICE_TOKEN = os.getenv("TRAINING_SERVICE_TOKEN", "")
CV_SERVICE_URL = os.getenv("CV_SERVICE_URL", "http://cv-service:8001")
PRICING_SERVICE_URL = os.getenv("PRICING_SERVICE_URL", "http://pricing-service:8002")


async def _reload_cv_service() -> None:
    if not SERVICE_TOKEN:
        return
    try:
        import httpx
        async with httpx.AsyncClient(timeout=30.0) as client:
            res = await client.post(
                f"{CV_SERVICE_URL}/internal/reload",
                headers={"X-Training-Service-Token": SERVICE_TOKEN},
            )
            if res.status_code >= 400:
                print(f"[WARN] CV service reload failed: {res.status_code} {res.text}")
    except Exception as exc:
        print(f"[WARN] CV service reload unreachable: {exc}")


async def _reload_pricing_service() -> None:
    if not SERVICE_TOKEN:
        return
    try:
        import httpx
        async with httpx.AsyncClient(timeout=30.0) as client:
            res = await client.post(
                f"{PRICING_SERVICE_URL}/internal/reload",
                headers={"X-Training-Service-Token": SERVICE_TOKEN},
            )
            if res.status_code >= 400:
                print(f"[WARN] Pricing service reload failed: {res.status_code} {res.text}")
    except Exception as exc:
        print(f"[WARN] Pricing service reload unreachable: {exc}")


class TrainingJobRequest(BaseModel):
    model: str


def require_service_token(token: str | None) -> None:
    if not SERVICE_TOKEN or not token or not hmac.compare_digest(token, SERVICE_TOKEN):
        raise HTTPException(status_code=403, detail="Unauthorized internal training request")


def training_command(model: str) -> list[str]:
    if model == "pricing":
        return [sys.executable, "scripts/continuous_train.py", "pricing"]
    if model == "cv":
        return [sys.executable, "scripts/continuous_train.py", "cv"]
    raise HTTPException(status_code=422, detail="model must be pricing or cv")


async def run_job(job_id: str, model: str) -> None:
    await jobs.update_one(
        {"job_id": job_id},
        {"$set": {"status": "RUNNING", "started_at": datetime.now(timezone.utc)}},
    )
    environment = os.environ.copy()
    environment["PYTHONPATH"] = f"{repo_root}{os.pathsep}{repo_root / 'api'}"
    process = await asyncio.create_subprocess_exec(
        *training_command(model),
        cwd=repo_root,
        env=environment,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    output, _ = await process.communicate()
    text = output.decode("utf-8", errors="replace")
    status = "SUCCEEDED" if process.returncode == 0 else "FAILED"
    await jobs.update_one(
        {"job_id": job_id},
        {"$set": {
            "status": status,
            "finished_at": datetime.now(timezone.utc),
            "exit_code": process.returncode,
            "log_tail": text[-12000:],
        }},
    )
    if status == "SUCCEEDED":
        if model == "cv":
            await _reload_cv_service()
        elif model == "pricing":
            await _reload_pricing_service()


@app.post("/jobs", status_code=202)
async def create_job(
    request: TrainingJobRequest,
    background_tasks: BackgroundTasks,
    x_training_service_token: str | None = Header(default=None),
):
    require_service_token(x_training_service_token)
    command = training_command(request.model)
    existing = await jobs.find_one({"model": request.model, "status": {"$in": ["QUEUED", "RUNNING"]}})
    if existing:
        existing.pop("_id", None)
        return {"job": existing, "created": False}

    job = {
        "job_id": str(uuid.uuid4()),
        "model": request.model,
        "status": "QUEUED",
        "requested_at": datetime.now(timezone.utc),
        "command": command,
    }
    await jobs.insert_one(job)
    background_tasks.add_task(run_job, job["job_id"], request.model)
    job.pop("_id", None)
    return {"job": job, "created": True}


@app.get("/health")
async def health():
    await mongo_client.admin.command("ping")
    return {"status": "ok"}


@app.get("/jobs")
async def list_jobs(
    limit: int = 20,
    x_training_service_token: str | None = Header(default=None),
):
    require_service_token(x_training_service_token)
    limit = max(1, min(limit, 100))
    cursor = jobs.find({}, {"_id": 0}).sort("requested_at", -1).limit(limit)
    return {"items": await cursor.to_list(length=limit)}
