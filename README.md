# Platana — Circular Economy Intelligence

**Refurbishment & Resale Engine** for returned/SAV electronics.

Platana is an end-to-end platform that automatically evaluates the condition of a
returned product from photos (CV grading), predicts its optimal resale price
(ML pricing), generates a ready-to-publish product listing (GenAI), routes it to
the best refurbishment workshop (combinatorial optimisation), and lets an admin
review and publish every decision to marketplaces such as Shopify.

| Component | Stack |
|---|---|
| Frontend | Angular 16.2 (NgModule-based SPA, custom i18n FR/EN) |
| Backend | Python 3.12.10 · FastAPI microservices |
| ML Inference | PyTorch→ONNX (CV grading) · XGBoost (pricing) |
| GenAI | Groq (Llama 3.3) product listing generation |
| Data | MongoDB (Motor) · Redis (pricing cache) · MLflow (experiment tracking) |
| Infra | Docker Compose · Traefik reverse proxy · Nginx |

---

## Features

- **AI product evaluation** — upload 1–5 photos; CV model grades the device (A–D)
  and detects defects; XGBoost predicts the market resale price; a decision engine
  returns `RESALE_DIRECT`, `RECONDITION`, or `RECYCLE`.
- **Product listing generation** — GenAI writes a French, SEO-optimised listing
  (title, description, highlights, warnings) from the technical defect list.
- **PDF evaluation report** — a professional A4 report is generated after every
  evaluation, stored on disk (`data/reports/`), referenced in MongoDB, and
  downloadable by the admin.
- **Admin review workflow** — the admin can correct the AI output (grade, price,
  cost, defects, title, description), reject products, re-evaluate them, and
  publish approved listings.
- **Closed-loop continuous learning** — admin-reviewed products become labelled
  training samples (pricing + CV) used by a guarded retraining pipeline.
- **Drift monitoring** — dashboard KPIs + an alert banner that fires when the
  number of admin corrections crosses the configured threshold.
- **Logistics optimisation** — OR-Tools SCIP solver allocates reconditionable
  products to workshops while maximising expected profit.
- **Marketplace publication** — one-click publish to Shopify (via Dify workflow
  or direct Shopify Admin API).

---

## Architecture at a glance

```
┌──────────┐      ┌───────────────┐      ┌──────────────────────────────┐
│ Angular  │─────▶│   Traefik     │─────▶│  main-service (8003)         │
│ Frontend │      │  (8081 → :80) │      │  auth · products · review    │
└──────────┘      └───────────────┘      │  Dify eval · reports · stats │
                                         └──────┬───────────────────────┘
                                                │ HTTP
                              ┌─────────────────┼─────────────────┐
                              ▼                 ▼                 ▼
                       orchestrator        training-service   mongodb · redis
                        (8000) · CV (8001)   (8010) · mlflow    (datastore)
                        · pricing (8002)     (5000)
```

Each microservice is a Docker container behind Traefik. Only `main-service`
and `frontend` are exposed to the outside world; everything else lives on an
internal network. See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for details.

---

## Quick start

### 1. Prerequisites

