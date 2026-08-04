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

def train(mode='continue'):
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    
    current_dir = Path(__file__).resolve().parent
    root_dir = current_dir.parent.parent
    
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
    
    mvtec_path = str(current_dir / "checkpoints" / "backbone_mvtec.pt")
    model = MultiTaskDefectModel(num_grades=4, num_defects=3, mvtec_weights_path=mvtec_path).to(device)
    
    # --- GESTION DES MODES ---
    if mode == 'continue':
        grading_model_path = root_dir / "models" / "cv" / "checkpoints" / "best_grading_model.pth"
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
    
    epochs = 100
    best_val_f1 = 0.0
    early_stopping_rounds = 25
    epochs_without_improvement = 0

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
        
        # On garde le F1 du Grade pour le scheduler et la sauvegarde
        f1_macro = f1_grade
        scheduler.step(f1_macro)
        
        if f1_macro > best_val_f1:
            epochs_without_improvement = 0
            best_val_f1 = f1_macro
            save_path = root_dir / "models" / "cv" / "checkpoints" / "best_multitask_model.pth"
            save_path.parent.mkdir(parents=True, exist_ok=True)
            torch.save(model.state_dict(), save_path)
            print(f"🚀 New best model saved! (F1: {best_val_f1:.4f})\n")
        else:
            epochs_without_improvement += 1
            if epochs_without_improvement >= early_stopping_rounds:
                print(f"Early stopping triggered after {epoch+1} epochs.")
                break 

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', type=str, default='continue', choices=['from_scratch', 'continue'],
                        help="'from_scratch' to train both heads from MVTec backbone, 'continue' to load existing grading model and add defect head.")
    args = parser.parse_args()
    
    train(mode=args.mode)