import torch
from PIL import Image
from .model import MultiTaskDefectModel
from .dataset import GradingDataset, get_val_transforms, IDX_TO_GRADE, DEFECT_CLASSES
from pathlib import Path
from torch.utils.data import DataLoader
from sklearn.metrics import (accuracy_score, precision_score, recall_score, 
                             f1_score, roc_auc_score, confusion_matrix, classification_report)
import numpy as np
from tqdm import tqdm

class MultiViewGrader:
    def __init__(self, model_path):
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        current_dir = Path(__file__).resolve().parent
        self.transform = get_val_transforms()
        
        onnx_path = str(model_path).replace('.pth', '.onnx')
        self.use_onnx = Path(onnx_path).exists()
        
        if self.use_onnx:
            import onnxruntime as ort
            print(f"Loading ONNX model from {onnx_path}")
            self.ort_session = ort.InferenceSession(onnx_path, providers=['CPUExecutionProvider'])
        else:
            print(f"Loading PyTorch model from {model_path}")
            self.model = MultiTaskDefectModel(num_grades=4, num_defects=len(DEFECT_CLASSES), mvtec_weights_path=str(current_dir / "checkpoints" / "backbone_mvtec.pt"))
            try:
                self.model.load_state_dict(torch.load(model_path, map_location=self.device))
            except:
                self.model.load_state_dict(torch.load(model_path, map_location=self.device), strict=False)
            self.model.to(self.device)
            self.model.eval()

    def predict_defects_and_grade(self, list_of_image_paths):
        if not list_of_image_paths:
            return "Unknown", ["no_defect"]

        images_tensor = []
        for path in list_of_image_paths:
            img = Image.open(path).convert("RGB")
            img_tensor = self.transform(img)
            images_tensor.append(img_tensor)
            
        batch = torch.stack(images_tensor)
        
        if self.use_onnx:
            # ONNX Inference
            ort_inputs = {self.ort_session.get_inputs()[0].name: batch.numpy()}
            ort_outs = self.ort_session.run(None, ort_inputs)
            grade_logits = torch.tensor(ort_outs[0])
            defect_logits = torch.tensor(ort_outs[1])
        else:
            # PyTorch Inference
            batch = batch.to(self.device)
            with torch.no_grad():
                grade_logits, defect_logits = self.model(batch)
            
        # 1. Grade Prediction (Late Fusion: Max)
        grade_probs = torch.softmax(grade_logits, dim=1)
        grade_indices = torch.argmax(grade_probs, dim=1)
        predicted_grades = [IDX_TO_GRADE[idx.item()] for idx in grade_indices]
        final_grade = max(predicted_grades)
        
        # 2. Defects Prediction (Late Fusion: MAX Prob > 0.5)
        defect_probs = torch.sigmoid(defect_logits)
        # On prend la probabilité MAXIMALE parmi toutes les vues
        max_defect_probs, _ = torch.max(defect_probs, dim=0)
        
        detected_defects = []
        for i, prob in enumerate(max_defect_probs):
            if prob > 0.5 and DEFECT_CLASSES[i] != "no_defect":
                detected_defects.append(DEFECT_CLASSES[i])
                
        if not detected_defects:
            detected_defects.append("no_defect")
        
        # Règle métier : surcharger le grade si un défaut critique est détecté
        if "screen_crack" in detected_defects or "back_glass_crack" in detected_defects:
            final_grade = "D"
            
        print(f"Individual view grades: {predicted_grades}")
        print(f"Detected defects: {detected_defects}")
        return final_grade, detected_defects


