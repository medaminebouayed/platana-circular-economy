"""
Pré-entraînement du backbone sur MVTec AD (mono-vue), multi-catégories.
Évaluation par catégorie (MVTec Benchmark Standard) + métriques globales.
"""

import argparse
from collections import defaultdict
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from torch.optim import AdamW
from torch.optim.lr_scheduler import ReduceLROnPlateau
from torch.utils.data import DataLoader, WeightedRandomSampler, Subset
from torchvision import transforms
from sklearn.model_selection import train_test_split
from sklearn.metrics import (accuracy_score, precision_score, recall_score, 
                             f1_score, roc_auc_score, confusion_matrix)
from tqdm import tqdm

from backbone import create_backbone
from mvtec_dataset import MVTecMultiCategoryDataset, MVTecDataset


class CategoryFiLM(nn.Module):
    """
    Conditionnement FiLM (Feature-wise Linear Modulation) par catégorie.
    Apprend, par catégorie, une modulation (gamma, beta) de l'embedding partagé.
    """

    def __init__(self, num_categories: int, embed_dim: int, cat_embed_dim: int = 32):
        super().__init__()
        self.category_embedding = nn.Embedding(num_categories, cat_embed_dim)
        self.film = nn.Sequential(
            nn.Linear(cat_embed_dim, cat_embed_dim * 2),
            nn.GELU(),
            nn.Linear(cat_embed_dim * 2, embed_dim * 2)
        )
        nn.init.zeros_(self.film[-1].weight)
        nn.init.zeros_(self.film[-1].bias)

    def forward(self, features: torch.Tensor, category_idx: torch.Tensor) -> torch.Tensor:
        cat_emb = self.category_embedding(category_idx)          # (B, cat_embed_dim)
        gamma_beta = self.film(cat_emb)                           # (B, 2*embed_dim)
        gamma, beta = gamma_beta.chunk(2, dim=-1)                 # (B, embed_dim) chacun
        gamma = 1.0 + gamma
        return gamma * features + beta


