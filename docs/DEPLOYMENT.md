# Deployment

Docker Compose drives the entire stack. This document covers the runtime
topology, environment configuration, volumes, and production hardening notes.

---

## 1. Topology

`docker-compose.yaml` defines 11 services. See
[`docs/ARCHITECTURE.md`](ARCHITECTURE.md) for a service table.

```
Network: platana-shared-network (external), default (compose)
```

- Traefik listens on **host port 8081** and is the only exposed entry point.
- **MongoDB** also publishes **host port 27017** (debug only — remove in prod).
- Redis, MLflow and all microservices are internal.
- `platana-shared-network` is an **external** network created once with
  `docker network create platana-shared-network`; it also carries the **Dify**
  stack so `main-service` can reach `http://api:5001/v1` (see §8).
- `training-service` runs with `shm_size: 2g` — required by the PyTorch
  DataLoader workers during CV training (they crash without enough shared
  memory).

### Routing rules

| Host / Path | Target |
|---|---|
| `Host(localhost)` | `frontend` (nginx :80) |
| `Host(localhost)` + `/api` | `main-service` (:8003) |
| `PathPrefix(/mlflow)` | `mlflow` (:5000) |
| `Host(api.localhost)` | `main-service` (:8003) |

---

## 2. Images

Each service has its own Dockerfile to keep images small and rebuilds fast:

| Dockerfile | Base | Build context | Installs |
|---|---|---|---|
| `Dockerfile.main` | python:3.12-slim | repo root (copies `api/`, `.env`-free) | fastapi, uvicorn, motor, PyJWT, bcrypt, python-multipart, httpx, fpdf2 |
| `Dockerfile.orchestrator` | python:3.12-slim | repo root (copies `api/`, `models/genai/`) | fastapi, groq, fpdf2, ortools, joblib, requests |
| `Dockerfile.cv` | python:3.12-slim | `models/cv/` | fastapi, onnxruntime, pillow, numpy, matplotlib, pandas |
| `Dockerfile.pricing` | python:3.12-slim | `models/pricing/` | fastapi, xgboost, joblib, redis |
| `Dockerfile.training` | python:3.12-slim | `models/cv/` | pandas, pymongo, xgboost, torch, MLflow client |
| `Dockerfile.mlflow` | python:3.12-slim | repo root | mlflow, pymongo |
| `Dockerfile.frontend` | node:20 → nginx | `frontend/` | Angular build output |

The `api/shared` package is copied into every service image, so shared schemas,
models and the PDF report generator are available everywhere (only main-service
imports the PDF generator, which is why fpdf2 is only a main-service
dependency).

> **Note:** images are built without the repository `.env` — secrets must be
> provided at runtime via Compose (see below).

---

## 3. Environment configuration

Copy `.env.example` → `.env` and fill in secrets before first boot:

```powershell
Copy-Item .env.example .env
```

Key variables (full list in `.env.example`):