- Docker Desktop (or Docker Engine) with Compose v2
- A `.env` file (see [Configuration](#configuration))
- The **Dify** stack running on the shared `platana-shared-network`
  (see [RUNBOOK §3](docs/RUNBOOK.md#3-%C3%A9tape-0--r%C3%A9seau-partag%C3%A9--dify))

### 2. Start the stack

```powershell
docker compose up -d --build
```

Wait for all containers to be healthy, then open:

- **Frontend:** http://localhost:8081
- **API docs:** http://localhost:8081/api/docs
- **MLflow:** http://localhost:8081/mlflow (BasicAuth required)

### 3. Default accounts (seeded on first boot)

| Role  | Email                    | Password |
|-------|--------------------------|----------|
| Admin | `thomas.dubois@platana.fr` | `admin`  |
| User  | `user@example.com`        | `user`   |

> Change these in production — they are seeded only when MongoDB is empty.

### 4. Stop the stack

```powershell
docker compose down          # keeps volumes
docker compose down -v       # wipes MongoDB/Redis/MLflow/uploads volumes
```

---

## Configuration

Copy `.env.example` to `.env` and fill in the secrets:

| Variable | Purpose |
|---|---|
| `DIFY_API_URL`, `DIFY_EVAL_API_KEY`, `DIFY_PUBLISH_API_KEY` | Dify workflow endpoints for AI evaluation & publication |
| `GROQ_API_KEY` | Groq API key for GenAI listing generation |
| `SHOPIFY_STORE_URL`, `SHOPIFY_ACCESS_TOKEN` | Shopify store credentials |
| `MONGO_URL` | MongoDB connection string |
| `JWT_SECRET` | 256-bit secret used to sign JWTs (**change it**) |
| `TRAINING_SERVICE_TOKEN` | Shared secret between main-service and training-service |
| `MLFLOW_BASIC_AUTH_USERS` | htpasswd line protecting MLflow (`htpasswd -nbB admin '<pass>'`) |
| `REDIS_URL`, `PRICING_CACHE_TTL_SECONDS` | Redis cache for pricing predictions |
| `ALLOWED_ORIGINS` | Comma-separated CORS origins |

See [`.env.example`](.env.example) and [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md).

---

## Repository layout

```
├── api/                    # FastAPI microservices
│   ├── main_service/       #   public API: auth, products, review, reports, stats
│   ├── orchestrator/       #   pipeline orchestration (CV → Pricing → GenAI) + logistics
│   ├── cv_service/         #   ONNX visual grading & defect detection (8001)
│   ├── pricing_service/    #   XGBoost price prediction with Redis cache (8002)
│   ├── training_service/   #   guarded continuous retraining worker (8010)
│   ├── dify/               #   Dify workflow client used by main-service
│   └── shared/             #   schemas, models, defects, report PDF, training export
├── models/                 # ML code
│   ├── cv/                 #   training, inference, ONNX export
│   ├── pricing/            #   training, feature engineering, model
│   ├── genai/              #   Groq sheet generator + FPDF listing
│   └── artifacts.py        #   immutable version resolution (latest.json)
├── scripts/                # seed catalog, continuous training, dummy data
├── configs/                # YAML configs (cv_config.yaml, ...)
├── frontend/               # Angular application
├── tests/                  # pytest suite (53 tests)
├── docs/                   # architecture, API, data model, deployment, MLOps, audit
└── data/                   # uploads, reports, processed datasets (gitignored)
```

---

## Documentation

| Document | Contents |
|---|---|
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Services, ports, data flow, sequence diagrams |
| [`docs/API.md`](docs/API.md) | Full REST endpoint reference |
| [`docs/DATA_MODEL.md`](docs/DATA_MODEL.md) | MongoDB collections & document shapes |
| [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) | Docker Compose, volumes, networking, production notes |
| [`docs/MLOPS.md`](docs/MLOPS.md) | Model versions, MLflow, Redis, continuous training |
| [`docs/RUNBOOK.md`](docs/RUNBOOK.md) | **Step-by-step guide to run the whole app** (network + Dify + stack + demo) |
| [`docs/AUDIT.md`](docs/AUDIT.md) | Project scan: findings & fixes |
| [`Cahier_De_Charge.md`](Cahier_De_Charge.md) | Original specification (French) |

---

## Development

### Backend

```powershell
# Install the full local dev environment (venv recommended)
.\venv\Scripts\python.exe -m pip install -r requirements.txt

# Run the test suite
.\venv\Scripts\python.exe -m pytest

# Run a single service locally (from repo root)
.\venv\Scripts\python.exe -m uvicorn api.main_service.main:app --port 8003
```

### Frontend

```powershell
cd frontend
npm install
npm start            # dev server on :4200, proxies /api to :8003
npm run build        # production bundle
```

---

## Testing

The repository ships a `pytest` suite covering decision-engine thresholds,
drift statistics, pricing cache keys, defect normalisation, catalog seeding,
training exports, and CV config consistency:

```powershell
.\venv\Scripts\python.exe -m pytest -q
```

---

## License

Internal project — Platana. See [`Cahier_De_Charge.md`](Cahier_De_Charge.md).
