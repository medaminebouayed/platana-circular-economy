"""
Entraînement final du modèle de grading multi-vues.
Fine-tuning sur le dataset propriétaire avec le backbone pré-entraîné.
"""

import argparse
import yaml
from pathlib import Path

import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader
from torch.utils.tensorboard import SummaryWriter
from torchvision import transforms
import mlflow

from grading_model import MultiViewGradingModel
from dataset import ProductGradingDataset, collate_fn


class GradingTrainer:
    """Entraîne le modèle de grading multi-vues complet."""
    
    def __init__(self, config: dict):
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.config = config
        
        # Modèle
        self.model = MultiViewGradingModel(
            max_views=config["model"]["max_views"],
            num_classes=config["model"]["num_classes"],
            backbone_name=config["model"]["backbone"],
            fusion_type=config["model"]["fusion_type"],
            pretrained=config["model"]["pretrained"],
            dropout=config["model"]["dropout"]
        ).to(self.device)
        
        # Charge le backbone pré-entraîné si spécifié
        if config["training"].get("pretrained_backbone"):
            self.model.load_pretrained_backbone(config["training"]["pretrained_backbone"])
            print(f"[OK] Backbone pré-entraîné chargé")
        
        # Gèle le backbone initialement
        if config["training"]["freeze_backbone_epochs"] > 0:
            self.model.freeze_backbone()
            print(f"[INFO] Backbone gelé pour {config['training']['freeze_backbone_epochs']} epochs")
        
        # Optimiseur
        self.optimizer = optim.AdamW(
            filter(lambda p: p.requires_grad, self.model.parameters()),
            lr=config["training"]["lr"],
            weight_decay=config["training"]["weight_decay"]
        )
        
        self.scheduler = optim.lr_scheduler.CosineAnnealingWarmRestarts(
            self.optimizer, T_0=10, T_mult=2
        )
        
        # Loss
        grade_weights = torch.tensor(config["training"].get("grade_weights", [1.0, 1.2, 1.5, 2.0]))
        self.grade_criterion = nn.CrossEntropyLoss(weight=grade_weights.to(self.device))
        self.defect_criterion = nn.BCEWithLogitsLoss()
        
        # Logging
        mlflow.set_experiment(config["paths"]["mlflow_experiment"])
        self.writer = SummaryWriter(log_dir=config["paths"]["logs"])
        
        self.best_val_acc = 0.0
        self.epoch = 0
    
    def train_epoch(self, dataloader: DataLoader) -> dict:
        self.model.train()
        total_loss = 0.0
        correct = 0
        total = 0
        
        for batch_idx, batch in enumerate(dataloader):
            views = batch["views"].to(self.device)
            num_views = batch["num_views"].to(self.device)
            grades = batch["grade"].to(self.device)
            defects = batch["defects"].to(self.device)
            
            self.optimizer.zero_grad()
            
            outputs = self.model(views, num_views)
            
            loss_grade = self.grade_criterion(outputs["grade_logits"], grades)
            loss_defects = self.defect_criterion(outputs["defect_logits"], defects)
            loss = loss_grade + 0.3 * loss_defects
            
            loss.backward()
            torch.nn.utils.clip_grad_norm_(self.model.parameters(), max_norm=1.0)
            self.optimizer.step()
            
            total_loss += loss.item()
            predicted = outputs["predicted_grade"]
            correct += (predicted == grades).sum().item()
            total += grades.size(0)
            
            if batch_idx % 10 == 0:
                print(f"  Batch {batch_idx}/{len(dataloader)} | "
                      f"Loss: {loss.item():.4f} | Acc: {100*correct/total:.2f}%")
        
        return {"loss": total_loss / len(dataloader), "accuracy": correct / total}
    
    @torch.no_grad()
    def validate(self, dataloader: DataLoader) -> dict:
        self.model.eval()
        total_loss = 0.0
        correct = 0
        total = 0
        confusion = torch.zeros(4, 4, dtype=torch.long)
        
        for batch in dataloader:
            views = batch["views"].to(self.device)
            num_views = batch["num_views"].to(self.device)
            grades = batch["grade"].to(self.device)
            defects = batch["defects"].to(self.device)
            
            outputs = self.model(views, num_views)
            
            loss_grade = self.grade_criterion(outputs["grade_logits"], grades)
            loss_defects = self.defect_criterion(outputs["defect_logits"], defects)
            loss = loss_grade + 0.3 * loss_defects
            
            total_loss += loss.item()
            predicted = outputs["predicted_grade"]
            correct += (predicted == grades).sum().item()
            total += grades.size(0)
            
            for p, g in zip(predicted, grades):
                confusion[p.item(), g.item()] += 1
        
        return {
            "loss": total_loss / len(dataloader),
            "accuracy": correct / total,
            "confusion_matrix": confusion
        }
    
    def train(self, train_loader: DataLoader, val_loader: DataLoader, epochs: int):
        with mlflow.start_run(run_name=self.config["run_name"]):
            mlflow.log_params(self.config)
            
            for epoch in range(epochs):
                self.epoch = epoch
                print(f"\n{'='*50}")
                print(f"Epoch {epoch+1}/{epochs}")
                print(f"{'='*50}")
                
                # Dé-gèle le backbone
                if epoch == self.config["training"]["freeze_backbone_epochs"]:
                    self.model.unfreeze_backbone()
                    self.optimizer = optim.AdamW(
                        self.model.parameters(),
                        lr=self.config["training"]["lr"] * 0.1,
                        weight_decay=self.config["training"]["weight_decay"]
                    )
                    print("🔓 Backbone dégelé!")
                
                # Train
                train_metrics = self.train_epoch(train_loader)
                print(f"📊 Train — Loss: {train_metrics['loss']:.4f} | "
                      f"Acc: {train_metrics['accuracy']*100:.2f}%")
                
                # Val
                val_metrics = self.validate(val_loader)
                print(f"📊 Val   — Loss: {val_metrics['loss']:.4f} | "
                      f"Acc: {val_metrics['accuracy']*100:.2f}%")
                print(f"📊 Confusion:\n{val_metrics['confusion_matrix']}")
                
                self.scheduler.step()
                
                # Log
                self.writer.add_scalars("Loss", {
                    "train": train_metrics["loss"],
                    "val": val_metrics["loss"]
                }, epoch)
                self.writer.add_scalars("Accuracy", {
                    "train": train_metrics["accuracy"],
                    "val": val_metrics["accuracy"]
                }, epoch)
                
                mlflow.log_metrics({
                    "train_loss": train_metrics["loss"],
                    "val_loss": val_metrics["loss"],
                    "val_acc": val_metrics["accuracy"]
                }, step=epoch)
                
                # Sauvegarde
                if val_metrics["accuracy"] > self.best_val_acc:
                    self.best_val_acc = val_metrics["accuracy"]
                    save_path = Path(self.config["paths"]["checkpoints"]) / "best_model.pt"
                    save_path.parent.mkdir(parents=True, exist_ok=True)
                    torch.save({
                        "epoch": epoch,
                        "model_state_dict": self.model.state_dict(),
                        "optimizer_state_dict": self.optimizer.state_dict(),
                        "val_acc": val_metrics["accuracy"],
                        "config": self.config
                    }, save_path)
                    print(f"💾 Meilleur modèle! (acc: {val_metrics['accuracy']*100:.2f}%)")
                    mlflow.log_artifact(str(save_path))
        
        self.writer.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/cv_config.yaml")
    parser.add_argument("--run_name", default="grading_v1")
    args = parser.parse_args()
    
    # Charge la config
    with open(args.config, 'r') as f:
        config = yaml.safe_load(f)
    config["run_name"] = args.run_name
    
    # Transforms
    train_transform = transforms.Compose([
        transforms.Resize((256, 256)),
        transforms.RandomCrop(224),
        transforms.RandomHorizontalFlip(p=0.5),
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
    train_dataset = ProductGradingDataset(
        data_root=config["data"]["train_data"],
        annotations_file=config["data"]["annotations_train"],
        transform=train_transform,
        max_views=config["model"]["max_views"]
    )
    val_dataset = ProductGradingDataset(
        data_root=config["data"]["val_data"],
        annotations_file=config["data"]["annotations_val"],
        transform=val_transform,
        max_views=config["model"]["max_views"]
    )
    
    train_loader = DataLoader(
        train_dataset,
        batch_size=config["training"]["batch_size"],
        shuffle=True,
        collate_fn=collate_fn,
        num_workers=config["data"]["num_workers"],
        pin_memory=config["data"]["pin_memory"]
    )
    val_loader = DataLoader(
        val_dataset,
        batch_size=config["training"]["batch_size"],
        shuffle=False,
        collate_fn=collate_fn,
        num_workers=config["data"]["num_workers"],
        pin_memory=config["data"]["pin_memory"]
    )
    
    # Entraînement
    trainer = GradingTrainer(config)
    trainer.train(train_loader, val_loader, config["training"]["epochs"])


if __name__ == "__main__":
    main()