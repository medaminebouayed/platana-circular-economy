"""
Dataset multi-vues pour le grading de produits reconditionnés.
Gère un nombre VARIABLE de vues (1 à max_views).
"""

import json
import random
from pathlib import Path
from typing import Optional, Callable, List, Dict

import torch
from torch.utils.data import Dataset
from PIL import Image


class ProductGradingDataset(Dataset):
    """
    Dataset de produits avec vues multiples (nombre variable).
    
    Structure attendue:
        data/processed/
        ├── train/
        │   ├── product_001/
        │   │   ├── view_00.jpg
        │   │   ├── view_01.jpg
        │   │   └── view_02.jpg  (3 vues pour ce produit)
        │   ├── product_002/
        │   │   └── view_00.jpg  (1 seule vue)
        │   └── ...
        ├── val/
        └── annotations_train.json
        └── annotations_val.json
    
    Args:
        data_root: Racine des données (train/ ou val/)
        annotations_file: Chemin vers le JSON d'annotations
        transform: Transformations à appliquer
        max_views: Nombre maximum de vues (padding si moins)
        view_patterns: Patterns de nommage des vues
    """
    
    GRADE_TO_IDX = {"A": 0, "B": 1, "C": 2, "D": 3}
    IDX_TO_GRADE = {v: k for k, v in GRADE_TO_IDX.items()}
    
    DEFECT_TYPES = [
        "scratch", "dent", "crack",
        "discoloration", "missing_part", "water_damage"
    ]
    
    def __init__(
        self,
        data_root: str,
        annotations_file: str,
        transform: Optional[Callable] = None,
        max_views: int = 5,
        view_patterns: Optional[List[str]] = None
    ):
        self.data_root = Path(data_root)
        self.transform = transform
        self.max_views = max_views
        
        # Patterns de nommage (ordre important)
        self.view_patterns = view_patterns or [
            "view_00", "view_01", "view_02",
            "view_03", "view_04"
        ]
        
        # Charge les annotations
        with open(annotations_file, 'r') as f:
            self.annotations = json.load(f)
        
        # Filtre les produits valides
        self.product_ids = []
        for pid, ann in self.annotations.items():
            if self._validate_product(pid, ann):
                self.product_ids.append(pid)
        
        print(f"[INFO] Dataset chargé: {len(self.product_ids)} produits "
              f"(max {max_views} vues, padding si moins)")
    
    def _validate_product(self, pid: str, ann: dict) -> bool:
        """Vérifie qu'un produit a au moins une vue valide."""
        product_dir = self.data_root / pid
        if not product_dir.exists():
            return False
        
        # Compte les vues existantes
        num_views = 0
        for pattern in self.view_patterns:
            if list(product_dir.glob(f"{pattern}.*")):
                num_views += 1
        
        return num_views >= 1  # Au moins 1 vue requise
    
    def _load_view(self, product_dir: Path, pattern: str) -> Optional[Image.Image]:
        """Charge une vue ou retourne None si absente."""
        matches = list(product_dir.glob(f"{pattern}.*"))
        if not matches:
            return None
        return Image.open(matches[0]).convert("RGB")
    
    def __len__(self) -> int:
        return len(self.product_ids)
    
    def __getitem__(self, idx: int) -> Dict[str, torch.Tensor]:
        product_id = self.product_ids[idx]
        product_dir = self.data_root / product_id
        ann = self.annotations[product_id]
        
        # Charge les vues existantes
        views = []
        valid_count = 0
        
        for pattern in self.view_patterns:
            img = self._load_view(product_dir, pattern)
            if img is not None:
                if self.transform:
                    img = self.transform(img)
                views.append(img)
                valid_count += 1
            else:
                # Vue manquante : padding avec des zéros
                views.append(torch.zeros(3, 224, 224))
        
        # Stack les vues: (max_views, C, H, W)
        views_tensor = torch.stack(views)
        
        # Nombre réel de vues
        num_views_tensor = torch.tensor(valid_count, dtype=torch.long)
        
        # Grade
        grade = self.GRADE_TO_IDX[ann["grade"]]
        
        # Défauts (multi-label)
        defects = torch.zeros(len(self.DEFECT_TYPES))
        for defect in ann.get("defects", []):
            for i, dtype in enumerate(self.DEFECT_TYPES):
                if dtype in defect.lower():
                    defects[i] = 1
        
        return {
            "views": views_tensor,           # (max_views, C, H, W)
            "num_views": num_views_tensor,    # Nombre réel de vues
            "grade": torch.tensor(grade, dtype=torch.long),
            "defects": defects,               # (6,)
            "product_id": product_id,
            "metadata": {
                "category": ann.get("category", "unknown"),
                "brand": ann.get("brand", "unknown"),
                "model": ann.get("model", "unknown"),
                "original_price": ann.get("original_price", 0),
                "age_days": ann.get("age_days", 0)
            }
        }


def collate_fn(batch: List[Dict]) -> Dict[str, torch.Tensor]:
    """
    Collate function pour batcher des produits avec vues variables.
    """
    views = torch.stack([item["views"] for item in batch])      # (B, N_max, C, H, W)
    num_views = torch.stack([item["num_views"] for item in batch])  # (B,)
    grades = torch.stack([item["grade"] for item in batch])     # (B,)
    defects = torch.stack([item["defects"] for item in batch])  # (B, 6)
    product_ids = [item["product_id"] for item in batch]
    
    return {
        "views": views,
        "num_views": num_views,
        "grade": grades,
        "defects": defects,
        "product_id": product_ids
    }