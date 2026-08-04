import torch
from torch.utils.data import Dataset, DataLoader
from torchvision import transforms
from PIL import Image
import json
from pathlib import Path

# Mapping grades to numerical classes
GRADE_TO_IDX = {"A": 0, "B": 1, "C": 2, "D": 3}
IDX_TO_GRADE = {v: k for k, v in GRADE_TO_IDX.items()}

# Les 5 défauts spécifiques que le modèle va apprendre à détecter
DEFECT_CLASSES = ["no_defect", "screen_crack", "cosmetic_scratch"]

def normalize_defect_name(d):
    """Mappe les noms de défauts de ton dataset vers les classes standardisées."""
    d = d.lower()
    if "crack" in d: return "screen_crack"
    if "scratch" in d: return "cosmetic_scratch"
    if "oil" in d or "stain" in d: return "cosmetic_scratch"
    if "good" in d: return "no_defect"
    return d

class GradingDataset(Dataset):
    def __init__(self, root_dir, annotation_file, transform=None):
        self.root_dir = Path(root_dir)
        with open(annotation_file, 'r') as f:
            self.annotations = json.load(f)
        self.product_ids = list(self.annotations.keys())
        self.transform = transform

    def __len__(self):
        return len(self.product_ids)

    def __getitem__(self, idx):
        prod_id = self.product_ids[idx]
        ann = self.annotations[prod_id]
        
        img_path = self.root_dir / prod_id / "view_00.png"
        image = Image.open(img_path).convert("RGB")
        
        if self.transform:
            image = self.transform(image)
            
        grade_idx = GRADE_TO_IDX[ann["grade"]]
        
        # Création du vecteur multi-label pour les défauts
        defect_vector = torch.zeros(len(DEFECT_CLASSES), dtype=torch.float32)
        raw_defects = ann.get("defects", [])
        
        if not raw_defects or raw_defects == []:
            raw_defects = ["no_defect"]
            
        for d in raw_defects:
            norm_d = normalize_defect_name(d)
            if norm_d in DEFECT_CLASSES:
                defect_vector[DEFECT_CLASSES.index(norm_d)] = 1.0
                
        # Si aucun défaut n'a été mappé mais que le grade n'est pas A, on met no_defect à 0
        if defect_vector.sum() == 0 and ann["grade"] != "A":
            defect_vector[DEFECT_CLASSES.index("no_defect")] = 0.0
            
        return image, torch.tensor(grade_idx, dtype=torch.long), defect_vector

def get_train_transforms():
    return transforms.Compose([
        transforms.Resize((224, 224)),
        transforms.RandomHorizontalFlip(p=0.5),
        transforms.ColorJitter(brightness=0.1, contrast=0.1),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
    ])

def get_val_transforms():
    return transforms.Compose([
        transforms.Resize((224, 224)),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
    ])