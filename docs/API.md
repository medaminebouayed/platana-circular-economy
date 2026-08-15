# API Reference

All endpoints live behind Traefik at `http://localhost:8081`. Interactive
Swagger docs are available at `/api/docs` (main-service), `/docs` on every
microservice, and Redoc at `/redoc`.

---

## Conventions

- **Base path:** `/api` (main-service), `/` on internal microservices.
- **Auth:** `Authorization: Bearer <JWT>` for protected endpoints.
- **Roles:** `USER` (seller) and `ADMIN`. Admin-only endpoints return `403` for
  users.
- **Errors:** FastAPI-style `{ "detail": "..." }` with standard HTTP codes.

---

## main-service (8003)

### Auth

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/api/auth/login` | — | Login. Body: `{email, password, role}` → token |
| `POST` | `/api/auth/register` | — | Register a USER. Body: `{email, password, name}` |
| `GET` | `/api/auth/verify` | JWT | Validate a token |
| `GET` | `/api/auth/me` | JWT | Current user profile + preferences |
| `PUT` | `/api/auth/preferences` | JWT | Update user preferences (`UserPreferences`) |
| `PUT` | `/api/auth/profile` | JWT | Update display name |
| `PUT` | `/api/auth/password` | JWT | Change password |

`UserPreferences` fields: `isDarkTheme`, `notificationsEnabled`, `emailNotifs`,
`language`, `autoRefreshQueue`, `gradeDriftAlert`, `driftThreshold`,
`maxAIFaults`.

### Catalog & defects

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/api/catalog/brands?q=` | JWT | Searchable brand suggestions |
| `GET` | `/api/catalog/models?brand=&q=` | JWT | Searchable model suggestions for a brand |
| `GET` | `/api/defects/catalog` | JWT | Canonical defect ids for the admin UI |

### Products

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/api/products/upload` | JWT | Multipart: brand, model, year, original_price, files (1–5 images) → runs Dify eval, saves product + PDF report |
| `GET` | `/api/products` | ADMIN | All products |
| `GET` | `/api/products/pending` | ADMIN | Products in `PENDING_EVALUATION` / `REVIEW_READY` / `PENDING_ADMIN_REVIEW` |
| `GET` | `/api/products/user/{email}` | owner/ADMIN | Products of one user |
| `GET` | `/api/products/{id}` | owner/ADMIN | Single product |
| `GET` | `/api/products/{id}/images/{index}` | owner/ADMIN | Product photo (blob) |
| `GET` | `/api/products/{id}/report` | owner/ADMIN | Evaluation report **PDF** (blob) |
| `PATCH` | `/api/products/{id}/review` | ADMIN | Save admin review (grade, price, cost, defects, title, description, decision) → regenerates report, exports training sample |
| `POST` | `/api/products/{id}/reject` | ADMIN | Reject product with optional reason |
| `POST` | `/api/products/{id}/re-evaluate` | ADMIN | Re-run Dify evaluation |
| `POST` | `/api/products/{id}/publish` | ADMIN | Run Dify publish workflow → Shopify listing URL |

**Product document (simplified):**

```json
{
  "id": "66f...",
  "brand": "Apple",
  "model": "iPhone 13",
  "year": 2021,
  "original_price": 809.0,
  "image_paths": ["data/uploads/<uuid>.jpg"],
  "report_path": "data/reports/<id>.pdf",
  "status": "REVIEW_READY",
  "user_email": "user@example.com",
  "ai_predictions": {
    "grade": "B",
    "defects": ["cosmetic_scratch"],
    "market_price": 399.0,
    "refurb_cost": 15.0,
    "profit": 384.0,
    "decision": "RESALE_DIRECT",
    "title": "...", "description": "...",
    "predicted_at": "..."
  },
  "admin_review": { "...": "..." },
  "model_drift": { "pricing_error_eur": ..., "grade_changed": false, "defects_changed": false },
  "shopify_url": "https://.../products/...",
  "created_at": "..."
}
```

Status values: `PENDING_EVALUATION`, `REVIEW_READY` (serialized as
`PENDING_ADMIN_REVIEW`), `REVIEWED`, `PUBLISHED`, `REJECTED`, `AI_ERROR`,
`PUBLISH_ERROR`.

### Dashboard & stats

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/api/stats/dashboard` | — | KPIs: pending/published/rejected, decision mix, grade distribution, avg price, revenue, profit, AI corrections, transport cost |
| `GET` | `/api/stats/drift?window_days=30` | ADMIN | Drift counters + `alert` flag vs `maxAIFaults` preference |

