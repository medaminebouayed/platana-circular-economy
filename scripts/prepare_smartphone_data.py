"""
Prepare 3 Kaggle smartphone datasets into grading format (A-D).

Dataset 1 (cracked-and-intact): intact->A, cracked->D
Dataset 2 (defect-segmentation): grade by defect type + area from masks
Dataset 3 (mobile-phone-image): all -> D (badly damaged)

Grading logic:
  stain: tiny spots ~0.03% area -> B (barely visible cosmetic)
  oil:   blobs ~3.8% area -> B (cosmetic) or C if large
  scratch: lines ~0.2% area -> C (physical damage)
  good / intact -> A
  cracked / damaged -> D
"""

import json
import shutil
import random
from pathlib import Path
from collections import defaultdict

import numpy as np
from PIL import Image


PROJECT_ROOT = Path(__file__).resolve().parent.parent
EXTERNAL = PROJECT_ROOT / "data" / "external"
PROCESSED = PROJECT_ROOT / "data" / "processed"
OUTPUT = PROCESSED / "smartphone_grading"

def analyze_mask(mask_path: Path) -> dict:
    mask = np.array(Image.open(mask_path).convert("L")) > 0
    return {"ratio": float(mask.mean())}

def assign_grade(defect: str, ratio: float) -> str:
    if defect == "good":        return "A"
    if defect == "stain":       return "B"  # tiny spots, barely visible
    if defect == "oil":         return "C" if ratio > 0.05 else "B"
    if defect == "scratch":     return "C"  # physical damage
    if defect == "crack":       return "D"
    return "C"


# ── dataset 1: cracked-and-intact-smartphone-images-dataset ──────────────

def process_dataset1(output_dir: Path) -> dict:
    root = EXTERNAL / "cracked-and-intact-smartphone-images-dataset"
    annotations = {}
    pid = 0

    for f in sorted((root / "Image_phones").glob("*.png")):
        prod_id = f"ds1_intact_{pid:04d}"
        out_dir = output_dir / prod_id
        out_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, out_dir / "view_00.png")
        annotations[prod_id] = {
            "grade": "A", "defects": [],
            "category": "smartphone", "brand": "unknown", "model": f.stem
        }
        pid += 1

    for f in sorted((root / "Image_brokenphones").glob("*.PNG")):
        prod_id = f"ds1_cracked_{pid:04d}"
        out_dir = output_dir / prod_id
        out_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, out_dir / "view_00.png")
        annotations[prod_id] = {
            "grade": "D", "defects": ["crack"],
            "category": "smartphone", "brand": "unknown", "model": "unknown"
        }
        pid += 1

    print(f"  Dataset 1: {pid} produits (intact->A, cracked->D)")
    return annotations


# ── dataset 2: mobile-phone-defect-segmentation-dataset ──────────────────

def process_dataset2(output_dir: Path) -> dict:
    root = EXTERNAL / "mobile-phone-defect-segmentation-dataset"
    annotations = {}
    pid = 0

    # good -> A
    for f in sorted((root / "good").glob("*.png")):
        prod_id = f"ds2_good_{pid:04d}"
        out_dir = output_dir / prod_id
        out_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, out_dir / "view_00.png")
        annotations[prod_id] = {
            "grade": "A", "defects": [],
            "category": "smartphone", "brand": "unknown", "model": "unknown"
        }
        pid += 1

    defect_map = {
        "oil":     (root / "oil",     root / "ground_truth_2", "Oil"),
        "scratch": (root / "scratch", root / "ground_truth_1", "Scr"),
        "stain":   (root / "stain",   root / "ground_truth_1", "Sta"),
    }

    for defect_name, (src_dir, gt_dir, prefix) in defect_map.items():
        if not src_dir.exists():
            continue
        for f in sorted(src_dir.glob("*.jpg")):
            stem = f.stem
            gt_path = gt_dir / f"{stem}.png"
            ratio = analyze_mask(gt_path)["ratio"] if gt_path.exists() else 0.5
            grade = assign_grade(defect_name, ratio)

            prod_id = f"ds2_{defect_name}_{pid:04d}"
            out_dir = output_dir / prod_id
            out_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, out_dir / "view_00.png")
            annotations[prod_id] = {
                "grade": grade,
                "defects": [defect_name],
                "category": "smartphone",
                "brand": "unknown",
                "model": "unknown"
            }
            pid += 1

    print(f"  Dataset 2: {pid} produits (smart mask grading)")
    return annotations


