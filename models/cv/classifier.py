"""
Heads de classification pour le grading et la détection de défauts.
"""

import torch
import torch.nn as nn


class GradeClassifier(nn.Module):
    """Classification du grade A/B/C/D."""
    
    def __init__(self, embed_dim: int, num_classes: int = 4, dropout: float = 0.3):
        super().__init__()
        self.classifier = nn.Sequential(
            nn.LayerNorm(embed_dim),
            nn.Linear(embed_dim, embed_dim // 2),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(embed_dim // 2, num_classes)
        )
    
    def forward(self, fused_embedding: torch.Tensor) -> torch.Tensor:
        return self.classifier(fused_embedding)


class DefectDetector(nn.Module):
    """Détection multi-label des défauts (6 types)."""
    
    DEFECT_TYPES = [
        "scratch",      # Rayure
        "dent",         # Bosse/choc
        "crack",        # Fissure
        "discoloration", # Décoloration
        "missing_part",  # Pièce manquante
        "water_damage"   # Dommage eau
    ]
    
    def __init__(self, embed_dim: int, num_defects: int = 6, dropout: float = 0.3):
        super().__init__()
        self.detector = nn.Sequential(
            nn.LayerNorm(embed_dim),
            nn.Linear(embed_dim, embed_dim // 2),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(embed_dim // 2, num_defects)
        )
    
    def forward(self, fused_embedding: torch.Tensor) -> torch.Tensor:
        return self.detector(fused_embedding)