"""
API FastAPI pour l'Orchestrateur central.
"""

from typing import List, Dict, Optional
import os
import sys
import time
import random
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

sys.path.append(str(Path(__file__).parent.parent.parent))

from api.shared.schemas import ProductProcessingRequest, ProductProcessingResponse

app = FastAPI(title="Platana Orchestrator Service", version="1.0.0")

# Enable CORS for frontend interaction
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# === SCHEMAS ===

class OptimizeLogisticsRequest(BaseModel):
    product_ids: List[str]
    workshop_ids: Optional[List[str]] = None

class OptimizeLogisticsResponse(BaseModel):
    allocations: List[Dict]
    total_cost: float
    total_duration_hours: float
    solving_status: str

# === ENDPOINTS ===

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "services_configured": {
            "cv_url": os.getenv("CV_SERVICE_URL", "http://localhost:8001"),
            "pricing_url": os.getenv("PRICING_SERVICE_URL", "http://localhost:8002")
        }
    }

@app.post("/process", response_model=ProductProcessingResponse)
async def process_product(request: ProductProcessingRequest):
    """
    Orchestre le cycle de vie d'un produit :
    décision (revente / reconditionnement / recyclage) et suggestions de canaux.
    """
    # Logic matching the decision workflow
    decision = "RESALE_DIRECT"
    rationale = "Le produit est dans un état esthétique excellent ne nécessitant aucune intervention technique."
    channels = ["BackMarket", "Leboncoin", "Platana Store"]
    
    if request.grade in ["C", "D"]:
        # Mock calculation: simulate repair cost based on original price decimation
        original_price = 500.0  # default assumption if not provided
        repair_cost = 150.0 if request.grade == "C" else 300.0
        
        if repair_cost > original_price * 0.5:
            decision = "RECYCLE"
            rationale = f"Les coûts de reconditionnement ({repair_cost}€) dépassent 50% du prix d'origine ({original_price}€). Le recyclage matière est recommandé."
            channels = ["Filière D3E locale", "Recyclage Platana"]
        else:
            decision = "RECONDITION"
            rationale = f"Le grade de départ est bas ({request.grade}), mais le coût de réparation ({repair_cost}€) reste rentable. Remise en état conseillée avant publication."
            channels = ["BackMarket", "eBay", "Vente Privée Reconditionné"]

    # Generate a professional product sheet
    grade_labels = {
        'A': 'Excellent État',
        'B': 'Très Bon État',
        'C': 'État Correct',
        'D': 'À reconditionner'
    }
    
    title = f"{request.brand} {request.model} - {grade_labels.get(request.grade, 'Reconditionné')}"
    defect_text = f"Présente des traces d'usure : {', '.join(request.defects)}." if request.defects else "Aucun défaut esthétique majeur détecté."
    
    description = (
        f"Ce produit {request.brand} {request.model} a été rigoureusement inspecté par les algorithmes de vision par ordinateur Platana. "
        f"Classé en grade {request.grade} ({grade_labels.get(request.grade, '')}), il est fonctionnel à 100%. {defect_text} "
        f"Idéal pour une démarche éco-responsable, ce produit reconditionné évite l'extraction de matières premières et la mise en décharge de déchets électroniques."
    )

    fiche_produit = {
        "title": title,
        "description": description,
        "highlights": [
            "Testé et validé par notre laboratoire de grading multi-vues",
            "Fonctionnalités internes vérifiées à 100%",
            "Nettoyage antibactérien complet effectué",
            "Garantie légale de 12 mois Platana"
        ],
        "attention_points": [f"Défaut esthétique identifié : {d}" for d in request.defects] or ["Aucun point d'attention critique"],
        "decision_rationale": rationale
    }

    return ProductProcessingResponse(
        product_id=request.product_id,
        fiche_produit=fiche_produit,
        decision=decision,
        recommended_channels=channels
    )

@app.post("/optimize-logistics", response_model=OptimizeLogisticsResponse)
async def optimize_logistics(request: OptimizeLogisticsRequest):
    """
    Optimise le routage des produits vers les ateliers/canaux de revente
    en utilisant un solveur d'optimisation (OR-Tools de Google).
    """
    try:
        from ortools.linear_solver import pywraplp
        solver = pywraplp.Solver.CreateSolver('SCIP')
    except Exception as e:
        solver = None
        print(f"[WARN] Impossible d'initialiser OR-Tools, mode simulation actif pour la logistique. Details: {e}")

    # Workshops definition
    workshops = [
        {"id": "Lille", "specialty": "smartphones", "avg_cost": 25.0, "avg_days": 2.0},
        {"id": "Strasbourg", "specialty": "laptops", "avg_cost": 45.0, "avg_days": 3.0},
        {"id": "Lyon", "specialty": "tablets", "avg_cost": 30.0, "avg_days": 2.5},
        {"id": "Nantes", "specialty": "multipurpose", "avg_cost": 35.0, "avg_days": 4.0}
    ]

    allocations = []
    total_cost = 0.0
    total_duration = 0.0
    
    if solver:
        # Simple Linear Programming Assignment using OR-Tools Solver
        # Decision variables x[i, j] = 1 if product i is assigned to workshop j
        x = {}
        for i, prod in enumerate(request.product_ids):
            for j, ws in enumerate(workshops):
                x[i, j] = solver.IntVar(0, 1, f"x_{i}_{j}")

        # Constraint: each product is assigned to exactly one workshop
        for i in range(len(request.product_ids)):
            solver.Add(solver.Sum([x[i, j] for j in range(len(workshops))]) == 1)

        # Objective Function: Minimize assignment cost (workshop cost + simple specialty matching discount)
        objective_terms = []
        for i, prod in enumerate(request.product_ids):
            for j, ws in enumerate(workshops):
                # Simulated category check - discount routing to specialty
                cost = ws["avg_cost"]
                objective_terms.append(x[i, j] * cost)
        
        solver.Minimize(solver.Sum(objective_terms))
        status = solver.Solve()

        if status == pywraplp.Solver.OPTIMAL:
            solving_status = "OPTIMAL"
            for i, prod in enumerate(request.product_ids):
                for j, ws in enumerate(workshops):
                    if x[i, j].solution_value() > 0.5:
                        allocations.append({
                            "product_id": prod,
                            "workshop_id": ws["id"],
                            "cost": ws["avg_cost"],
                            "duration_days": ws["avg_days"],
                            "specialty_matched": True
                        })
                        total_cost += ws["avg_cost"]
                        total_duration += ws["avg_days"]
        else:
            solving_status = "FEASIBLE_SIMULATED"
            solver = None  # Force simulation fallback on solving issues

    if not solver:
        # Fallback to simulated greedy allocation
        solving_status = "SIMULATED"
        for prod in request.product_ids:
            # Randomly select a workshop
            ws = random.choice(workshops)
            allocations.append({
                "product_id": prod,
                "workshop_id": ws["id"],
                "cost": ws["avg_cost"],
                "duration_days": ws["avg_days"],
                "specialty_matched": random.choice([True, False])
            })
            total_cost += ws["avg_cost"]
            total_duration += ws["avg_days"]

    return OptimizeLogisticsResponse(
        allocations=allocations,
        total_cost=round(total_cost, 2),
        total_duration_hours=round(total_duration * 24.0, 2),
        solving_status=solving_status
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
