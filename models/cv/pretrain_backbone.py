"""
Pré-entraînement du backbone sur MVTec AD (mono-vue).
Le backbone apprend à reconnaître les défauts visuels.
Les poids sont sauvegardés pour le fine-tuning multi-vues.
"""

import argparse
from pathlib import Path

import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader
from torchvision import transforms
from tqdm import tqdm

from backbone import create_backbone
from mvtec_dataset import MVTecMultiCategoryDataset, MVTecDataset


class PretrainRunner:
    """
    Entraîne le backbone sur MVTec AD pour la détection d'anomalies.
    """
    
    def __init__(self, config: dict):
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.config = config
        
        # Backbone
        self.backbone, self.embed_dim = create_backbone(
            model_name=config["backbone"],
            pretrained=True,
            num_classes=0
        )
        self.backbone = self.backbone.to(self.device)
        
        # Heads de pré-entraînement
        # 1. Classification binaire: normal vs anomalie
        self.anomaly_head = nn.Sequential(
            nn.Linear(self.embed_dim, 256),
            nn.ReLU(),
            nn.Dropout(0.3),
            nn.Linear(256, 2)
        ).to(self.device)
        
        # 2. Classification multi-classe des types de défauts
        self.defect_head = nn.Sequential(
            nn.Linear(self.embed_dim, 512),
            nn.ReLU(),
            nn.Dropout(0.3),
            nn.Linear(512, len(MVTecDataset.DEFECT_TYPES))  # Nombre exact de types de défauts MVTec
        ).to(self.device)
        
        # Optimiseur
        self.optimizer = optim.AdamW([
            {'params': self.backbone.parameters(), 'lr': config["lr_backbone"]},
            {'params': self.anomaly_head.parameters(), 'lr': config["lr_head"]},
            {'params': self.defect_head.parameters(), 'lr': config["lr_head"]}
        ], weight_decay=config["weight_decay"])
        
        self.scheduler = optim.lr_scheduler.CosineAnnealingLR(
            self.optimizer, T_max=config["epochs"]
        )
        
        self.criterion_anomaly = nn.CrossEntropyLoss()
        self.criterion_defect = nn.BCEWithLogitsLoss()
    
    def train_epoch(self, dataloader: DataLoader) -> dict:
        self.backbone.train()
        self.anomaly_head.train()
        self.defect_head.train()
        
        total_loss = 0.0
        correct_anomaly = 0
        total = 0
        
        pbar = tqdm(dataloader, desc="Training")
        for batch in pbar:
            images = batch["image"].to(self.device)
            is_anomaly = batch["is_anomaly"].to(self.device)
            defect_labels = batch["defect_labels"].to(self.device)
            
            self.optimizer.zero_grad()
            
            # Forward
            embeddings = self.backbone(images)
            anomaly_logits = self.anomaly_head(embeddings)
            defect_logits = self.defect_head(embeddings)
            
            # Loss
            loss_anomaly = self.criterion_anomaly(anomaly_logits, is_anomaly)
            loss_defect = self.criterion_defect(defect_logits, defect_labels)
            loss = loss_anomaly + 0.5 * loss_defect
            
            loss.backward()
            torch.nn.utils.clip_grad_norm_(
                list(self.backbone.parameters()) + 
                list(self.anomaly_head.parameters()) +
                list(self.defect_head.parameters()),
                max_norm=1.0
            )
            self.optimizer.step()
            
            # Metrics
            total_loss += loss.item()
            pred_anomaly = anomaly_logits.argmax(dim=1)
            correct_anomaly += (pred_anomaly == is_anomaly).sum().item()
            total += is_anomaly.size(0)
            
            pbar.set_postfix({
                'loss': f"{loss.item():.4f}",
                'acc': f"{100*correct_anomaly/total:.2f}%"
            })
        
        return {
            "loss": total_loss / len(dataloader),
            "accuracy": correct_anomaly / total
        }
    
    @torch.no_grad()
    def validate(self, dataloader: DataLoader) -> dict:
        self.backbone.eval()
        self.anomaly_head.eval()
        self.defect_head.eval()
        
        total_loss = 0.0
        total_loss_anomaly = 0.0
        total_loss_defect = 0.0
        correct_anomaly = 0
        total = 0
        
        all_targets = []
        all_probs = []
        
        for batch in tqdm(dataloader, desc="Validation"):
            images = batch["image"].to(self.device)
            is_anomaly = batch["is_anomaly"].to(self.device)
            defect_labels = batch["defect_labels"].to(self.device)
            
            embeddings = self.backbone(images)
            anomaly_logits = self.anomaly_head(embeddings)
            defect_logits = self.defect_head(embeddings)
            
            loss_anomaly = self.criterion_anomaly(anomaly_logits, is_anomaly)
            loss_defect = self.criterion_defect(defect_logits, defect_labels)
            loss = loss_anomaly + 0.5 * loss_defect
            
            total_loss += loss.item()
            total_loss_anomaly += loss_anomaly.item()
            total_loss_defect += loss_defect.item()
            pred_anomaly = anomaly_logits.argmax(dim=1)
            correct_anomaly += (pred_anomaly == is_anomaly).sum().item()
            total += is_anomaly.size(0)
            
            # Anomaly probability corresponds to class 1
            probs = torch.softmax(anomaly_logits, dim=1)[:, 1]
            all_targets.extend(is_anomaly.cpu().numpy())
            all_probs.extend(probs.cpu().numpy())
            
        # Compute Area Under ROC Curve (AUC-ROC)
        from sklearn.metrics import roc_auc_score
        try:
            auc = roc_auc_score(all_targets, all_probs)
        except ValueError:
            auc = 0.5 # fallback if only one class is present in split
        
        return {
            "loss": total_loss / len(dataloader),
            "loss_anomaly": total_loss_anomaly / len(dataloader),
            "loss_defect": total_loss_defect / len(dataloader),
            "accuracy": correct_anomaly / total,
            "auc": auc
        }
    
    def save_backbone(self, path: str):
        """Sauvegarde uniquement les poids du backbone."""
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        torch.save({
            "backbone_state_dict": self.backbone.state_dict(),
            "embed_dim": self.embed_dim,
            "config": self.config
        }, path)
        print(f"[OK] Backbone sauvegardé: {path}")
    
    def run(self, train_loader: DataLoader, val_loader: DataLoader):
        """Boucle d'entraînement complète."""
        best_val_auc = 0.0
        
        for epoch in range(self.config["epochs"]):
            print(f"\n{'='*50}")
            print(f"Epoch {epoch+1}/{self.config['epochs']}")
            print(f"{'='*50}")
            
            # Train
            train_metrics = self.train_epoch(train_loader)
            print(f"Train — Loss: {train_metrics['loss']:.4f} | "
                  f"Acc: {train_metrics['accuracy']*100:.2f}%")
            
            # Val
            val_metrics = self.validate(val_loader)
            print(f"Val   — Loss: {val_metrics['loss']:.4f} (Anomaly: {val_metrics['loss_anomaly']:.4f}, Defect: {val_metrics['loss_defect']:.4f}) | "
                  f"Acc: {val_metrics['accuracy']*100:.2f}% | "
                  f"AUC: {val_metrics['auc']*100:.2f}%")
            
            # Scheduler
            self.scheduler.step()
            
            # Sauvegarde basée sur l'AUC-ROC (métrique robuste et standard pour MVTec AD)
            if val_metrics["auc"] > best_val_auc:
                best_val_auc = val_metrics["auc"]
                self.save_backbone(self.config["output_path"])
                print(f"💾 Nouveau meilleur modèle! (AUC: {best_val_auc*100:.2f}%)")
        
        print(f"\n[OK] Pré-entraînement terminé. Meilleur AUC: {best_val_auc*100:.2f}%")


