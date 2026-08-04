"""
Module Computer Vision pour le grading de produits reconditionnés.
"""

from .backbone import create_backbone
from .fusion import FusionModule
# The MultiViewGradingModel class does not exist – use the multi‑task model defined in model.py
from .model import MultiTaskDefectModel
from .dataset import GradingDataset
from .mvtec_dataset import MVTecDataset

__all__ = [
    "create_backbone",
    "FusionModule",
    "GradingDataset",
    "MVTecDataset",
    "MultiTaskDefectModel",
]