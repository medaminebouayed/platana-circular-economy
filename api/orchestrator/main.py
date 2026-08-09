"""
Platana Orchestrator Service — Production-ready FastAPI microservice.
Responsible for: Orchestrating the full evaluation pipeline (CV → Pricing → GenAI)
                 and publishing products to Shopify.
Port: 8000
"""
import os
import logging
from pathlib import Path
from typing import List

import httpx
from fastapi import FastAPI, HTTPException, File, UploadFile, Form, Request
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

# ── Config ─────────────────────────────────────────────────────
import sys
sys.path.append(str(Path(__file__).resolve().parents[1]))

env_path = Path(__file__).resolve().parents[2] / '.env'
load_dotenv(dotenv_path=env_path)

from shared.schemas import OptimizeLogisticsRequest, OptimizeLogisticsResponse

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | orchestrator | %(message)s")
logger = logging.getLogger(__name__)

# ── Service URLs ─────────────────────────────────────────────────
CV_URL = os.getenv("CV_SERVICE_URL", "http://localhost:8001")
PRICING_URL = os.getenv("PRICING_SERVICE_URL", "http://localhost:8002")
SHOPIFY_STORE_URL = os.getenv("SHOPIFY_STORE_URL")
SHOPIFY_ACCESS_TOKEN = os.getenv("SHOPIFY_ACCESS_TOKEN")

# ── App ─────────────────────────────────────────────────────────
app = FastAPI(
    title="Platana Orchestrator",
    description="Central orchestration service that coordinates CV, Pricing, and GenAI services.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:4200", "http://localhost"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Decision Engine ──────────────────────────────────────────────
class DecisionEngine:
    REFURB_COSTS = {
        "screen_crack": 120.0,
        "cosmetic_scratch": 15.0,
        "back_glass_crack": 40.0,
        "battery_weak": 30.0,
        "no_defect": 5.0,
    }

    @staticmethod
    def estimate_refurb_cost(defects: List[str]) -> float:
        return sum(DecisionEngine.REFURB_COSTS.get(d, 10.0) for d in defects)

    @staticmethod
    def decide(profit: float) -> str:
        if profit >= 50.0:
            return "RESALE_DIRECT"
        elif profit >= 20.0:
            return "RECONDITION"
        else:
            return "RECYCLE"

# ── Health Check ─────────────────────────────────────────────────
@app.get("/health", tags=["health"])
async def health():
    """Check orchestrator health and downstream service connectivity."""
    checks = {}
    async with httpx.AsyncClient() as client:
        for name, url in [("cv_service", CV_URL), ("pricing_service", PRICING_URL)]:
            try:
                r = await client.get(f"{url}/health", timeout=3.0)
                checks[name] = r.json().get("status", "unknown")
            except Exception:
                checks[name] = "unreachable"
    return {"status": "ok", "service": "orchestrator", "downstream": checks}

# ── Full Processing Pipeline ─────────────────────────────────────
@app.post("/process", tags=["pipeline"])
async def process_product(
    brand: str = Form(...),
    model: str = Form(...),
    year: int = Form(...),
    original_price: float = Form(...),
    files: List[UploadFile] = File(...)
):
    """Full pipeline: CV grading → price prediction → decision logic → GenAI sheet."""
    logger.info("Processing product: %s %s (%d)", brand, model, year)

    # Step 1: CV Grading
    async with httpx.AsyncClient() as client:
        try:
            file_tuples = []
            for f in files:
                contents = await f.read()
                file_tuples.append(('files', (f.filename, contents, f.content_type or 'image/jpeg')))

            cv_res = await client.post(f"{CV_URL}/grade", files=file_tuples, timeout=30.0)
            cv_res.raise_for_status()
            cv_data = cv_res.json()
            grade = cv_data["grade"]
            defects = cv_data["detected_defects"]
            logger.info("CV result: grade=%s, defects=%s", grade, defects)
        except httpx.HTTPStatusError as e:
            raise HTTPException(status_code=503, detail=f"CV Service error: {e.response.text}")
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"CV Service unreachable: {e}")

    # Step 2: Price Prediction
    async with httpx.AsyncClient() as client:
        try:
            pricing_payload = {
                "grade": grade,
                "brand": brand,
                "model": model,
                "original_price": original_price,
                "category": "smartphone",
                "age_days": max(0, (2025 - year) * 365),
            }
            price_res = await client.post(f"{PRICING_URL}/predict", json=pricing_payload, timeout=10.0)
            price_res.raise_for_status()
            market_price = price_res.json()["predicted_price"]
            logger.info("Pricing result: market_price=%.2f", market_price)
        except httpx.HTTPStatusError as e:
            raise HTTPException(status_code=503, detail=f"Pricing Service error: {e.response.text}")
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"Pricing Service unreachable: {e}")

    # Step 3: Decision
    refurb_cost = DecisionEngine.estimate_refurb_cost(defects)
    profit = round(market_price - refurb_cost, 2)
    decision = DecisionEngine.decide(profit)

    # Step 4: GenAI Sheet (if applicable)
    fiche_produit = None
    if decision in ("RESALE_DIRECT", "RECONDITION"):
        try:
            from models.genai.sheet_generator import ProductSheetGenerator
            sheet_gen = ProductSheetGenerator()
            fiche_produit = sheet_gen.generate_sheet_text(
                model_name=f"{brand} {model}", grade=grade,
                repaired_defects=defects, price=market_price
            )
        except Exception as e:
            logger.warning("GenAI sheet generation failed: %s", e)

    logger.info("Pipeline complete: decision=%s, profit=%.2f", decision, profit)
    return {
        "grade": grade,
        "defects": defects,
        "market_price": market_price,
        "refurb_cost": refurb_cost,
        "profit": profit,
        "decision": decision,
        "fiche_produit": fiche_produit,
    }

