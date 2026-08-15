# Architecture

This document describes the Platana microservice architecture, its services,
ports, and the main data flows.

---

## 1. Overview

Platana is built as a set of independent FastAPI microservices orchestrated by
Docker Compose. A Traefik reverse proxy is the single entry point; only the
Angular frontend and the main API are exposed to clients.

```
                    ┌─────────────────────────────────────────┐
   Client ─────────▶│  Traefik (:8081 → host port 80)         │
                    │  • Host(localhost)           → frontend │
                    │  • Host(localhost) && /api/* → main     │
                    │  • PathPrefix(/mlflow)       → mlflow   │
                    └─────────────────────────────────────────┘
```

All internal services join the external `platana-shared-network` and the
compose `default` network. MongoDB, Redis and MLflow expose **no host port** in
production configuration (MongoDB exposes `27017` locally for debugging).

---

## 2. Services

| Service | Port | Image | Responsibility |
|---|---|---|---|
| `frontend` | 80 (nginx) | `Dockerfile.frontend` | Angular SPA |
| `main-service` | 8003 | `Dockerfile.main` | Auth, products, Dify eval, admin review, PDF reports, dashboard stats, publication proxy, training job proxy |
| `orchestrator` | 8000 | `Dockerfile.orchestrator` | CV→Pricing→GenAI pipeline, OR-Tools logistics, Shopify publication |
| `cv-service` | 8001 | `Dockerfile.cv` | ONNX visual grading (A–D) + defect detection |
| `pricing-service` | 8002 | `Dockerfile.pricing` | XGBoost resale price prediction, Redis cache |
| `training-service` | 8010 | `Dockerfile.training` | Guarded continuous retraining (pricing / CV), model promotion |
| `mongodb` | 27017 | `mongo:7.0` | Primary datastore |
| `redis` | 6379 (internal) | `redis:7.4-alpine` | Pricing prediction cache |
| `mlflow` | 5000 (internal) | `Dockerfile.mlflow` | Experiment tracking, model metrics |
| `traefik` | 8081 → 80 | `traefik:latest` | Reverse proxy, TLS termination point |
| `docker-proxy` | — | `tecnativa/docker-socket-proxy` | Secured Docker socket access for Traefik |

---

## 3. Data flow — product evaluation

### 3.1 Evaluation path (production, Dify-based)

1. **Frontend → main-service** `POST /api/products/upload`
   (multipart: brand, model, year, original_price, files).
2. **main-service** saves the images under `data/uploads/` and inserts the
   product document with status `PENDING_EVALUATION`.
3. **main-service → Dify** uploads each image and runs the *eval workflow*.
4. **Dify** returns structured outputs (`grade`, `defects`, `market_price`,
   `refurb_cost`, `profit`, `decision`, `title`, `description`).
5. **main-service** validates the payload against `AIPredictions` and sets the
   product status to `REVIEW_READY`.
6. **main-service** generates the **PDF evaluation report** into
   `data/reports/<product_id>.pdf` and stores the relative path in
   `report_path`.
7. **Frontend** shows the product in the admin validation queue.

### 3.2 Classic pipeline (orchestrator)

`POST /process` (multipart) runs the microservice chain directly:

```
CV Service (/grade) ──▶ grade + defects
Pricing Service (/predict) ──▶ market price
Decision Engine ──▶ RESALE_DIRECT / RECONDITION / RECYCLE
GenAI (Groq) ──▶ product listing (title, description, highlights, warnings)
```

This path is used by local tooling and tests; the production frontend uses the
Dify path above.

### 3.3 Dify integration (external Compose project)

Dify runs as a **separate Docker Compose project** (its own directory, own
networks) and is **not part of** `docker-compose.yaml`. The two stacks are
bridged over a shared, manually-created external Docker network:

```
Platana (docker-compose.yaml)          Dify (dify-main/docker)
  main-service ──────────────────────▶ api:5001/v1   (eval/publish workflows)
  orchestrator ─┐                        │  api, worker ─┐
  cv-service    ├─ platana-shared-network│  (also on:     ├─ docker_default
  pricing-service ── network ────────────┘   ssrf_proxy,  │
  mongodb       ┘                            default)     └─ platana-shared-network
```

- **Shared network** `platana-shared-network` is created once with
  `docker network create platana-shared-network` and declared `external: true`
  in both Compose files. Platana's `main-service`, `orchestrator`,
  `cv-service`, `pricing-service` and `mongodb` are attached; on the Dify side
  only the `api` and `worker` services are attached.
- **Entry point:** `main-service` calls `http://api:5001/v1` (Dify API service
  name + port resolved over the shared network). This is set with
  `DIFY_API_URL=http://api:5001/v1` in Platana's `.env`.
- **SSRF proxy:** Dify's `.env` was relaxed so its workflows can reach the
  Platana microservices — `SSRF_PROXY_ALLOW_PRIVATE_DOMAINS` includes
  `orchestrator,cv-service,pricing-service,api,localhost,127.0.0.1` and
  `SSRF_PROXY_ALLOW_PRIVATE_IPS` covers the private ranges. (To fully bypass
  the proxy, clear `SSRF_PROXY_HTTP_URL` / `SSRF_PROXY_HTTPS_URL`.)