class PretrainRunner:
    """Entraîne le backbone sur MVTec AD avec évaluation par catégorie et globale."""

    def __init__(self, config: dict, num_categories: int):
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.config = config

        self.backbone, self.embed_dim = create_backbone(
            model_name=config["backbone"],
            pretrained=True,
            num_classes=0
        )
        self.backbone = self.backbone.to(self.device)

        self.category_film = CategoryFiLM(
            num_categories=num_categories,
            embed_dim=self.embed_dim
        ).to(self.device)

        self.anomaly_head = nn.Sequential(
            nn.Linear(self.embed_dim, 256),
            nn.ReLU(),
            nn.Dropout(0.3),
            nn.Linear(256, 2)
        ).to(self.device)

        self.optimizer = AdamW([
            {'params': self.backbone.parameters(), 'lr': config["lr_backbone"]},
            {'params': self.category_film.parameters(), 'lr': config["lr_head"]},
            {'params': self.anomaly_head.parameters(), 'lr': config["lr_head"]}
        ], weight_decay=config["weight_decay"])

        self.scheduler = ReduceLROnPlateau(
            self.optimizer, mode='max', factor=0.5, patience=3
        )

        self.criterion = nn.CrossEntropyLoss()

    def _forward(self, images: torch.Tensor, category_idx: torch.Tensor) -> torch.Tensor:
        embeddings = self.backbone(images)
        embeddings = self.category_film(embeddings, category_idx)
        anomaly_logits = self.anomaly_head(embeddings)
        return anomaly_logits

    def train_epoch(self, dataloader: DataLoader) -> float:
        self.backbone.train()
        self.category_film.train()
        self.anomaly_head.train()

        running_loss = 0.0

        for batch in tqdm(dataloader, desc="[Training]"):
            images = batch["image"].to(self.device)
            is_anomaly = batch["is_anomaly"].to(self.device)
            category_idx = batch["category_idx"].to(self.device)

            self.optimizer.zero_grad()
            outputs = self._forward(images, category_idx)
            loss = self.criterion(outputs, is_anomaly)
            loss.backward()

            all_params = (
                list(self.backbone.parameters()) +
                list(self.category_film.parameters()) +
                list(self.anomaly_head.parameters())
            )
            torch.nn.utils.clip_grad_norm_(all_params, max_norm=1.0)
            self.optimizer.step()

            running_loss += loss.item()

        return running_loss / len(dataloader)

    @torch.no_grad()
    def validate(self, dataloader: DataLoader, desc: str = "Validating") -> dict:
        self.backbone.eval()
        self.category_film.eval()
        self.anomaly_head.eval()

        running_loss = 0.0
        all_preds = []
        all_labels = []
        all_probs = []

        targets_by_cat = defaultdict(list)
        preds_by_cat = defaultdict(list)
        probs_by_cat = defaultdict(list)

        for batch in tqdm(dataloader, desc=desc):
            images = batch["image"].to(self.device)
            is_anomaly = batch["is_anomaly"].to(self.device)
            category_idx = batch["category_idx"].to(self.device)
            categories = batch["category"]

            outputs = self._forward(images, category_idx)
            loss = self.criterion(outputs, is_anomaly)
            running_loss += loss.item()

            probs = torch.softmax(outputs, dim=1)
            predicted = torch.argmax(probs, dim=1)

            targets = is_anomaly.cpu().numpy()
            preds = predicted.cpu().numpy()
            probabilities = probs.cpu().numpy()

            all_preds.extend(preds)
            all_labels.extend(targets)
            all_probs.extend(probabilities)

            for cat, t, p, pr in zip(categories, targets, preds, probabilities[:, 1]):
                targets_by_cat[cat].append(t)
                preds_by_cat[cat].append(p)
                probs_by_cat[cat].append(pr)

        all_preds = np.array(all_preds)
        all_labels = np.array(all_labels)
        all_probs = np.array(all_probs)

        # 1. Métriques Globales (Poolées)
        acc_global = accuracy_score(all_labels, all_preds)
        precision_global = precision_score(all_labels, all_preds, average='macro', zero_division=0)
        recall_global = recall_score(all_labels, all_preds, average='macro', zero_division=0)
        f1_global = f1_score(all_labels, all_preds, average='macro', zero_division=0)
        try:
            roc_auc_global = roc_auc_score(all_labels, all_probs[:, 1])
        except ValueError:
            roc_auc_global = 0.5
        cm_global = confusion_matrix(all_labels, all_preds)

        # 2. Métriques par Catégorie (MVTec Standard)
        f1_by_cat = {}
        auc_by_cat = {}
        for cat in targets_by_cat:
            cat_targets = np.array(targets_by_cat[cat])
            cat_preds = np.array(preds_by_cat[cat])
            cat_probs = np.array(probs_by_cat[cat])

            f1_by_cat[cat] = f1_score(cat_targets, cat_preds, average='macro', zero_division=0)
            try:
                auc_by_cat[cat] = roc_auc_score(cat_targets, cat_probs)
            except ValueError:
                auc_by_cat[cat] = 0.5

        macro_f1_cat = float(np.mean(list(f1_by_cat.values())))
        macro_auc_cat = float(np.mean(list(auc_by_cat.values())))

        return {
            "loss": running_loss / len(dataloader),
            "accuracy_global": acc_global,
            "precision_global": precision_global,
            "recall_global": recall_global,
            "f1_global": f1_global,
            "roc_auc_global": roc_auc_global,
            "confusion_matrix_global": cm_global,
            "macro_f1_cat": macro_f1_cat,
            "macro_auc_cat": macro_auc_cat,
            "f1_by_cat": f1_by_cat,
            "auc_by_cat": auc_by_cat
        }

    def save_checkpoint(self, path: str):
        """Sauvegarde le backbone + FiLM + anomaly head."""
        save_path = Path(path)
        save_path.parent.mkdir(parents=True, exist_ok=True)
        torch.save({
            "backbone_state_dict": self.backbone.state_dict(),
            "category_film_state_dict": self.category_film.state_dict(),
            "anomaly_head_state_dict": self.anomaly_head.state_dict(),
            "embed_dim": self.embed_dim,
            "config": self.config
        }, save_path)

    def run(self, train_loader: DataLoader, val_loader: DataLoader, test_loader: DataLoader):
        best_val_f1 = 0.0  # Sélection basée sur F1 Macro Par Catégorie
        epochs_without_improvement = 0
        early_stopping_rounds = self.config.get("patience", 25)

        for epoch in range(self.config["epochs"]):
            print(f"\n--- Epoch {epoch+1}/{self.config['epochs']} ---")

            train_loss = self.train_epoch(train_loader)
            print(f"Train Loss: {train_loss:.4f}")

            val_metrics = self.validate(val_loader, desc="Validating")
            f1_macro_cat = val_metrics["macro_f1_cat"]
            auc_macro_cat = val_metrics["macro_auc_cat"]
            f1_global = val_metrics["f1_global"]
            acc_global = val_metrics["accuracy_global"]
            cm = val_metrics["confusion_matrix_global"]

            print(f"Val F1-Score (Macro Per-Category): {f1_macro_cat:.4f}  <-- Benchmark metric")
            print(f"Val ROC-AUC  (Macro Per-Category): {auc_macro_cat:.4f}")
            print(f"Val Global Pooled Metrics -> F1: {f1_global:.4f} | Acc: {acc_global*100:.2f}%")
            print("Global Confusion Matrix (Rows=True, Cols=Pred):")
            print("       Normal  Anomaly")
            print(cm)
            print("-" * 40)

            # Step le scheduler ReduceLROnPlateau sur le F1-Score Macro par Catégorie
            self.scheduler.step(f1_macro_cat)

            # Sélection du meilleur modèle basée sur le F1-Score Macro Par Catégorie
            if f1_macro_cat > best_val_f1:
                best_val_f1 = f1_macro_cat
                epochs_without_improvement = 0
                self.save_checkpoint(self.config["output_path"])
                print(f"🚀 New best model saved! (Category Macro F1: {best_val_f1:.4f})\n")
            else:
                epochs_without_improvement += 1
                if epochs_without_improvement >= early_stopping_rounds:
                    print(f"Early stopping triggered after {epoch+1} epochs.")
                    break

        print(f"\n[OK] Pré-entraînement terminé. Meilleur Category Macro F1 (val): {best_val_f1:.4f}")

        # Évaluation finale sur le test set réservé
        print("\n" + "="*50)
        print("ÉVALUATION FINALE SUR LE TEST SET (jamais vu)")
        print("="*50)
        test_metrics = self.validate(test_loader, desc="Testing")
        print(f"Test F1-Score (Macro Per-Category): {test_metrics['macro_f1_cat']:.4f}")
        print(f"Test ROC-AUC  (Macro Per-Category): {test_metrics['macro_auc_cat']:.4f}")
        print(f"Test Global Pooled Metrics -> F1: {test_metrics['f1_global']:.4f} | Acc: {test_metrics['accuracy_global']*100:.2f}%")
        print("\nDétail F1 & ROC-AUC par catégorie:")
        for cat in test_metrics["f1_by_cat"]:
            f1_c = test_metrics["f1_by_cat"][cat]
            auc_c = test_metrics["auc_by_cat"][cat]
            print(f"  - {cat:<12}: F1 = {f1_c:.4f} | ROC-AUC = {auc_c:.4f}")
        print("\nGlobal Confusion Matrix:")
        print(test_metrics["confusion_matrix_global"])
        print("="*50)

        return test_metrics