def evaluate_test_set():
    """Runs a full evaluation report on the test dataset for both Grade and Defects."""
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    current_dir = Path(__file__).resolve().parent
    root_dir = current_dir.parent.parent
    
    test_dir = root_dir / "data" / "processed" / "smartphone_grading" / "test"
    test_ann = root_dir / "data" / "processed" / "annotations_test.json"
    model_path = root_dir / "models" / "cv" / "checkpoints" / "best_multitask_model.pth"
    
    transform = get_val_transforms()
    test_dataset = GradingDataset(test_dir, test_ann, transform)
    test_loader = DataLoader(test_dataset, batch_size=16, shuffle=False, num_workers=4)
    
    model = MultiTaskDefectModel(num_grades=4, num_defects=len(DEFECT_CLASSES), mvtec_weights_path=str(current_dir / "checkpoints" / "backbone_mvtec.pt"))
    model.load_state_dict(torch.load(model_path, map_location=device))
    model.to(device)
    model.eval()
    
    all_grade_preds = []
    all_grade_labels = []
    all_grade_probs = []
    all_defect_preds = []
    all_defect_labels = []
    all_defect_probs = []
    
    print("Running full evaluation on Test Set...")
    with torch.no_grad():
        for images, grades, defects in tqdm(test_loader):
            images, grades, defects = images.to(device), grades.to(device), defects.to(device)
            
            grade_logits, defect_logits = model(images)
            
            # 1. Grade
            grade_probs = torch.softmax(grade_logits, dim=1)
            _, predicted_grades = torch.max(grade_logits.data, 1)
            all_grade_preds.extend(predicted_grades.cpu().numpy())
            all_grade_labels.extend(grades.cpu().numpy())
            all_grade_probs.extend(grade_probs.cpu().numpy())
            
            # 2. Defects
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
    
    print("\n" + "="*60)
    print(" PROFESSIONAL MODEL EVALUATION REPORT (TEST SET)")
    print("="*60)
    
    # ==========================================
    # RAPPORT TÂCHE 1 : GRADE (A/B/C/D)
    # ==========================================
    target_names_grade = ["Grade A", "Grade B", "Grade C", "Grade D"]
    print("\n[1] GRADE TASK (Multi-Class):")
    print(classification_report(all_grade_labels, all_grade_preds, target_names=target_names_grade, zero_division=0))
    
    p_grade = precision_score(all_grade_labels, all_grade_preds, average='macro', zero_division=0)
    r_grade = recall_score(all_grade_labels, all_grade_preds, average='macro', zero_division=0)
    f1_grade = f1_score(all_grade_labels, all_grade_preds, average='macro', zero_division=0)
    try:
        roc_grade = roc_auc_score(all_grade_labels, all_grade_probs, multi_class='ovr', average='macro')
    except ValueError:
        roc_grade = 0.0
        
    print(f"Global Macro Metrics -> Precision: {p_grade:.4f} | Recall: {r_grade:.4f} | F1: {f1_grade:.4f} | ROC-AUC: {roc_grade:.4f}")
    
    cm = confusion_matrix(all_grade_labels, all_grade_preds)
    print("\nConfusion Matrix (Rows=True, Cols=Pred):")
    print("       A    B    C    D")
    for i, row in enumerate(cm):
        print(f"{target_names_grade[i][6]}  ", row)
        
    # ==========================================
    # RAPPORT TÂCHE 2 : DEFECTS (Multi-Label)
    # ==========================================
    print("\n" + "-"*60)
    print("[2] DEFECT TASK (Multi-Label):")
    
    exact_match = accuracy_score(all_defect_labels, all_defect_preds)
    p_def = precision_score(all_defect_labels, all_defect_preds, average='macro', zero_division=0)
    r_def = recall_score(all_defect_labels, all_defect_preds, average='macro', zero_division=0)
    f1_def = f1_score(all_defect_labels, all_defect_preds, average='macro', zero_division=0)
    
    # --- CORRECTION DU WARNING ROC-AUC ---
    valid_defect_indices = np.where(all_defect_labels.sum(axis=0) > 0)[0]
    if len(valid_defect_indices) > 1:
        roc_def = roc_auc_score(
            all_defect_labels[:, valid_defect_indices], 
            all_defect_probs[:, valid_defect_indices], 
            average='macro'
        )
    else:
        roc_def = 0.0
        
    print(f"Global Macro Metrics -> Precision: {p_def:.4f} | Recall: {r_def:.4f} | F1: {f1_def:.4f} | ROC-AUC: {roc_def:.4f}")
    print(f"Exact Match Accuracy (All defects correct): {exact_match*100:.2f}%")
    
    print("\nClassification Report (Defects):")
    # S'assurer de ne rapporter que les classes présentes pour éviter les warnings
    present_defect_classes = [DEFECT_CLASSES[i] for i in valid_defect_indices]
    if len(present_defect_classes) > 0:
        print(classification_report(all_defect_labels[:, valid_defect_indices], all_defect_preds[:, valid_defect_indices], target_names=present_defect_classes, zero_division=0))
    
    print("="*60)


# --- Example Usage ---
if __name__ == "__main__":
    current_dir = Path(__file__).resolve().parent
    root_dir = current_dir.parent.parent
    
    # 1. Run the full professional test set evaluation
    evaluate_test_set()
    
    # 2. Example of using the MultiViewGrader for a single product inference
    print("\nTesting MultiViewGrader on sample images...")
    grader = MultiViewGrader(str(root_dir / "models" / "cv" / "checkpoints" / "best_multitask_model.pth"))
    
    val_dir = root_dir / "data" / "processed" / "smartphone_grading" / "val"
    user_uploaded_images = [
        str(val_dir / "ds2_good_0000" / "view_00.png"),    
        str(val_dir / "ds2_scratch_0420" / "view_00.png"), 
        str(val_dir / "ds1_cracked_0043" / "view_00.png")  
    ]
    
    final_grade, detected_defects = grader.predict_defects_and_grade(user_uploaded_images)
    print(f"FINAL PRODUCT GRADE: {final_grade}")
    print(f"DEFECTS TO REPAIR: {detected_defects}") 