See [`docs/RUNBOOK.md`](RUNBOOK.md) §3 for the exact steps and
[`docs/DEPLOYMENT.md`](DEPLOYMENT.md) §3 for the environment variables.

### 3.4 Admin AI tool proxies

The admin UI exposes three dedicated pages that call the internal microservices
through `main-service` proxies (all `ADMIN`-only):

| Page | Proxy | Target |
|---|---|---|
| Grading | `POST /api/cv/grade` | `cv-service /grade` |
| Pricing | `POST /api/pricing/predict` | `pricing-service /predict` |
| Product sheet | `POST /api/sheet/generate` | local deterministic template (same decision thresholds as the pipeline) |

---

## 4. Data flow — admin review & closed loop

```
Admin edits values (grade, price, cost, defects, title, description)
      │
      ▼
main-service PATCH /api/products/{id}/review
      │
      ├─▶ normalize defects (shared catalog)
      ├─▶ compute model_drift (grade/defects/price deltas vs AI)
      ├─▶ regenerate PDF report (now reflects admin truth)
      ├─▶ upsert labelled sample → pricing_training_samples (MongoDB)
      ├─▶ export first image + annotation → data/processed/... (CV retraining)
      └─▶ optional: PATCH publish → Dify publish workflow → Shopify URL
```

Drift stats (`GET /api/stats/drift`) aggregate `model_drift` records over a
time window and compare correction counts against the admin threshold
(`maxAIFaults` preference) to raise the alert banner.

---

## 5. Continuous training (closed loop)

1. `scripts/continuous_train.py pricing|cv` (or admin-triggered job via
   `training-service`).
2. Pricing: snapshots MongoDB `pricing_training_samples`, trains XGBoost,
   logs to MLflow, **promotes only if MAPE improves by ≥ 0.05**.
3. CV: continues from the active multitask model on the expanded processed
   dataset, logs to MLflow, **promotes only if macro-F1 improves by ≥ 0.002**.
4. On promotion, immutable artifacts are written to
   `models/*/checkpoints/versions/<id>/` and a pointer (`latest.json`) is
   atomically updated.
5. The internal training service calls `POST /internal/reload` on `cv-service`
   so the promoted ONNX model is hot-reloaded (HMAC-authenticated with
   `TRAINING_SERVICE_TOKEN`).

See [`docs/MLOPS.md`](MLOPS.md) for details.

---

## 6. Model versioning

All models are **immutable, versioned, and pointer-selected**:

- `models/pricing/checkpoints/latest.json` → `model.pkl` + `feature_engineer.pkl`
- `models/cv/checkpoints/latest.json` → production ONNX model
- `models/cv/checkpoints/latest_backbone.json` → backbone (training)
- `models/cv/checkpoints/latest_training.json` → latest PyTorch checkpoint

`resolve_latest_artifact()` in `models/artifacts.py` resolves pointers, falling
back to a legacy path when no version has ever been promoted.

---

## 7. Caching & data persistence

- **Redis**: pricing predictions, keyed by every validated request field + a
  fingerprint of the model, feature engineer, and feature code (auto-invalidation
  on retraining). See `build_pricing_cache_key()`.
- **MongoDB**: products, users, workshops, product catalog, pricing training
  samples.
- **Volumes (compose)**:
  - `mongo-data` → `/data/db`
  - `redis-data` → `/data`
  - `mlflow-data` → `/mlflow`
  - `uploads-data` → `/app/data/uploads` (main-service rw, training-service ro)
  - `./data/processed` → training-service (CV exports)
  - `./data/reports` → main-service (PDF evaluation reports)

---

## 8. Security model

- **JWT** (HS256) issued by main-service; `HTTPBearer` guards every protected
  endpoint; admin endpoints require `role == "ADMIN"`.
- **Resource ownership**: a user may only access their own products; admins may
  access everything.
- **Image/report serving** is path-validated (`_resolve_image_path`,
  `_resolve_report_path`) to prevent path traversal outside `data/uploads` /
  `data/reports`.
- **Internal services** are not published to the host; training reload is
  HMAC-authenticated; MLflow is behind Traefik BasicAuth.
- **Simulation/mock fallbacks removed**: CV and pricing services now answer
  `503` when their model is not loaded instead of returning fabricated results;
  the GenAI sheet generator raises instead of producing mock copy.

---

## 9. Decision engine

Thresholds shared between the local pipeline and the orchestrator:

| Condition | Decision |
|---|---|
| `profit ≥ 50.0` | `RESALE_DIRECT` |
| `20.0 ≤ profit < 50.0` | `RECONDITION` |
| `profit < 20.0` | `RECYCLE` |

Refurbishment costs are taken from a fixed defect→cost table
(`screen_crack` 120 €, `back_glass_crack` 40 €, `battery_weak` 30 €,
`cosmetic_scratch` 15 €, `no_defect` 5 €). Consistency between the local
pipeline and orchestrator is guarded by `tests/test_pipeline_decisions.py`.