### Logistics

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/api/logistics/workshops` | — | Workshop list |
| `POST` | `/api/logistics/workshops` | — | Create workshop |
| `PUT` | `/api/logistics/workshops/{id}` | — | Update workshop |
| `DELETE` | `/api/logistics/workshops/{id}` | — | Delete workshop |
| `POST` | `/api/logistics/optimize` | — | OR-Tools allocation of products to workshops |

### Admin AI tools (proxies to internal services)

Used by the dedicated admin pages (`/grading`, `/pricing`, `/product-sheet`).

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/api/cv/grade` | ADMIN | Multipart `files` (1–5 images) → forwards to cv-service `/grade` → `{grade, grade_confidence, detected_defects}`. Returns **503** if cv-service is unreachable |
| `POST` | `/api/pricing/predict` | ADMIN | Body: `PricingRequest` → forwards to pricing-service `/predict` → `{predicted_price, confidence_interval, price_ratio}`. Returns **503** if pricing-service is unreachable |
| `POST` | `/api/sheet/generate` | ADMIN | Body: `{productId?, brand, model, category, grade, originalPrice, predictedPrice, repairCost, defects[]}` → deterministic product sheet: `{title, description, highlights, attention_points, decision, decision_rationale, recommended_channels}`. Uses the same `RefurbDecisionEngine` thresholds as the training pipeline, so the decision always matches the backend business rules |

### Training (proxy to internal training-service)

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/api/training/jobs` | ADMIN | Queue `{"model": "pricing"\|"cv"}` retraining |
| `GET` | `/api/training/jobs?limit=` | ADMIN | List recent training jobs |

### Health

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Status, Dify URL + key configured flag |

---

## orchestrator (8000)

| Method | Path | Description |
|---|---|---|
| `POST` | `/process` | Full pipeline (CV→Pricing→Decision→GenAI). Multipart: brand, model, year, original_price, files |
| `POST` | `/publish-to-marketplace` | Direct Shopify publication (legacy path) |
| `POST` | `/optimize-logistics` | OR-Tools workshop allocation (`OptimizeLogisticsRequest`) |
| `GET` | `/health` | Health + downstream (cv/pricing) status |

---

## cv-service (8001)

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/grade` | internal | Multipart `files` (1–5 images) → `{grade, grade_confidence, detected_defects}`. Returns **503** if the model is not loaded |
| `POST` | `/internal/reload` | HMAC `X-Training-Service-Token` | Hot-reload the promoted ONNX model |
| `GET` | `/health` | — | Status + loaded model version |

## pricing-service (8002)

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/predict` | internal | `PricingRequest` → `{predicted_price, confidence_interval, price_ratio}`. Returns **503** if the model is not loaded |
| `GET` | `/health` | — | Status + model version + Redis cache state |

## training-service (8010)

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/jobs` | `X-Training-Service-Token` | Queue a pricing or CV retraining job |
| `GET` | `/jobs?limit=` | `X-Training-Service-Token` | List jobs |
| `GET` | `/health` | — | Status |

---

## Request / response schemas

All schemas live in `api/shared/schemas.py` (`PricingRequest`,
`PricingResponse`, `GradingResponse`, `OptimizeLogisticsRequest/Response`, ...)
and `api/shared/models.py` (`AIPredictions`, `AdminReview`, `ModelDrift`).

```json
// PricingRequest
{
  "grade": "C",
  "category": "smartphone",
  "brand": "Apple",
  "model": "iPhone 13",
  "original_price": 799.0,
  "age_days": 730,
  "repair_cost": 65.0,
  "defects": ["cosmetic_scratch"]
}
```

```json
// AdminReview (PATCH /api/products/{id}/review)
{
  "grade": "B",
  "defects": ["cosmetic_scratch"],
  "market_price": 379.0,
  "refurb_cost": 15.0,
  "title": "iPhone 13 reconditionné",
  "description": "Très bon état, garanti 6 mois.",
  "decision": "RESALE_DIRECT",
  "reviewed_by": "thomas.dubois@platana.fr"
}
```