# ── Shopify Publication ───────────────────────────────────────────
@app.post("/publish-to-marketplace", tags=["marketplace"])
async def publish_to_marketplace(request: Request):
    """Publish a reviewed product to Shopify marketplace."""
    try:
        data = await request.json()
    except Exception:
        form_data = await request.form()
        data = dict(form_data)

    title = str(data.get("title", "Untitled Product"))
    description = str(data.get("description", ""))
    grade = str(data.get("grade", "N/A"))
    try:
        price = float(data.get("price", 0.0))
    except (ValueError, TypeError):
        price = 0.0

    if not SHOPIFY_STORE_URL or not SHOPIFY_ACCESS_TOKEN:
        raise HTTPException(status_code=503, detail="Shopify credentials not configured in .env")

    shopify_payload = {
        "product": {
            "title": title,
            "body_html": f"<p>{description}</p><p><strong>Grade: {grade}</strong></p>",
            "vendor": "Platana Refurbished",
            "product_type": "Reconditioned Electronics",
            "variants": [{"price": str(price), "sku": f"PLT-{int(price * 100)}"}],
        }
    }

    async with httpx.AsyncClient() as client:
        try:
            headers = {"X-Shopify-Access-Token": SHOPIFY_ACCESS_TOKEN, "Content-Type": "application/json"}
            response = await client.post(
                f"https://{SHOPIFY_STORE_URL}/admin/api/2024-01/products.json",
                json=shopify_payload, headers=headers, timeout=15.0
            )
            response.raise_for_status()
            result = response.json()
            product_id = result["product"]["id"]
            handle = result["product"]["handle"]
            logger.info("Published to Shopify: id=%s", product_id)
            return {
                "status": "SUCCESS",
                "marketplace_listing_id": product_id,
                "listing_url": f"https://{SHOPIFY_STORE_URL}/products/{handle}",
            }
        except httpx.HTTPStatusError as e:
            logger.error("Shopify API error: %s", e.response.text)
            raise HTTPException(status_code=502, detail=f"Shopify API error: {e.response.text}")
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Marketplace publish failed: {e}")

