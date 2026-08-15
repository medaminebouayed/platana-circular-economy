import torch
import torch.nn as nn
from torch.optim import AdamW
from torch.optim.lr_scheduler import ReduceLROnPlateau
from torch.utils.data import DataLoader
from tqdm import tqdm
from .model import MultiTaskDefectModel
from .dataset import GradingDataset, get_train_transforms, get_val_transforms
from pathlib import Path
from sklearn.metrics import (accuracy_score, precision_score, recall_score, 
                             f1_score, roc_auc_score, confusion_matrix)
import numpy as np
import argparse
import os
import mlflow
from dotenv import load_dotenv
from models.artifacts import (create_version_dir, promote_version,
                              read_active_manifest, resolve_latest_artifact, write_manifest)


def _safe_mlflow(fn, *args, **kwargs):
    """Run an MLflow tracking call, but never let tracking failure abort training."""
    try:
        return fn(*args, **kwargs)
    except Exception as exc:
        print(f"[WARN] MLflow call '{getattr(fn, '__name__', 'fn')}' skipped: {exc}")
        return None


def train(mode='continue', promotion_policy='always', min_f1_improvement=0.002, epochs=100):
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    
    current_dir = Path(__file__).resolve().parent
    root_dir = current_dir.parent.parent
    load_dotenv(root_dir / ".env")
    tracking_uri = os.getenv("MLFLOW_TRACKING_URI")
    if tracking_uri:
        _safe_mlflow(mlflow.set_tracking_uri, tracking_uri)
    _safe_mlflow(mlflow.set_experiment, os.getenv("MLFLOW_CV_EXPERIMENT", "platana-cv-grading"))
    _safe_mlflow(mlflow.start_run, run_name=f"cv-{mode}")
    checkpoint_dir = root_dir / "models" / "cv" / "checkpoints"
    version_id, version_dir = create_version_dir(checkpoint_dir, "cv")
    
    train_dir = root_dir / "data" / "processed" / "smartphone_grading" / "train"
    train_ann = root_dir / "data" / "processed" / "annotations_train.json"
    val_dir = root_dir / "data" / "processed" / "smartphone_grading" / "val"
    val_ann = root_dir / "data" / "processed" / "annotations_val.json"
    
    train_transform = get_train_transforms()
    val_transform = get_val_transforms()

    train_dataset = GradingDataset(train_dir, train_ann, train_transform)
    val_dataset = GradingDataset(val_dir, val_ann, val_transform)
    
    train_loader = DataLoader(train_dataset, batch_size=16, shuffle=True, num_workers=4)
    val_loader = DataLoader(val_dataset, batch_size=16, shuffle=False, num_workers=4)
    
    backbone_path, backbone_version = resolve_latest_artifact(
        checkpoint_dir, "backbone.pt", pointer_name="latest_backbone.json"
    )
    mvtec_path = str(backbone_path or (current_dir / "checkpoints" / "backbone_mvtec.pt"))
    model = MultiTaskDefectModel(num_grades=4, num_defects=3, mvtec_weights_path=mvtec_path).to(device)
    
    # --- GESTION DES MODES ---
    if mode == 'continue':
        grading_model_path, grading_version = resolve_latest_artifact(
            checkpoint_dir, "model.pth", pointer_name="latest_training.json"
        )
        grading_model_path = grading_model_path or (checkpoint_dir / "best_grading_model.pth")
        if grading_model_path.exists():
            print(f"Mode CONTINUE: Loading existing grading weights from {grading_model_path}")
            state_dict = torch.load(grading_model_path, map_location='cpu')
            
            # Adapter les clés (compatibilité nom de tête)
            new_state_dict = {}
            for k, v in state_dict.items():
                new_k = k.replace('grading_head', 'grade_head')
                new_state_dict[new_k] = v
                
            model.load_state_dict(new_state_dict, strict=False)
            
            # Differential Learning Rates
            backbone_grade_params = list(model.backbone.parameters()) + list(model.grade_head.parameters())
            defect_params = model.defect_head.parameters()
            
            optimizer = AdamW([
                {'params': backbone_grade_params, 'lr': 1e-5}, 
                {'params': defect_params, 'lr': 1e-4}          
            ])
            print("Differential Learning Rates applied.")
        else:
            print("Ancien modèle non trouvé, entraînement from scratch activé.")
            mode = 'from_scratch'
            
    if mode == 'from_scratch':
        print("Mode FROM SCRATCH: Training both heads together.")
        optimizer = AdamW(model.parameters(), lr=1e-4)

    # Loss functions
    criterion_grade = nn.CrossEntropyLoss()
    criterion_defect = nn.BCEWithLogitsLoss()
    
    scheduler = ReduceLROnPlateau(optimizer, mode='max', factor=0.5, patience=3)
    
    best_val_f1 = 0.0
    early_stopping_rounds = 25
    epochs_without_improvement = 0
    best_model_path = version_dir / "model.pth"
    _safe_mlflow(mlflow.log_params, {
        "mode": mode, "device": str(device), "epochs": epochs, "batch_size": 16,
        "optimizer": "AdamW", "scheduler": "ReduceLROnPlateau", "defect_threshold": 0.5,
        "local_model_version": version_id, "backbone_version": backbone_version or "legacy",
    })

    for epoch in range(epochs):
        model.train()
        running_loss = 0.0
        running_loss_grade = 0.0
        running_loss_defect = 0.0
        
        for images, grades, defects in tqdm(train_loader, desc=f"Epoch {epoch+1}/{epochs} [Training]"):
            images, grades, defects = images.to(device), grades.to(device), defects.to(device)
            
            optimizer.zero_grad()
            grade_logits, defect_logits = model(images)
            
            loss_grade = criterion_grade(grade_logits, grades)
            loss_defect = criterion_defect(defect_logits, defects)
            
            total_loss = loss_grade + loss_defect
            total_loss.backward()
            optimizer.step()
            
            running_loss += total_loss.item()
            running_loss_grade += loss_grade.item()
            running_loss_defect += loss_defect.item()
            
        print(f"\n--- Epoch {epoch+1} Evaluation ---")
        print(f"Train Total Loss: {running_loss/len(train_loader):.4f} (Grade: {running_loss_grade/len(train_loader):.4f}, Defect: {running_loss_defect/len(train_loader):.4f})")
        
        # Validation
        model.eval()
        all_grade_preds = []
        all_grade_labels = []
        all_grade_probs = []
        all_defect_preds = []
        all_defect_labels = []
        all_defect_probs = []
        
        with torch.no_grad():
            for images, grades, defects in tqdm(val_loader, desc="Validating"):
                images, grades, defects = images.to(device), grades.to(device), defects.to(device)
                
                grade_logits, defect_logits = model(images)
                
                # 1. Grade Predictions & Probs
                grade_probs = torch.softmax(grade_logits, dim=1)
                _, predicted_grades = torch.max(grade_logits.data, 1)
                all_grade_preds.extend(predicted_grades.cpu().numpy())
                all_grade_labels.extend(grades.cpu().numpy())
                all_grade_probs.extend(grade_probs.cpu().numpy())
                
                # 2. Defects Predictions & Probs
                defect_probs = torch.sigmoid(defect_logits)
                predicted_defects = (defect_probs > 0.5).float()
                all_defect_preds.extend(predicted_defects.cpu().numpy())
                all_defect_labels.extend(defects.cpu().numpy())
                all_defect_probs.extend(defect_probs.cpu().numpy())
        
        # Conversion en arrays numpy
        all_grade_preds = np.array(all_grade_preds)
        all_grade_labels = np.array(all_grade_labels)
        all_grade_probs = np.array(all_grade_probs)
        all_defect_preds = np.array(all_defect_preds)
        all_defect_labels = np.array(all_defect_labels)
        all_defect_probs = np.array(all_defect_probs)
        
        # ==========================================
        # MÉTRIQUES TÂCHE 1 : GRADE (A/B/C/D)
        # ==========================================
        acc_grade = accuracy_score(all_grade_labels, all_grade_preds)
        p_grade = precision_score(all_grade_labels, all_grade_preds, average='macro', zero_division=0)
        r_grade = recall_score(all_grade_labels, all_grade_preds, average='macro', zero_division=0)
        f1_grade = f1_score(all_grade_labels, all_grade_preds, average='macro', zero_division=0)
        
        try:
            roc_grade = roc_auc_score(all_grade_labels, all_grade_probs, multi_class='ovr', average='macro')
        except ValueError:
            roc_grade = 0.0

        cm_grade = confusion_matrix(all_grade_labels, all_grade_preds)
        
        print(f"\n[GRADE TASK] Acc: {acc_grade*100:.2f}% | P: {p_grade:.4f} | R: {r_grade:.4f} | F1: {f1_grade:.4f} | ROC-AUC: {roc_grade:.4f}")
        print("Confusion Matrix:")
        print("       A    B    C    D")
        print(cm_grade)
        
        # ==========================================
        # MÉTRIQUES TÂCHE 2 : DEFECTS (Multi-Label)
        # ==========================================
        exact_match = accuracy_score(all_defect_labels, all_defect_preds)
        p_def = precision_score(all_defect_labels, all_defect_preds, average='macro', zero_division=0)
        r_def = recall_score(all_defect_labels, all_defect_preds, average='macro', zero_division=0)
        f1_def = f1_score(all_defect_labels, all_defect_preds, average='macro', zero_division=0)
        
        # On ne calcule le ROC-AUC que pour les défauts qui ont au moins 1 exemple positif dans y_true
        valid_defect_indices = np.where(all_defect_labels.sum(axis=0) > 0)[0]
        if len(valid_defect_indices) > 1:
            roc_def = roc_auc_score(
                all_defect_labels[:, valid_defect_indices], 
                all_defect_probs[:, valid_defect_indices], 
                average='macro'
            )
        else:
            roc_def = 0.0
        
        print(f"[DEFECT TASK] Exact: {exact_match*100:.2f}% | P: {p_def:.4f} | R: {r_def:.4f} | F1: {f1_def:.4f} | ROC-AUC: {roc_def:.4f}")
        print("-" * 50)
        _safe_mlflow(mlflow.log_metrics, {
            "train_loss": running_loss / len(train_loader),
            "train_grade_loss": running_loss_grade / len(train_loader),
            "train_defect_loss": running_loss_defect / len(train_loader),
            "val_grade_accuracy": acc_grade,
            "val_grade_precision_macro": p_grade,
            "val_grade_recall_macro": r_grade,
            "val_grade_f1_macro": f1_grade,
            "val_grade_roc_auc": roc_grade,
            "val_defect_exact_match": exact_match,
            "val_defect_precision_macro": p_def,
            "val_defect_recall_macro": r_def,
            "val_defect_f1_macro": f1_def,
            "val_defect_roc_auc": roc_def,
        }, step=epoch + 1)
        
        # On garde le F1 du Grade pour le scheduler et la sauvegarde
        f1_macro = f1_grade
        scheduler.step(f1_macro)
        
        if f1_macro > best_val_f1:
            epochs_without_improvement = 0
            best_val_f1 = f1_macro
            best_model_path.parent.mkdir(parents=True, exist_ok=True)
            torch.save(model.state_dict(), best_model_path)
            print(f"🚀 New best model saved! (F1: {best_val_f1:.4f})\n")
        else:
            epochs_without_improvement += 1
            if epochs_without_improvement >= early_stopping_rounds:
                print(f"Early stopping triggered after {epoch+1} epochs.")
                break 

    if best_model_path.exists():
        active_run = mlflow.active_run()
        manifest_path = write_manifest(version_dir, {
            "version_id": version_id,
            "model_type": "cv-multitask-grading-defects",
            "mlflow_run_id": active_run.info.run_id if active_run else None,
            "metrics": {"best_val_grade_f1_macro": float(best_val_f1)},
            "parents": {"backbone_version": backbone_version or "legacy"},
            "artifacts": {"model": "model.pth"},
        })
        active_manifest = read_active_manifest(checkpoint_dir, "latest_training.json")
        active_f1 = (active_manifest or {}).get("metrics", {}).get("best_val_grade_f1_macro")
        promoted = (
            promotion_policy == "always"
            or active_f1 is None
            or (promotion_policy == "if-better" and best_val_f1 >= float(active_f1) + min_f1_improvement)
        ) and promotion_policy != "never"
        if promoted:
            promote_version(
                checkpoint_dir, version_id, {"model": "model.pth"},
                pointer_name="latest_training.json",
            )
        _safe_mlflow(mlflow.set_tag, "promotion_status", "promoted" if promoted else "candidate_not_promoted")
        _safe_mlflow(mlflow.set_tag, "promotion_policy", promotion_policy)
        _safe_mlflow(mlflow.log_artifact, str(best_model_path), artifact_path="model")
        _safe_mlflow(mlflow.log_artifact, str(manifest_path), artifact_path="model")
    _safe_mlflow(mlflow.log_metric, "best_val_grade_f1_macro", best_val_f1)
    _safe_mlflow(mlflow.end_run)
    if best_model_path.exists():
        print("[OK] Active CV training pointer updated." if promoted else "[INFO] CV candidate retained; active version unchanged.")
        return promoted
    return False

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', type=str, default='continue', choices=['from_scratch', 'continue'],
                        help="'from_scratch' to train both heads from MVTec backbone, 'continue' to load existing grading model and add defect head.")
    parser.add_argument("--promotion-policy", choices=["always", "if-better", "never"], default="always")
    parser.add_argument("--min-f1-improvement", type=float, default=0.002,
                        help="Absolute validation F1 gain needed by if-better.")
    parser.add_argument("--epochs", type=int, default=100,
                        help="Number of epochs (default 100; pass 1 for a quick smoke test).")
    args = parser.parse_args()
    
    train(args.mode, args.promotion_policy, args.min_f1_improvement, args.epochs)