def main():
    parser = argparse.ArgumentParser(description="Pré-entraînement backbone MVTec")
    parser.add_argument("--data_root", default="data/external/mvtec_ad")
    parser.add_argument("--backbone", default="vit_base_patch16_224")
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--batch_size", type=int, default=32)
    parser.add_argument("--lr_backbone", type=float, default=5e-6)
    parser.add_argument("--lr_head", type=float, default=2e-4)
    parser.add_argument("--output", default="models/cv/checkpoints/backbone_mvtec.pt")
    args = parser.parse_args()
    
    config = {
        "backbone": args.backbone,
        "epochs": args.epochs,
        "lr_backbone": args.lr_backbone,
        "lr_head": args.lr_head,
        "weight_decay": 1e-4,
        "output_path": args.output
    }
    
    # Transforms
    train_transform = transforms.Compose([
        transforms.Resize((256, 256)),
        transforms.RandomCrop(224),
        transforms.RandomHorizontalFlip(),
        transforms.RandomRotation(15),
        transforms.ColorJitter(0.2, 0.2, 0.1),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
    ])
    
    val_transform = transforms.Compose([
        transforms.Resize((224, 224)),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
    ])
    
    # Datasets
    print("[INFO] Chargement des datasets MVTec...")
    train_dataset = MVTecMultiCategoryDataset(
        root=args.data_root,
        split="train",
        transform=train_transform
    )
    val_dataset = MVTecMultiCategoryDataset(
        root=args.data_root,
        split="test",
        transform=val_transform
    )
    
    train_loader = DataLoader(
        train_dataset, batch_size=args.batch_size,
        shuffle=True, num_workers=4, pin_memory=True
    )
    val_loader = DataLoader(
        val_dataset, batch_size=args.batch_size,
        shuffle=False, num_workers=4, pin_memory=True
    )
    
    # Entraînement
    runner = PretrainRunner(config)
    runner.run(train_loader, val_loader)


if __name__ == "__main__":
    main()