def stratified_val_test_split(dataset: MVTecMultiCategoryDataset, test_size: float = 0.5, seed: int = 42):
    """
    Sépare le test set officiel MVTec en deux : val (sélection checkpoint) et test (évaluation finale).
    Stratifié par (catégorie, label).
    """
    indices = list(range(len(dataset)))
    combined_strata = [f"{c}_{l}" for c, l in zip(dataset.categories, dataset.labels)]

    try:
        val_idx, test_idx = train_test_split(
            indices, test_size=test_size, stratify=combined_strata, random_state=seed
        )
    except ValueError:
        val_idx, test_idx = train_test_split(
            indices, test_size=test_size, stratify=dataset.labels, random_state=seed
        )

    return Subset(dataset, val_idx), Subset(dataset, test_idx)


def collate_with_category(batch):
    out = {}
    for key in batch[0]:
        if key in ("category", "defect_type", "path"):
            out[key] = [b[key] for b in batch]
        else:
            out[key] = torch.stack([b[key] for b in batch])
    return out


def main():
    parser = argparse.ArgumentParser(description="Pré-entraînement backbone MVTec multi-catégories")
    parser.add_argument("--data_root", default="data/external/mvtec_ad")
    parser.add_argument("--categories", nargs="+", default=None,
                         help="Liste de catégories à utiliser (défaut: toutes les catégories disponibles)")
    parser.add_argument("--backbone", default="vit_base_patch16_224")
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--batch_size", type=int, default=32)
    parser.add_argument("--lr_backbone", type=float, default=1e-5)
    parser.add_argument("--lr_head", type=float, default=2e-4)
    parser.add_argument("--patience", type=int, default=25)
    parser.add_argument("--output", default="models/cv/checkpoints/backbone_mvtec.pt")
    args = parser.parse_args()

    config = {
        "backbone": args.backbone,
        "epochs": args.epochs,
        "lr_backbone": args.lr_backbone,
        "lr_head": args.lr_head,
        "weight_decay": 1e-4,
        "patience": args.patience,
        "output_path": args.output
    }

    train_transform = transforms.Compose([
        transforms.Resize((256, 256)),
        transforms.RandomCrop(224),
        transforms.RandomHorizontalFlip(),
        transforms.RandomRotation(15),
        transforms.ColorJitter(brightness=0.2, contrast=0.2, saturation=0.1),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
    ])

    val_transform = transforms.Compose([
        transforms.Resize((224, 224)),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
    ])

    print("[INFO] Chargement des datasets MVTec...")
    train_dataset = MVTecMultiCategoryDataset(
        root=args.data_root,
        categories=args.categories,
        split="train",
        transform=train_transform
    )
    full_test_dataset = MVTecMultiCategoryDataset(
        root=args.data_root,
        categories=args.categories,
        split="test",
        transform=val_transform
    )

    val_dataset, test_dataset = stratified_val_test_split(full_test_dataset, test_size=0.5)
    print(f"[INFO] Split test set officiel -> val: {len(val_dataset)} | test (réservé): {len(test_dataset)}")

    sample_weights = train_dataset.category_sample_weights()
    sampler = WeightedRandomSampler(
        weights=sample_weights,
        num_samples=len(sample_weights),
        replacement=True
    )

    train_loader = DataLoader(
        train_dataset, batch_size=args.batch_size,
        sampler=sampler,
        num_workers=4, pin_memory=True,
        collate_fn=collate_with_category
    )
    val_loader = DataLoader(
        val_dataset, batch_size=args.batch_size,
        shuffle=False, num_workers=4, pin_memory=True,
        collate_fn=collate_with_category
    )
    test_loader = DataLoader(
        test_dataset, batch_size=args.batch_size,
        shuffle=False, num_workers=4, pin_memory=True,
        collate_fn=collate_with_category
    )

    num_categories = len(MVTecDataset.CATEGORIES)
    runner = PretrainRunner(config, num_categories=num_categories)
    runner.run(train_loader, val_loader, test_loader)


if __name__ == "__main__":
    main()