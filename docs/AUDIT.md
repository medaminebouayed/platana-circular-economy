# Project Audit — Scan Report

Scope: full repository scan (services, models, frontend, tests, configuration)
performed on 2026-08-14. Severity: **High** / **Medium** / **Low**.

---

## Summary

| Severity | Found | Fixed | Open |
|---|---|---|---|
| High | 3 | 3 | 0 |
| Medium | 3 | 3 | 0 |
| Low | 4 | 3 | 1 |

---

## High severity

### H1. Simulation/mock fallbacks in inference services (FIXED)

`api/cv_service/main.py`, `api/pricing_service/main.py` and
`models/genai/sheet_generator.py` fabricated **fake outputs** when the model
(ONNX / XGBoost / Groq) was unavailable — e.g. `/grade` returned a canned
grade + confidence when the grader was `None`, and `/predict` fell back to
hard-coded price ratios. This silently passed wrong data into the product
pipeline.

**Fix:** services now fail loudly — `503 "CV/Pricing model is not loaded"` when
the model is absent, and the GenAI sheet generator raises `RuntimeError` on a
missing `GROQ_API_KEY` or Groq failure. The orchestrator `/process` catches
sheet-generation errors and continues with `fiche_produit=None` (logged). Real
model artifacts are versioned and hot-reloaded, so 503s only occur in genuine
misconfiguration states.

### H2. Hard-coded reference year in age computation (FIXED)

`api/orchestrator/main.py` computed `age_days` with `(2025 - year) * 365`,
making the model input silently wrong after 2025.

**Fix:** `(datetime.now().year - year) * 365`.

### H3. Duplicate dead assignments in the decision pipeline (FIXED)

`models/pipeline.py` set `decision`, `action`, and `product_sheet` twice in the
`else` branch (identical values) — dead code with no behavioural impact but a
maintainability/confusion risk.

**Fix:** removed the duplicate assignments.

---

## Medium severity

### M1. Deprecated `datetime.utcnow()` usage (FIXED)

`datetime.datetime.utcnow()` is deprecated in Python 3.12 (removal scheduled in
3.13+). The only occurrences were in `api/main_service/main.py` (JWT exp/iat,
seed dates, review/reject/publish timestamps, drift window).

**Fix:** all 11 occurrences replaced with `datetime.now(timezone.utc)`. The
`assess_drift` fallback was switched to an aware `datetime.min` so sorting and
`.isoformat()` never mix naive and aware values. Stored BSON values are
byte-identical (MongoDB always stores UTC).

### M2. Hard-coded `avgDelay: 4.2` in dashboard stats (FIXED)

`api/main_service` dashboard stats hard-coded the average processing delay.

**Fix:** `avgDelay` is now computed as the mean of
`reviewed_at - created_at` (in hours) across all reviewed products that have
both timestamps; falls back to `0.0` when no reviewed product exists yet.

### M3. FastAPI `@app.on_event` deprecation (FIXED)

`on_event("startup")` / `on_event("shutdown")` were used in `cv`, `pricing`,
`training`, `orchestrator`, and `main_service`, emitting deprecation warnings.

**Fix:** all services migrated to `lifespan` context managers wired through the
`FastAPI(lifespan=...)` constructor. Startups (model load, Redis connect,
catalog/workshop seeding) run before serving; shutdowns (Mongo/Redis close)
run on teardown.

---

## Low severity

### L1. `.gitignore` did not cover generated PDF reports (FIXED)

`data/reports/*` was generated on disk but not ignored — reports would be
committed by accident.

**Fix:** added `data/reports/*` to `.gitignore` (mirrors `data/uploads/*`).

### L2. Multi-encoding labels in PDF generator (FIXED)

The FPDF report used `—` (em-dash) and accented text with the built-in
`latin-1` font, which raises `FPDFUnicodeEncodingException` at runtime
(e.g. `—` is outside latin-1).

**Fix:** all text is now passed through a latin-1 sanitizer (`_clean`) —
headers, section labels, rows, and the footer.

### L3. Demo credentials seeded unconditionally (OPEN)

Admin/user demo accounts are seeded whenever MongoDB is empty. Acceptable for
dev; production must disable seeding or require a first-run password change.

### L4. Raw/interpolated query construction in stats (FIXED)

A deeper review found **no raw `db.command()` or interpolated aggregation
pipeline** in the stats code — all aggregation uses typed
`count_documents`/`find`/`distinct`. The only `command()` call is a fixed-string
`ping` health check in `training_service`. The two `$regex`-based catalog
searches did use an inline `__import__('re').escape(...)`.

**Fix:** replaced the inline `__import__('re')` calls with a top-level
`import re` + `re.escape(...)` (identical escaping behaviour, cleaner and
reviewable), keeping all user input escaped before entering Mongo queries.

---

## Test coverage (post-fix)

```
53 passed, 7 warnings in ~2s
```

Covered areas: decision-engine thresholds (pipeline vs orchestrator parity),
drift statistics, pricing cache key stability, defect normalisation, catalog
seeding, training export paths, CV config consistency.

---

## Recommendations (non-blocking)

1. Gate demo-account seeding behind an env flag in production (L3).
2. Add an end-to-end smoke test that uploads a product, evaluates it, and
   asserts the PDF report is generated and downloadable.