| Variable | Required | Notes |
|---|---|---|
| `DIFY_API_URL`, `DIFY_EVAL_API_KEY`, `DIFY_PUBLISH_API_KEY` | yes (eval) | Dify workflow credentials. `DIFY_API_URL=http://api:5001/v1` (Dify's API service resolved over `platana-shared-network` — see §8) |
| `GROQ_API_KEY` | yes (GenAI) | Used by orchestrator listing generation |
| `SHOPIFY_STORE_URL`, `SHOPIFY_ACCESS_TOKEN` | yes (publish) | Shopify Admin API |
| `MONGO_URL` | yes | `mongodb://mongodb:27017/platana` inside compose |
| `JWT_SECRET` | yes | **Change it.** ≥ 32 random bytes, base64 |
| `TRAINING_SERVICE_TOKEN` | yes | Shared HMAC secret main↔training |
| `MLFLOW_BASIC_AUTH_USERS` | yes | htpasswd line: `htpasswd -nbB admin '<pass>'` |
| `REDIS_URL` | no | Defaults to `redis://redis:6379/0` |
| `PRICING_CACHE_TTL_SECONDS` | no | Default `300` |
| `ALLOWED_ORIGINS` | no | CORS origins, comma-separated |

Services receive their configuration through Compose `environment:` /
`env_file:`. **Never commit `.env`** — it is gitignored.

---

## 4. Data & volumes

| Volume / bind | Mount | Services |
|---|---|---|
| `mongo-data` | `/data/db` | mongodb |
| `redis-data` | `/data` | redis |
| `mlflow-data` | `/mlflow` | mlflow |
| `uploads-data` | `/app/data/uploads` | main-service (rw), training-service (ro) |
| `./data/processed` | `/app/data/processed` | training-service |
| `./data/reports` | `/app/data/reports` | main-service |

`uploads-data` being shared read-only with `training-service` lets CV
retraining read the original photos of admin-validated products.

> PDF reports persist in `./data/reports` on the host — back this directory up
> or move it to a dedicated volume in production.

---

## 5. Startup & lifecycle

```powershell
docker compose up -d --build        # build + start
docker compose ps                   # health status
docker compose logs -f main-service # follow a service
docker compose down                 # stop, keep volumes
docker compose down -v              # stop + wipe volumes (seeds re-run)
```

On first boot, `mongodb` runs `./scripts/mongo-init` (collection/user seeds)
and `main-service` seeds the admin account + product catalog when the DB is
empty.

---

## 6. Production hardening checklist

- [ ] Replace the seeded `JWT_SECRET`, admin/user demo passwords, and
      `TRAINING_SERVICE_TOKEN`.
- [ ] Set `MLFLOW_BASIC_AUTH_USERS` (protects the MLflow UI).
- [ ] Stop publishing MongoDB host port `27017`; keep the database on an
      internal network or a managed Mongo.
- [ ] Remove or restrict `docker-proxy` access (currently read-only socket
      needed by Traefik for dynamic service discovery).
- [ ] Put HTTPS in front of Traefik (TLS + `--certificatesresolvers` config).
- [ ] Set `ALLOWED_ORIGINS` to the real frontend origin(s).
- [ ] Add a monitoring/health dashboard (Traefik metrics, `GET /health` on
      every service).
- [ ] Schedule backups of `mongo-data`, `mlflow-data`, `uploads-data`, and
      `data/reports`.
- [ ] Run `docker compose config --quiet` in CI to validate Compose files.

---

## 7. Local development (no Docker)

```powershell
# backend (repo root, venv active)
.\venv\Scripts\python.exe -m uvicorn api.main_service.main:app --port 8003
.\venv\Scripts\python.exe -m uvicorn api.orchestrator.main:app --port 8000
# ... repeat per service (cv 8001, pricing 8002, training 8010)

# frontend
cd frontend
npm install
npm start        # http://localhost:4200, proxies /api → http://localhost:8003
```

Frontend `src/environments/environment.development.ts` sets
`apiUrl = 'http://localhost:8003/api'`; the production build is served by
Traefik with the `/api` route rewritten to main-service.

---

## 8. Dify integration (external stack)

Dify is a **separate Compose project** (e.g. `C:\Users\amine\OneDrive\Desktop\dify-main\docker`),
not part of this `docker-compose.yaml`. The two stacks are bridged over the
shared external network so `main-service` can run the Dify eval/publish
workflows.

### 8.1 Shared network

```powershell
docker network create platana-shared-network
```

Declared `external: true` in both Compose files. On the Platana side,
`main-service`, `orchestrator`, `cv-service`, `pricing-service` and `mongodb`
are attached. On the Dify side, the `api` and `worker` services must be
attached too (edit `…\dify-main\docker\docker-compose.yaml`):

```yaml
services:
  api:
    networks: [ssrf_proxy_network, default, platana-shared-network]
  worker:
    networks: [ssrf_proxy_network, default, platana-shared-network]

networks:
  platana-shared-network:
    external: true
```

### 8.2 Dify `.env` — SSRF proxy relaxed

To let Dify's workflows reach the Platana microservices over the shared
network, `…\dify-main\docker\.env` was modified:

```dotenv
SSRF_PROXY_ALLOW_PRIVATE_DOMAINS=orchestrator,cv-service,pricing-service,api,localhost,127.0.0.1
SSRF_PROXY_ALLOW_PRIVATE_IPS=host.docker.internal,172.16.0.0/12,192.168.0.0/16,10.0.0.0/8
```

To **fully disable** the SSRF proxy (direct outbound connections), empty
`SSRF_PROXY_HTTP_URL` and `SSRF_PROXY_HTTPS_URL` and recreate the containers:
`docker compose up -d api worker`.

### 8.3 Entry point

Platana's `.env` sets `DIFY_API_URL=http://api:5001/v1` (`api` = Dify API
service name, `5001` = its internal port). Check the connection with:

```powershell
docker network inspect platana-shared-network --format "{{range .Containers}}{{.Name}} {{end}}"
```

### 8.4 Local MongoDB pitfall (Windows)

A stock Windows MongoDB install may be listening on `127.0.0.1:27017` — the
**same host port** published by the Docker `mongodb` service. Tools (mongosh,
Studio 3T) that point at `127.0.0.1:27017` may hit the *wrong* (stale) database.
Always operate on the real database through Docker:

```powershell
docker exec platana-mongodb mongosh --quiet platana_circular_economy
```

---

## 9. End-to-end run instructions

For a step-by-step guide covering network creation, Dify setup, `.env`
configuration, stack startup, seeding, demo flow and troubleshooting, see
[`docs/RUNBOOK.md`](RUNBOOK.md).
