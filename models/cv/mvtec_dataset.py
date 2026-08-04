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
from .augmentations import get_train_transform, generate_synthetic_anomaly


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
    """

    CATEGORIES = [
        "bottle", "cable", "capsule", "carpet", "grid", "hazelnut",
        "leather", "metal_nut", "pill", "screw", "tile", "toothbrush",
        "transistor", "wood", "zipper"
    ]

    # Mapping fixe catégorie -> index, utilisé pour le conditionnement FiLM.
    # Fixe et global (pas dépendant des catégories réellement chargées) pour que
    # l'embedding de catégorie reste cohérent entre les runs.
    CATEGORY_TO_IDX = {cat: i for i, cat in enumerate(CATEGORIES)}


    def __init__(
        self,
        root: str,
        category: str,
        split: str = "train",
        transform: Optional[Callable] = None
    ):
        self.root = Path(root)
        self.category = category
        self.category_idx = self.CATEGORY_TO_IDX[category]
        self.split = split
        self.transform = transform
        self.mask_aware = True

        if category not in self.CATEGORIES:
            raise ValueError(f"Catégorie '{category}' invalide. Choisir parmi: {self.CATEGORIES}")

        self.samples = []
        self.labels = []
        self.defect_types = []

        self._load_samples()

        if self.transform is None and self.split == "train" and self.mask_aware:
            self.transform = get_train_transform(self.category)
        elif self.transform is None:
            self.transform = lambda x: torch.tensor(np.array(x)).permute(2, 0, 1).float() / 255.0

    def _load_samples(self):
        split_dir = self.root / self.category / self.split

        if not split_dir.exists():
            raise FileNotFoundError(f"Dossier non trouvé: {split_dir}")

        for defect_dir in sorted(split_dir.iterdir()):
            if not defect_dir.is_dir():
                continue

            defect_type = defect_dir.name
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

        image = Image.open(img_path).convert("RGB")

        if self.split == "train" and self.mask_aware:
            if random.random() < 0.5:
                image, defect_type = generate_synthetic_anomaly(image)
                label = 1

        if self.transform:
            try:
                image = self.transform(image)
            except Exception:
                if isinstance(image, torch.Tensor):
                    image = Image.fromarray((image.cpu().permute(1, 2, 0).numpy() * 255).astype('uint8'))
                image = self.transform(image)

        return {
            "image": image,
            "is_anomaly": torch.tensor(label, dtype=torch.long),
            "defect_type": defect_type,
            "category": self.category,
            "category_idx": torch.tensor(self.category_idx, dtype=torch.long),
            "path": img_path
        }



class MVTecMultiCategoryDataset(Dataset):
    """
    Dataset MVTec qui combine plusieurs catégories.
    Expose aussi labels/categories/category_indices agrégés,
    nécessaires pour: le split stratifié et le sampler équilibré par catégorie.
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

        self.offsets = [0]
        for ds in self.datasets:
            self.offsets.append(self.offsets[-1] + len(ds))

        # Agrégation pour le split stratifié et le sampler équilibré
        self.labels = []
        self.categories = []
        self.category_indices = []
        for ds in self.datasets:
            self.labels.extend(ds.labels)
            self.categories.extend([ds.category] * len(ds))
            self.category_indices.extend([ds.category_idx] * len(ds))

    def __len__(self) -> int:
        return self.offsets[-1]

    def __getitem__(self, idx: int) -> dict:
        for i, offset in enumerate(self.offsets[:-1]):
            if idx < self.offsets[i + 1]:
                local_idx = idx - offset
                return self.datasets[i][local_idx]
        raise IndexError(f"Index {idx} hors limites")

    def category_sample_weights(self) -> torch.Tensor:
        """
        Calcule un poids par échantillon inversement proportionnel à la fréquence
        de sa catégorie, pour un WeightedRandomSampler équilibré.
        Évite que 'bottle' (209 images) domine 'screw' (potentiellement moins d'images).
        """
        from collections import Counter
        counts = Counter(self.categories)
        weights = [1.0 / counts[cat] for cat in self.categories]
        return torch.tensor(weights, dtype=torch.double)