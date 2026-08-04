import torch
import torch.nn as nn
from pathlib import Path
from torch.utils.data import DataLoader
from sklearn.metrics import (accuracy_score, precision_score, recall_score, 
                             f1_score, roc_auc_score, confusion_matrix, classification_report)
import numpy as np
from tqdm import tqdm
from torchvision import transforms

from backbone import create_backbone
from pretrain_backbone import CategoryFiLM, collate_with_category
from mvtec_dataset import MVTecMultiCategoryDataset, MVTecDataset

def evaluate_mvtec_backbone():
    """Runs a full evaluation report on the MVTec AD test dataset using the pre-trained backbone."""
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    current_dir = Path(__file__).resolve().parent
    root_dir = current_dir.parent.parent
    
    data_root = root_dir / "data" / "external" / "mvtec_ad"
    model_path = current_dir / "checkpoints" / "backbone_mvtec.pt"
    
    if not model_path.exists():
        print(f"Error: Backbone weights not found at {model_path}.")
        print("Please run pretrain_backbone.py first to generate the weights.")
        return
        
    print(f"Loading weights from {model_path}...")
    checkpoint = torch.load(model_path, map_location=device)
    config = checkpoint.get("config", {})
    embed_dim = checkpoint.get("embed_dim", 768)
    
    # Check if heads were saved (requires the updated pretrain_backbone.py)
    if "anomaly_head_state_dict" not in checkpoint:
        print("WARNING: 'anomaly_head_state_dict' not found in checkpoint!")
        print("You are likely using an older checkpoint. Please retrain the backbone using the updated pretrain_backbone.py to save the anomaly head.")
        return

    val_transform = transforms.Compose([
        transforms.Resize((224, 224)),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
    ])
    
    print("[INFO] Loading MVTec dataset...")
    test_dataset = MVTecMultiCategoryDataset(
        root=str(data_root),
        categories=None,  # All categories
        split="test",
        transform=val_transform
    )
    
    test_loader = DataLoader(
        test_dataset, batch_size=16, shuffle=False, 
        num_workers=4, pin_memory=True, collate_fn=collate_with_category
    )
    
    print("[INFO] Initializing models...")
    backbone_name = config.get("backbone", "vit_base_patch16_224")
    backbone, _ = create_backbone(model_name=backbone_name, pretrained=False, num_classes=0)
    backbone.load_state_dict(checkpoint["backbone_state_dict"])
    backbone.to(device)
    backbone.eval()
    
    num_categories = len(MVTecDataset.CATEGORIES)
    category_film = CategoryFiLM(num_categories=num_categories, embed_dim=embed_dim)
    category_film.load_state_dict(checkpoint["category_film_state_dict"])
    category_film.to(device)
    category_film.eval()
    
    anomaly_head = nn.Sequential(
        nn.Linear(embed_dim, 256),
        nn.ReLU(),
        nn.Dropout(0.3),
        nn.Linear(256, 2)
    )
    anomaly_head.load_state_dict(checkpoint["anomaly_head_state_dict"])
    anomaly_head.to(device)
    anomaly_head.eval()

    all_preds = []
    all_labels = []
    all_probs = []
    
    print("Running full evaluation on MVTec Test Set...")
    with torch.no_grad():
        for batch in tqdm(test_loader):
            images = batch["image"].to(device)
            category_idx = batch["category_idx"].to(device)
            is_anomaly = batch["is_anomaly"].to(device)
            
            embeddings = backbone(images)
            embeddings = category_film(embeddings, category_idx)
            anomaly_logits = anomaly_head(embeddings)
            
            probs = torch.softmax(anomaly_logits, dim=1)[:, 1] # Probability of anomaly (class 1)
            predicted = torch.argmax(anomaly_logits, dim=1)
            
            all_preds.extend(predicted.cpu().numpy())
            all_labels.extend(is_anomaly.cpu().numpy())
            all_probs.extend(probs.cpu().numpy())
            
    all_preds = np.array(all_preds)
    all_labels = np.array(all_labels)
    all_probs = np.array(all_probs)
    
    print("\n" + "="*50)
    print(" BACKBONE MVTec EVALUATION REPORT")
    print("="*50)
    
    # 1. Classification Report
    target_names = ["Normal (0)", "Anomaly (1)"]
    print("\n[1] Classification Report:")
    print(classification_report(all_labels, all_preds, target_names=target_names, zero_division=0))
    
    # 2. Global Metrics
    acc = accuracy_score(all_labels, all_preds)
    f1_macro = f1_score(all_labels, all_preds, average='macro', zero_division=0)
    print(f"[2] Global Metrics:")
    print(f"Accuracy:  {acc*100:.2f}%")
    print(f"F1-Score:  {f1_macro:.4f} (Macro)")
    
    # 3. ROC-AUC
    try:
        roc_auc = roc_auc_score(all_labels, all_probs)
        print(f"\n[3] ROC-AUC:")
        print(f"ROC-AUC Score: {roc_auc:.4f}")
    except ValueError as e:
        print(f"\n[3] ROC-AUC: Could not calculate - {e}")
        
    # 4. Confusion Matrix
    cm = confusion_matrix(all_labels, all_preds)
    print(f"\n[4] Confusion Matrix (Rows=True, Cols=Pred):")
    print("           Normal   Anomaly")
    print(f"Normal    {cm[0][0]:<8} {cm[0][1]}")
    if len(cm) > 1:
        print(f"Anomaly   {cm[1][0]:<8} {cm[1][1]}")
    print("="*50)

if __name__ == "__main__":
    evaluate_mvtec_backbone()
