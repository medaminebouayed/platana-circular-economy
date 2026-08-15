from pydantic import BaseModel, Field
from typing import List, Optional, Any
from datetime import datetime
import uuid

class AIPredictions(BaseModel):
    grade: str
    defects: List[str] = []
    market_price: float
    refurb_cost: float
    profit: float
    decision: str
    title: str = ""
    description: str = ""
    fiche_produit: Any = None
    predicted_at: datetime = Field(default_factory=datetime.utcnow)

class AdminReview(BaseModel):
    """Les données modifiées par l'admin. Remplace les données IA pour la vérité terrain."""
    grade: str
    defects: List[str] = []
    market_price: float
    refurb_cost: float
    title: str
    description: str
    decision: str = ""
    reviewed_by: str = "admin"
    reviewed_at: datetime = Field(default_factory=datetime.utcnow)

class ModelDrift(BaseModel):
    pricing_error_eur: float
    grade_changed: bool
    defects_changed: bool