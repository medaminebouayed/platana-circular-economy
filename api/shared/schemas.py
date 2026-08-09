from typing import List, Optional, Dict
from pydantic import BaseModel

# === CV SERVICE ===
class GradingResponse(BaseModel):
    grade: str
    grade_confidence: float
    detected_defects: List[str]

# === PRICING SERVICE ===
class PricingRequest(BaseModel):
    grade: str
    category: str = "smartphone"
    brand: str
    model: str
    original_price: float = 800.0
    age_days: int = 365

class PricingResponse(BaseModel):
    predicted_price: float
    confidence_interval: tuple[float, float]

# === ORCHESTRATOR ===
class ProductProcessRequest(BaseModel):
    brand: str
    model: str
    year: int
    original_price: float = 800.0
    images: List[str] # Liste des chemins d'images locales pour le test

class ProductProcessResponse(BaseModel):
    grade: str
    defects: List[str]
    market_price: float
    refurb_cost: float
    profit: float
    decision: str

# === WORKSHOPS (MongoDB-backed) ===
class WorkshopBase(BaseModel):
    name: str
    city: str
    region: str
    capacity: int
    occupancy: int          # current usage %
    avg_cost: float         # avg refurb cost per unit (€)
    distance: int           # km from central depot
    specialties: List[str]
    status: str = "available"  # available | busy | full
    # Logistics constraints
    min_profit_threshold: float = 20.0   # Only accept products with profit >= this
    max_items_per_batch: int = 10        # Max items per run

class WorkshopCreate(WorkshopBase):
    pass

class WorkshopResponse(WorkshopBase):
    id: str

# === LOGISTICS (OR-Tools) ===
class LogisticsProduct(BaseModel):
    product_id: str
    grade: str = "C"
    profit: float # Le profit attendu si reconditionné

class OptimizeLogisticsRequest(BaseModel):
    products: List[LogisticsProduct]
    # workshops are now fetched from DB inside the endpoint

class OptimizeLogisticsResponse(BaseModel):
    allocations: List[Dict]
    total_expected_profit: float
    status: str