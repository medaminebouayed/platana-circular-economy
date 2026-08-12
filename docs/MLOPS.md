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
