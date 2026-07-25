"""
Schémas Pydantic partagés entre les services.
"""

from typing import List, Optional, Dict
from pydantic import BaseModel


# === CV SERVICE ===

class GradingRequest(BaseModel):
    product_id: Optional[str] = None
    category: Optional[str] = None
    brand: Optional[str] = None
    model: Optional[str] = None


class GradingResponse(BaseModel):
    product_id: Optional[str]
    grade: str
    grade_confidence: float
    grade_probabilities: Dict[str, float]
    detected_defects: List[Dict[str, float]]
    attention_weights: Optional[List[float]]
    num_views_used: int
    processing_time_ms: float


# === PRICING SERVICE ===

class PricingRequest(BaseModel):
    grade: str
    category: str
    brand: str
    model: str
    original_price: float
    age_days: int
    repair_cost: Optional[float] = 0.0
    season: Optional[str] = None


class PricingResponse(BaseModel):
    predicted_price: float
    confidence_interval: tuple[float, float]
    price_ratio: float
    explanation: str


# === ORCHESTRATOR ===

class ProductProcessingRequest(BaseModel):
    product_id: str
    grade: str
    predicted_price: float
    category: str
    brand: str
    model: str
    defects: List[str]


class ProductProcessingResponse(BaseModel):
    product_id: str
    fiche_produit: Dict
    decision: str
    recommended_channels: List[str]