# ── dataset 3: mobile-phone-image-dataset ────────────────────────────────

def process_dataset3(output_dir: Path) -> dict:
    root = EXTERNAL / "mobile-phone-image-dataset"
    annotations = {}
    pid = 0

    img_dir = root / "Mobile_image" / "Mobile_image"
    if img_dir.exists():
        for f in sorted(img_dir.glob("*.jpg")):
            prod_id = f"ds3_intact_{pid:04d}"
            out_dir = output_dir / prod_id
            out_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, out_dir / "view_00.png")
            annotations[prod_id] = {
                "grade": "D", "defects": ["crack", "scratch"],
                "category": "smartphone", "brand": "unknown", "model": "unknown"
            }
            pid += 1

    print(f"  Dataset 3: {pid} produits (all -> D)")
    return annotations


# ── main ─────────────────────────────────────────────────────────────────

def main():
    random.seed(42)

    print("=" * 60)
    print("Preparation des donnees smartphones (grading A-D)")
    print("=" * 60)

    temp_dir = PROCESSED / "smartphone_temp"
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
    temp_dir.mkdir(parents=True, exist_ok=True)

    print("\n[1/3] Traitement des datasets...")
    all_annotations = {}
    all_annotations.update(process_dataset1(temp_dir))
    all_annotations.update(process_dataset2(temp_dir))
    all_annotations.update(process_dataset3(temp_dir))

    grade_counts = defaultdict(int)
    for ann in all_annotations.values():
        grade_counts[ann["grade"]] += 1
    print(f"\n  Distribution totale: {dict(grade_counts)}")

    # Stratified split: group by grade, then split each group
    print("\n[2/3] Split stratifie train/val/test (70/15/15)...")
    by_grade = defaultdict(list)
    for pid, ann in all_annotations.items():
        by_grade[ann["grade"]].append(pid)

    train_ids, val_ids, test_ids = [], [], []
    for grade, ids in sorted(by_grade.items()):
        random.shuffle(ids)
        n = len(ids)
        n_train = max(1, int(n * 0.70))
        n_val = max(1, int(n * 0.15))
        train_ids.extend(ids[:n_train])
        val_ids.extend(ids[n_train:n_train + n_val])
        test_ids.extend(ids[n_train + n_val:])
        print(f"  Grade {grade}: {n} total -> {n_train} train, {n_val} val, {n - n_train - n_val} test")

    random.shuffle(train_ids)
    random.shuffle(val_ids)
    random.shuffle(test_ids)

    def copy_split(ids, split_name):
        split_dir = OUTPUT / split_name
        if split_dir.exists():
            shutil.rmtree(split_dir)
        for prod_id in ids:
            src = temp_dir / prod_id
            dst = split_dir / prod_id
            if src.exists():
                dst.mkdir(parents=True, exist_ok=True)
                for img in src.glob("*"):
                    shutil.copy2(img, dst / img.name)
        split_anns = {pid: all_annotations[pid] for pid in ids}
        ann_file = PROCESSED / f"annotations_{split_name}.json"
        with open(ann_file, "w") as f:
            json.dump(split_anns, f, indent=2)
        split_grades = defaultdict(int)
        for ann in split_anns.values():
            split_grades[ann["grade"]] += 1
        print(f"  {split_name}: {len(ids)} produits {dict(split_grades)}")

    copy_split(train_ids, "train")
    copy_split(val_ids, "val")
    copy_split(test_ids, "test")

    shutil.rmtree(temp_dir)

    print("\n[3/3] Resume final:")
    all_grades = defaultdict(int)
    for ids in [train_ids, val_ids, test_ids]:
        for pid in ids:
            all_grades[all_annotations[pid]["grade"]] += 1
    print(f"  Total: {len(all_annotations)} produits")
    print(f"  Train: {len(train_ids)} | Val: {len(val_ids)} | Test: {len(test_ids)}")
    print(f"  Grades: {dict(all_grades)}")
    print(f"\n[OK] Preparation terminee!")


if __name__ == "__main__":
    main()
