# Model versions, MLflow, and Redis

Every training run creates an immutable directory under the relevant
`models/*/checkpoints/versions/<version-id>/` directory. Each directory
contains the model artifact and `manifest.json`, including the MLflow run ID
and metrics. Existing artifacts are never overwritten.

Pointers select which complete version is used:

- `models/pricing/checkpoints/latest.json` — model and feature engineer used by pricing.
- `models/cv/checkpoints/latest_backbone.json` — backbone used by CV training.
- `models/cv/checkpoints/latest_training.json` — latest PyTorch CV training checkpoint.
- `models/cv/checkpoints/latest.json` — ONNX version used by the CV container.

Train pricing with `python -m models.pricing.train --data <dataset.csv>`. Train
the backbone with `python -m models.cv.pretrain_backbone`; then train the
grading/defect model with `python -m models.cv.train --mode continue`. Finally,
export and promote that CV version for lightweight production inference with
`python scripts/export_cv_onnx.py`. Pass `--version-id <id>` to export a
specific historical CV version.

Local evaluators default to their active pointers but can select a historical
version without changing production. Examples:

```powershell
python -m models.cv.inference --version-id cv-... image1.jpg image2.jpg
python -m models.cv.backbone_inference --version-id backbone-...
python -m models.pipeline --cv-version-id cv-... --pricing-version-id pricing-...
```

Each command also supports an explicit artifact path (`--model-path`, or the
paired `--cv-model-path` / `--pricing-model-path` and
`--pricing-engineer-path` options in the pipeline) for an externally supplied
artifact.

The CV container uses only ONNX Runtime. PyTorch, timm, and ONNX export tools
remain local training dependencies and are not installed in that image.

MLflow is available only through Traefik at `http://localhost:8081/mlflow` and
requires BasicAuth. Redis has no host port and is reachable only by containers
on the Compose network. Pricing cache keys include every validated request
field and a hash of the promoted model, feature engineer, and feature code, so
retraining automatically creates a new cache namespace.

For a public deployment, configure an HTTPS `websecure` entrypoint, TLS
certificates, and a real hostname before exposing Traefik to the internet.

## Continuous training

Seed the synthetic pricing dataset and the searchable product catalog once:

```powershell
python scripts/seed_pricing_catalog.py --regenerate
```

Inside the `training` container the scripts live under `/app/scripts`, so the
same seeding runs as:

```powershell
docker exec platana-training python scripts/seed_pricing_catalog.py --regenerate
```

Run guarded continuous training from a scheduler or CI job:

```powershell
python scripts/continuous_train.py pricing
python scripts/continuous_train.py cv
```

Pricing first snapshots the MongoDB `pricing_training_samples` collection;
CV continues from the active multitask model. Both create immutable candidates,
log them to MLflow, and promote only if their validation metric improves. The
default thresholds are 0.05 lower MAPE for pricing and 0.002 higher macro-F1
for CV. Test schedules without training with `--dry-run`.

### Triggering jobs from the admin UI

The frontend calls `POST /api/training/jobs` (main-service) with a JSON body:

```json
{ "model": "pricing" }   // or "cv"
```

The response is `202 {job, created}`. `created: false` means a job for that
model is **already running** — the request is rejected, not queued twice.

Guards:
- **Pricing** requires ≥ **500 samples** in `pricing_training_samples`
  (seeded with the command above); otherwise the job is rejected.
- **CV** continues from the active backbone on
  `data/processed/smartphone_grading/`, which `continuous_train.py`
  re-exports from MongoDB before every guarded retrain.

### Quick smoke test (one epoch)

`models/cv/train.py` accepts `--epochs` (default 100) so the whole chain
(train → log → export → promote → reload) can be validated quickly without a
full run:

```powershell
docker exec platana-training python -m models.cv.train --mode continue --epochs 1
```

Note: CV training needs the same `shm_size: 2g` as the Compose
`training-service` definition — PyTorch DataLoader workers crash without enough
shared memory.

### MLflow experiments

Experiments live in the `mlflow-data` volume under `/mlflow/mlflow.db`
(sqlite). The active experiments are `0 Default`, `1 platana-cv-grading` and
`2 platana-pricing`. If an experiment is **deleted from the MLflow UI**, the
trainer falls back to the `Default` experiment instead of crashing; to bring
the experiment back:

```python
from mlflow.tracking import MlflowClient
MlflowClient().restore_experiment("1")   # platana-cv-grading
MlflowClient().restore_experiment("2")   # platana-pricing
```

## Admin-reviewed ground truth (closed loop)

When an admin saves a product review (`PATCH /api/products/{id}/review`), the
main service:

1. Normalizes defects to the shared catalog (`api/shared/defects.py`).
2. Upserts a labelled row into MongoDB `pricing_training_samples`
   (`source: admin-review`, unique `source_product_id`).
3. Does **not** export CV samples itself: its `data/processed` directory is
   ephemeral in production. Instead `scripts/continuous_train.py` re-exports
   every reviewed product from MongoDB (resolving each image path against
   `/app/data/uploads` and writing the annotation) into
   `data/processed/smartphone_grading/` before every guarded CV retrain.

Before each guarded retrain, `scripts/continuous_train.py` syncs all reviewed
products from MongoDB so batch jobs pick up the latest admin corrections.
Pricing exports the merged `pricing_training_samples` collection; CV continues
from the active multitask checkpoint on the expanded processed dataset.

After a successful retrain, the internal training service calls
`POST /internal/reload` on the affected service (`cv-service` or
`pricing-service`) so the promoted model is loaded without restarting the
container. Both reload endpoints are authenticated with the
`X-Training-Service-Token` header (HMAC-compared against
`TRAINING_SERVICE_TOKEN`).

### CV defect classes — design limitation, not a bug

The CV classifier only learns **three labels**: `no_defect`, `screen_crack`,
and `cosmetic_scratch`. Every canonical defect maps to one of those classes
(`CANONICAL_DEFECTS[].cv_class` in `api/shared/defects.py`):

- `screen_crack` ← `screen_crack`, `crack`, `back_glass_crack`
- `cosmetic_scratch` ← `cosmetic_scratch`, `scratch`, `dent`, `discoloration`
- `no_defect` ← everything else (`battery_weak`, `battery_swollen`,
  `port_broken`, `microphone_dead`, `no_power`, `missing_part`,
  `water_damage`, `hinge_broken`) — these are functional faults that are not
  visible on the exterior surface.

Consequences:

- Correcting a functional defect (e.g. `battery_weak`) in the admin UI does
  **not** add a new CV label; it still feeds the pricing model through
  `exact_defects`. This is intended.
- The CV model grades cosmetic/screen damage only. Functional faults are
  captured by admin review and priced via the defect-aware features, never by
  the camera.

Docker notes:

- `uploads-data` volume is mounted on `main-service` (read-write) and
  `training-service` (read-only) at `/app/data/uploads`.
- `data/processed` is mounted read-write on `training-service` for CV exports.