# ── OR-Tools Logistics Optimisation ──────────────────────────────
@app.post("/optimize-logistics", response_model=OptimizeLogisticsResponse, tags=["logistics"])
async def optimize_logistics(request: OptimizeLogisticsRequest):
    """Optimize product routing across workshops using OR-Tools.
    
    Workshops and their constraints are fetched live from MongoDB.
    """
    try:
        from ortools.linear_solver import pywraplp
    except ImportError:
        raise HTTPException(status_code=500, detail="OR-Tools not installed. Run: pip install ortools")

    # ── Fetch workshops from MongoDB ──────────────────────────────
    from motor.motor_asyncio import AsyncIOMotorClient
    import os
    MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")
    _client = AsyncIOMotorClient(MONGO_URL)
    _db = _client.platana_circular_economy
    
    workshops_cursor = _db.workshops.find({"status": {"$ne": "full"}})
    workshops = await workshops_cursor.to_list(length=100)
    
    if not workshops:
        logger.warning("No workshops found in DB. Cannot optimize logistics.")
        return OptimizeLogisticsResponse(allocations=[], total_expected_profit=0.0, status="NO_WORKSHOPS")

    # Build workshop lookup: name -> {capacity_remaining, avg_cost, min_profit, max_batch}
    workshop_map = {}
    for w in workshops:
        name = w["name"]
        capacity = w.get("capacity", 50)
        occupancy_pct = w.get("occupancy", 0)
        # Remaining slots = capacity * (1 - occupancy%)
        remaining = max(0, int(capacity * (1 - occupancy_pct / 100)))
        workshop_map[name] = {
            "capacity": remaining,
            "avg_cost": w.get("avg_cost", 20.0),
            "min_profit": w.get("min_profit_threshold", 20.0),
            "max_batch": w.get("max_items_per_batch", 10),
        }

    logger.info("Loaded %d workshops for optimization: %s", len(workshop_map), list(workshop_map.keys()))

    # ── Filter products per workshop constraints ──────────────────
    # Each product must meet the min_profit_threshold of the workshop it can go to
    solver = pywraplp.Solver.CreateSolver("SCIP")
    if not solver:
        raise HTTPException(status_code=500, detail="OR-Tools solver could not be created.")

    x = {}
    for i, prod in enumerate(request.products):
        for j, wdata in workshop_map.items():
            # Only allow assignment if profit meets the workshop threshold
            if prod.profit >= wdata["min_profit"]:
                x[i, j] = solver.IntVar(0, 1, f"x_{i}_{j}")

    if not x:
        logger.warning("No feasible product-workshop assignments found given current constraints.")
        return OptimizeLogisticsResponse(allocations=[], total_expected_profit=0.0, status="NO_FEASIBLE_ASSIGNMENTS")

    # Each product goes to at most one workshop
    for i in range(len(request.products)):
        vars_for_prod = [x[i, j] for j in workshop_map if (i, j) in x]
        if vars_for_prod:
            solver.Add(solver.Sum(vars_for_prod) <= 1)

    # Capacity constraints per workshop
    for j, wdata in workshop_map.items():
        vars_for_workshop = [x[i, j] for i in range(len(request.products)) if (i, j) in x]
        if vars_for_workshop:
            effective_cap = min(wdata["capacity"], wdata["max_batch"])
            solver.Add(solver.Sum(vars_for_workshop) <= effective_cap)

    # Objective: maximize total (profit - avg_cost)
    objective = solver.Objective()
    for i, prod in enumerate(request.products):
        for j, wdata in workshop_map.items():
            if (i, j) in x:
                objective.SetCoefficient(x[i, j], prod.profit - wdata["avg_cost"])
    objective.SetMaximization()

    status = solver.Solve()
    allocations = []
    total_profit = 0.0

    if status in (pywraplp.Solver.OPTIMAL, pywraplp.Solver.FEASIBLE):
        for i, prod in enumerate(request.products):
            for j, wdata in workshop_map.items():
                if (i, j) in x and x[i, j].solution_value() > 0.5:
                    allocations.append({"product_id": prod.product_id, "workshop": j})
                    total_profit += prod.profit - wdata["avg_cost"]
        status_str = "OPTIMAL" if status == pywraplp.Solver.OPTIMAL else "FEASIBLE"
    else:
        status_str = "NO_SOLUTION"

    logger.info("Logistics optimized: %d allocations, total profit=%.2f", len(allocations), total_profit)
    return OptimizeLogisticsResponse(
        allocations=allocations,
        total_expected_profit=round(total_profit, 2),
        status=status_str,
    )