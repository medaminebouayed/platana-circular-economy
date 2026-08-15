# Data Model

Primary datastore: **MongoDB** (accessed via Motor). Model definitions live in
`api/shared/models.py` and `api/shared/schemas.py`. Redis holds transient
pricing-cache entries only.

---

## Collections

### `products`

One document per submitted product, written by `main-service`.

```jsonc
{
  "_id": "ObjectId",
  "user_email": "user@example.com",            // owner (sellers)
  "brand": "Apple",
  "model": "iPhone 13",
  "year": 2021,
  "original_price": 809.0,
  "image_paths": ["data/uploads/66f3....jpg"],  // server-relative paths (1–5)
  "report_path": "data/reports/66f3....pdf",     // generated PDF evaluation report
  "status": "REVIEW_READY",                      // see status list below
  "created_at": "ISODate",
  "ai_predictions": {                            // Dify / pipeline output
    "grade": "B",
    "grade_confidence": 0.91,
    "defects": ["cosmetic_scratch"],
    "market_price": 399.0,
    "refurb_cost": 15.0,
    "profit": 384.0,
    "decision": "RESALE_DIRECT",
    "title": "iPhone 13 — Très bon état",
    "description": "...",
    "predicted_at": "ISODate"
  },
  "admin_review": {                              // set after admin validation
    "grade": "B",
    "defects": ["cosmetic_scratch"],
    "market_price": 379.0,
    "refurb_cost": 15.0,
    "title": "...", "description": "...",
    "decision": "RESALE_DIRECT",
    "reviewed_by": "thomas.dubois@platana.fr",
    "reviewed_at": "ISODate"
  },
  "model_drift": {                               // admin-vs-AI deltas (learning signal)
    "pricing_error_eur": 20.0,
    "refurb_error_eur": 0.0,
    "grade_changed": false,
    "defects_changed": false,
    "title_changed": false,
    "reviewed_at": "ISODate"
  },
  "shopify_url": "https://.../products/slug",    // after publish
  "rejection_reason": "…",                       // when REJECTED
  "error_message": "…"                            // when AI_ERROR
}
```

**Status values**

| Status | Meaning |
|---|---|
| `PENDING_EVALUATION` | Uploaded, Dify evaluation in flight |
| `REVIEW_READY` | AI evaluation complete, waiting for admin (API serializes as `PENDING_ADMIN_REVIEW`) |
| `REVIEWED` | Admin saved the review |
| `PUBLISHED` | Published to Shopify |
| `REJECTED` | Rejected by admin |
| `AI_ERROR` | Evaluation failed (kept for diagnosis) |
| `PUBLISH_ERROR` | Publish workflow failed |

### `users`

```jsonc
{
  "_id": "ObjectId",
  "email": "user@example.com",
  "hashed_password": "$2b$12$...",          // bcrypt
  "role": "USER",                             // USER | ADMIN
  "name": "User Name",
  "preferences": {
    "isDarkTheme": false,
    "notificationsEnabled": true,
    "emailNotifs": true,
    "language": "fr",
    "autoRefreshQueue": true,
    "gradeDriftAlert": true,
    "driftThreshold": 0.2,
    "maxAIFaults": 3
  },
  "created_at": "ISODate"
}
```

Passwords are **never stored in plain text**. Admins are seeded by
`scripts/seed_admin.py` when the collection is empty.

### `pricing_training_samples`

Labelled samples exported when an admin saves a review — the closed-loop
learning signal for the pricing model.

```jsonc
{
  "_id": "ObjectId",
  "product_id": "ObjectId",
  "brand": "Apple",
  "model": "iPhone 13",
  "year": 2021,
  "age_days": 730,
  "original_price": 809.0,
  "grade": "B",
  "defects": ["cosmetic_scratch"],
  "repair_cost": 15.0,
  "target_price": 379.0,           // admin-validated resale price
  "ai_price": 399.0,               // AI prediction at evaluation time
  "created_at": "ISODate"
}
```

Consumed by `scripts/continuous_train.py pricing` (snapshot → train →
MLflow → guarded promotion).

### `workshops`

```jsonc
{
  "_id": "ObjectId",
  "name": "Atelier Lyon",
  "location": "Lyon",
  "capacity": 50,
  "unit_cost": 8.0,
  "unit_cost_multiplier": 1.0,
  "is_active": true
}
```

### `product_catalog`

Seeded by `api/shared/catalog_seed.py` (`scripts/seed_catalog.py`): brand →
model → category → base price mappings used to normalise user input
(brand/model dropdowns in the UI).

```jsonc
{
  "brand": "Apple",
  "models": [
    { "name": "iPhone 13", "category": "smartphone", "base_price": 809.0 }
  ]
}
```

### `training_jobs`

Created by `main-service` when an admin queues a retraining job.

```jsonc
{
  "model": "pricing",               // pricing | cv
  "status": "PENDING",              // PENDING | RUNNING | SUCCESS | FAILED
  "triggered_by": "admin@platana.fr",
  "created_at": "ISODate",
  "started_at": "ISODate",
  "completed_at": "ISODate",
  "log": "..."                       // short run log / error
}
```

---

## Redis keys

| Key | Value | TTL |
|---|---|---|
| `pricing:{fingerprint}` | JSON `{price, confidence_interval, price_ratio}` | `PRICING_CACHE_TTL_SECONDS` |

The fingerprint is produced by `build_pricing_cache_key()` and includes the
full validated request plus the model/feature-engineer/feature-code versions,
so cache entries are automatically invalidated whenever a new model is
promoted. See `tests/test_pricing_cache.py`.

---

## File layout on disk

| Path | Contents | Served by |
|---|---|---|
| `data/uploads/*` | Product photos | `GET /api/products/{id}/images/{index}` |
| `data/reports/*.pdf` | Evaluation reports | `GET /api/products/{id}/report` |
| `data/processed/*` | CV retraining dataset exports | training-service |
| `models/{cv,pricing}/checkpoints/versions/*` | Immutable model versions | inference services |
| `models/{cv,pricing}/checkpoints/latest*.json` | Version pointers | all services |
