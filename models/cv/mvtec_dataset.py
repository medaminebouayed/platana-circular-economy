"""
Dataset MVTec AD pour le pré-entraînement du backbone.
Mono-vue : une seule image par échantillon.
"""

import os
import random
import numpy as np
from pathlib import Path
from typing import Optional, Callable

import torch
from torch.utils.data import Dataset
from PIL import Image

# Import mask‑aware augmentations
from augmentations import get_train_transform, generate_synthetic_anomaly


class MVTecDataset(Dataset):
    """
    Dataset MVTec AD pour la détection d'anomalies.
    
    Structure:
        mvtec_ad/
        ├── bottle/
        │   ├── train/
        │   │   ├── good/
        │   │   │   ├── 000.png
        │   │   │   └── ...
        │   └── test/
        │       ├── good/
        │       └── anomaly_type/
        ├── cable/
        └── ...
    
    Usage:
        dataset = MVTecDataset(
            root="data/external/mvtec_ad",
            category="bottle",
            split="train",
            transform=transforms
        )
    """
    
    CATEGORIES = [
        "bottle", "cable", "capsule", "carpet", "grid", "hazelnut",
        "leather", "metal_nut", "pill", "screw", "tile", "toothbrush",
        "transistor", "wood", "zipper"
    ]
    
    DEFECT_TYPES = [
        "bent", "bent_lead", "bent_wire", "broken", "broken_large",
        "broken_small", "broken_teeth", "cable_swap", "color", "combined",
        "contamination", "crack", "cut", "cut_inner_insulation", "cut_lead",
        "cut_outer_insulation", "damaged_case", "defective", "fabric_border",
        "fabric_interior", "faulty_imprint", "flip", "fold", "glue", "glue_strip",
        "gray_stroke", "hole", "liquid", "manipulated_front", "metal_contamination",
        "misplaced", "missing_cable", "missing_wire", "oil", "pill_type", "poke",
        "poke_insulation", "print", "rough", "scratch", "scratch_head",
        "scratch_neck", "split_teeth", "squeeze", "squeezed_teeth", "thread",
        "thread_side", "thread_top"
    ]
    
    def __init__(
        self,
        root: str,
        category: str,
        split: str = "train",
        transform: Optional[Callable] = None
    ):
        self.root = Path(root)
        self.category = category
        self.split = split
        self.transform = transform
        self.mask_aware = True  # use mask‑aware augmentations by default for training

        if category not in self.CATEGORIES:
            raise ValueError(f"Catégorie '{category}' invalide. Choisir parmi: {self.CATEGORIES}")

        self.samples = []
        self.labels = []
        self.defect_types = []

        self._load_samples()

        # Set default transform for training if none provided
        if self.transform is None and self.split == "train" and self.mask_aware:
            # The transform returned by get_train_transform already converts to Tensor
            self.transform = get_train_transform(self.category)
        elif self.transform is None:
            # Simple deterministic transform for validation/test
            self.transform = lambda x: torch.tensor(np.array(x)).permute(2, 0, 1).float() / 255.0
    
    def _load_samples(self):
        """Charge tous les chemins d'images et leurs labels."""
        split_dir = self.root / self.category / self.split
        
        if not split_dir.exists():
            raise FileNotFoundError(f"Dossier non trouvé: {split_dir}")
        
        # Parcours les sous-dossiers (good, anomaly_type_1, ...)
        for defect_dir in sorted(split_dir.iterdir()):
            if not defect_dir.is_dir():
                continue
            
            defect_type = defect_dir.name  # "good", "scratch", "broken", etc.
            is_anomaly = 0 if defect_type == "good" else 1
            
            for img_path in sorted(defect_dir.glob("*.png")):
                self.samples.append(str(img_path))
                self.labels.append(is_anomaly)
                self.defect_types.append(defect_type)
        
        print(f"[INFO] MVTec {self.category}/{self.split}: {len(self.samples)} images "
              f"({sum(1 for l in self.labels if l == 0)} normal, "
              f"{sum(self.labels)} anomalie)")
    
    def __len__(self) -> int:
        return len(self.samples)
    
    def __getitem__(self, idx: int) -> dict:
        img_path = self.samples[idx]
        label = self.labels[idx]
        defect_type = self.defect_types[idx]
        
        # Charge l'image
        image = Image.open(img_path).convert("RGB")
        
        # For training, dynamically generate synthetic anomalies with a 50% probability
        if self.split == "train" and self.mask_aware:
            if random.random() < 0.5:
                image, defect_type = generate_synthetic_anomaly(image)
                label = 1
        
        if self.transform:
            try:
                image = self.transform(image)
            except Exception:
                if isinstance(image, torch.Tensor):
                    # Fallback: convert back to PIL if the transform expects a PIL Image
                    image = Image.fromarray((image.cpu().permute(1, 2, 0).numpy() * 255).astype('uint8'))
                image = self.transform(image)
        
        # One‑hot encoding des types de défauts
        defect_onehot = torch.zeros(len(self.DEFECT_TYPES))
        if label == 1:
            defect_idx = self._get_defect_index(defect_type)
            if defect_idx is not None:
                defect_onehot[defect_idx] = 1
        
        return {
            "image": image,
            "is_anomaly": torch.tensor(label, dtype=torch.long),
            "defect_labels": defect_onehot,
            "defect_type": defect_type,
            "path": img_path
        }
    
    def _get_defect_index(self, defect_type: str) -> Optional[int]:
        """Map le nom du défaut à un index. Returns None if unknown."""
        if defect_type in self.DEFECT_TYPES:
            return self.DEFECT_TYPES.index(defect_type)
        # Emit a warning for unexpected defect types
        import warnings
        warnings.warn(f"Defect type '{defect_type}' not recognized. Returning None.")
        return None


class MVTecMultiCategoryDataset(Dataset):
    """
    Dataset MVTec qui combine plusieurs catégories.
    Utile pour le pré-entraînement sur tout MVTec.
    """
    
    def __init__(
        self,
        root: str,
        categories: Optional[list] = None,
        split: str = "train",
        transform: Optional[Callable] = None
    ):
        self.datasets = []
        categories = categories or MVTecDataset.CATEGORIES
        
        for cat in categories:
            try:
                ds = MVTecDataset(root, cat, split, transform)
                self.datasets.append(ds)
            except FileNotFoundError:
                print(f"[WARN] Catégorie {cat} non trouvée, ignorée")
        
        # Calcule les offsets pour l'indexation
        self.offsets = [0]
        for ds in self.datasets:
            self.offsets.append(self.offsets[-1] + len(ds))
    
    def __len__(self) -> int:
        return self.offsets[-1]
    
    def __getitem__(self, idx: int) -> dict:
        # Trouve le dataset correspondant
        for i, offset in enumerate(self.offsets[:-1]):
            if idx < self.offsets[i + 1]:
                local_idx = idx - offset
                return self.datasets[i][local_idx]
        raise IndexError(f"Index {idx} hors limites")