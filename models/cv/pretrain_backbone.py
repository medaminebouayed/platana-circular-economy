"""
Pré-entraînement du backbone sur MVTec AD (mono-vue), multi-catégories.
Le backbone apprend à reconnaître les défauts visuels, avec un conditionnement
par catégorie (FiLM) pour gérer la diversité visuelle entre catégories.
"""

import argparse
from collections import defaultdict
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader, WeightedRandomSampler, Subset
from torchvision import transforms
from sklearn.model_selection import train_test_split
from sklearn.metrics import roc_auc_score
from tqdm import tqdm

from backbone import create_backbone
from mvtec_dataset import MVTecMultiCategoryDataset, MVTecDataset


class CategoryFiLM(nn.Module):
    """
    Conditionnement FiLM (Feature-wise Linear Modulation) par catégorie.

    Pourquoi: le backbone produit un embedding générique, mais "anomalie" ne
    veut pas dire la même chose pour une bouteille (rayure sur verre) que pour
    un câble (fil tordu) ou un tapis (texture irrégulière). Ce module apprend,
    par catégorie, une modulation (gamma, beta) de l'embedding partagé, pour que
    les têtes de classification interprètent le même vecteur différemment selon
    le contexte catégorie.
    """

    def __init__(self, num_categories: int, embed_dim: int, cat_embed_dim: int = 32):
        super().__init__()
        self.category_embedding = nn.Embedding(num_categories, cat_embed_dim)
        self.film = nn.Sequential(
            nn.Linear(cat_embed_dim, cat_embed_dim * 2),
            nn.GELU(),
            nn.Linear(cat_embed_dim * 2, embed_dim * 2)
        )
        # Initialisation proche de l'identité pour ne pas perturber le backbone
        # pré-entraîné ImageNet dès le début de l'entraînement.
        nn.init.zeros_(self.film[-1].weight)
        nn.init.zeros_(self.film[-1].bias)

    def forward(self, features: torch.Tensor, category_idx: torch.Tensor) -> torch.Tensor:
        cat_emb = self.category_embedding(category_idx)          # (B, cat_embed_dim)
        gamma_beta = self.film(cat_emb)                           # (B, 2*embed_dim)
        gamma, beta = gamma_beta.chunk(2, dim=-1)                 # (B, embed_dim) chacun
        gamma = 1.0 + gamma  # centré sur 1 grâce à l'init à zéro ci-dessus
        return gamma * features + beta


class PretrainRunner:
    """Entraîne le backbone sur MVTec AD, conditionné par catégorie."""

    def __init__(self, config: dict, num_categories: int):
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.config = config

        # Backbone partagé entre toutes les catégories
        self.backbone, self.embed_dim = create_backbone(
            model_name=config["backbone"],
            pretrained=True,
            num_classes=0
        )
        self.backbone = self.backbone.to(self.device)

        # Conditionnement par catégorie — LE fix du problème multi-catégories
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

        self.defect_head = nn.Sequential(
            nn.Linear(self.embed_dim, 512),
            nn.ReLU(),
            nn.Dropout(0.3),
            nn.Linear(512, len(MVTecDataset.DEFECT_TYPES))
        ).to(self.device)

        self.optimizer = optim.AdamW([
            {'params': self.backbone.parameters(), 'lr': config["lr_backbone"]},
            {'params': self.category_film.parameters(), 'lr': config["lr_head"]},
            {'params': self.anomaly_head.parameters(), 'lr': config["lr_head"]},
            {'params': self.defect_head.parameters(), 'lr': config["lr_head"]}
        ], weight_decay=config["weight_decay"])

        self.scheduler = optim.lr_scheduler.CosineAnnealingLR(
            self.optimizer, T_max=config["epochs"]
        )

        self.criterion_anomaly = nn.CrossEntropyLoss()
        # reduction='none' pour pouvoir masquer les samples au label defect non-fiable
        self.criterion_defect = nn.BCEWithLogitsLoss(reduction='none')

    def _forward(self, images: torch.Tensor, category_idx: torch.Tensor) -> dict:
        embeddings = self.backbone(images)
        embeddings = self.category_film(embeddings, category_idx)
        anomaly_logits = self.anomaly_head(embeddings)
        defect_logits = self.defect_head(embeddings)
        return {"anomaly_logits": anomaly_logits, "defect_logits": defect_logits}

    def _compute_loss(self, outputs: dict, is_anomaly: torch.Tensor,
                       defect_labels: torch.Tensor, defect_valid: torch.Tensor) -> tuple:
        loss_anomaly = self.criterion_anomaly(outputs["anomaly_logits"], is_anomaly)

        loss_defect_raw = self.criterion_defect(outputs["defect_logits"], defect_labels)  # (B, num_defects)
        loss_defect_per_sample = loss_defect_raw.mean(dim=1)  # (B,)
        # Masque: on ignore les samples au label defect non-fiable (bug label corrigé ici)
        denom = defect_valid.sum().clamp(min=1)
        loss_defect = (loss_defect_per_sample * defect_valid).sum() / denom

        loss = loss_anomaly + 0.05 * loss_defect
        return loss, loss_anomaly, loss_defect

    def train_epoch(self, dataloader: DataLoader) -> dict:
        self.backbone.train()
        self.category_film.train()
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
            defect_valid = batch["defect_valid"].to(self.device)
            category_idx = batch["category_idx"].to(self.device)

            self.optimizer.zero_grad()

            outputs = self._forward(images, category_idx)
            loss, loss_anomaly, loss_defect = self._compute_loss(
                outputs, is_anomaly, defect_labels, defect_valid
            )

            loss.backward()
            all_params = (
                list(self.backbone.parameters()) +
                list(self.category_film.parameters()) +
                list(self.anomaly_head.parameters()) +
                list(self.defect_head.parameters())
            )
            torch.nn.utils.clip_grad_norm_(all_params, max_norm=1.0)
            self.optimizer.step()

            total_loss += loss.item()
            pred_anomaly = outputs["anomaly_logits"].argmax(dim=1)
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
        self.category_film.eval()
        self.anomaly_head.eval()
        self.defect_head.eval()

        total_loss = 0.0
        total_loss_anomaly = 0.0
        total_loss_defect = 0.0
        correct_anomaly = 0
        total = 0

        # Regroupement par catégorie pour l'AUC macro
        targets_by_cat = defaultdict(list)
        probs_by_cat = defaultdict(list)
        all_targets, all_probs = [], []

        for batch in tqdm(dataloader, desc="Validation"):
            images = batch["image"].to(self.device)
            is_anomaly = batch["is_anomaly"].to(self.device)
            defect_labels = batch["defect_labels"].to(self.device)
            defect_valid = batch["defect_valid"].to(self.device)
            category_idx = batch["category_idx"].to(self.device)
            categories = batch["category"]  # liste de strings

            outputs = self._forward(images, category_idx)
            loss, loss_anomaly, loss_defect = self._compute_loss(
                outputs, is_anomaly, defect_labels, defect_valid
            )

            total_loss += loss.item()
            total_loss_anomaly += loss_anomaly.item()
            total_loss_defect += loss_defect.item()

            pred_anomaly = outputs["anomaly_logits"].argmax(dim=1)
            correct_anomaly += (pred_anomaly == is_anomaly).sum().item()
            total += is_anomaly.size(0)

            probs = torch.softmax(outputs["anomaly_logits"], dim=1)[:, 1].cpu().numpy()
            targets = is_anomaly.cpu().numpy()

            all_targets.extend(targets)
            all_probs.extend(probs)
            for cat, t, p in zip(categories, targets, probs):
                targets_by_cat[cat].append(t)
                probs_by_cat[cat].append(p)

        # AUC globale (poolée) — gardée à titre indicatif seulement
        try:
            global_auc = roc_auc_score(all_targets, all_probs)
        except ValueError:
            global_auc = 0.5

        # AUC macro par catégorie — LA métrique de référence pour la sélection du modèle
        # Évite qu'une catégorie avec beaucoup d'images / anomalies faciles domine le score.
        per_category_auc = {}
        for cat in targets_by_cat:
            try:
                per_category_auc[cat] = roc_auc_score(targets_by_cat[cat], probs_by_cat[cat])
            except ValueError:
                # une seule classe présente pour cette catégorie dans ce split -> ignorée du macro
                per_category_auc[cat] = None

        valid_aucs = [v for v in per_category_auc.values() if v is not None]
        macro_auc = float(np.mean(valid_aucs)) if valid_aucs else 0.5

        return {
            "loss": total_loss / len(dataloader),
            "loss_anomaly": total_loss_anomaly / len(dataloader),
            "loss_defect": total_loss_defect / len(dataloader),
            "accuracy": correct_anomaly / total,
            "global_auc": global_auc,
            "macro_auc": macro_auc,
            "per_category_auc": per_category_auc
        }

    def save_backbone(self, path: str):
        """Sauvegarde le backbone + le module de conditionnement catégorie."""
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        torch.save({
            "backbone_state_dict": self.backbone.state_dict(),
            "category_film_state_dict": self.category_film.state_dict(),
            "embed_dim": self.embed_dim,
            "config": self.config
        }, path)
        print(f"[OK] Backbone sauvegardé: {path}")

    def run(self, train_loader: DataLoader, val_loader: DataLoader, test_loader: DataLoader):
        best_val_macro_auc = 0.0
        epochs_no_improve = 0
        patience = self.config.get("patience", 5)

        for epoch in range(self.config["epochs"]):
            print(f"\n{'='*50}")
            print(f"Epoch {epoch+1}/{self.config['epochs']}")
            print(f"{'='*50}")

            train_metrics = self.train_epoch(train_loader)
            print(f"Train — Loss: {train_metrics['loss']:.4f} | "
                  f"Acc: {train_metrics['accuracy']*100:.2f}%")

            val_metrics = self.validate(val_loader)
            print(f"Val   — Loss: {val_metrics['loss']:.4f} "
                  f"(Anomaly: {val_metrics['loss_anomaly']:.4f}, Defect: {val_metrics['loss_defect']:.4f}) | "
                  f"Acc: {val_metrics['accuracy']*100:.2f}% | "
                  f"AUC globale: {val_metrics['global_auc']*100:.2f}% | "
                  f"AUC macro (référence): {val_metrics['macro_auc']*100:.2f}%")
            print("  Détail AUC par catégorie:")
            for cat, auc in val_metrics["per_category_auc"].items():
                auc_str = f"{auc*100:.2f}%" if auc is not None else "N/A (1 seule classe)"
                print(f"    - {cat}: {auc_str}")

            self.scheduler.step()

            # Sélection du meilleur modèle sur l'AUC MACRO (pas globale)
            if val_metrics["macro_auc"] > best_val_macro_auc:
                best_val_macro_auc = val_metrics["macro_auc"]
                self.save_backbone(self.config["output_path"])
                print(f"💾 Nouveau meilleur modèle! (AUC macro: {best_val_macro_auc*100:.2f}%)")
                epochs_no_improve = 0
            else:
                epochs_no_improve += 1
                print(f"[INFO] Pas d'amélioration depuis {epochs_no_improve} epoch(s) (patience={patience})")
                if epochs_no_improve >= patience:
                    print(f"[INFO] Early stopping déclenché à l'epoch {epoch+1}")
                    break

        print(f"\n[OK] Pré-entraînement terminé. Meilleur AUC macro (val): {best_val_macro_auc*100:.2f}%")

        # Évaluation finale unique sur le vrai test set, jamais vu pendant l'entraînement
        print("\n" + "="*50)
        print("ÉVALUATION FINALE SUR LE TEST SET (jamais vu)")
        print("="*50)
        test_metrics = self.validate(test_loader)
        print(f"Test — AUC globale: {test_metrics['global_auc']*100:.2f}% | "
              f"AUC macro: {test_metrics['macro_auc']*100:.2f}%")
        for cat, auc in test_metrics["per_category_auc"].items():
            auc_str = f"{auc*100:.2f}%" if auc is not None else "N/A"
            print(f"    - {cat}: {auc_str}")

        return test_metrics


def stratified_val_test_split(dataset: MVTecMultiCategoryDataset, test_size: float = 0.5, seed: int = 42):
    """
    Sépare le test set officiel MVTec en deux : un 'val' utilisé pour le early
    stopping / sélection de checkpoint, et un 'test' gardé intouché jusqu'à
    l'évaluation finale. Stratifié par (catégorie, label) pour garder chaque
    catégorie représentée équitablement des deux côtés.
    """
    indices = list(range(len(dataset)))
    combined_strata = [f"{c}_{l}" for c, l in zip(dataset.categories, dataset.labels)]

    try:
        val_idx, test_idx = train_test_split(
            indices, test_size=test_size, stratify=combined_strata, random_state=seed
        )
    except ValueError:
        # fallback si une combinaison (catégorie, label) a trop peu de samples
        print("[WARN] Stratification fine impossible (trop peu de samples pour une combinaison "
              "catégorie/label), fallback sur stratification par label seul.")
        val_idx, test_idx = train_test_split(
            indices, test_size=test_size, stratify=dataset.labels, random_state=seed
        )

    return Subset(dataset, val_idx), Subset(dataset, test_idx)


def collate_with_category(batch):
    """Collate function standard, garde le champ 'category' (string) en liste."""
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
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--batch_size", type=int, default=32)
    parser.add_argument("--lr_backbone", type=float, default=5e-6)
    parser.add_argument("--lr_head", type=float, default=2e-4)
    parser.add_argument("--patience", type=int, default=5)
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
        transforms.ColorJitter(0.2, 0.2, 0.1),
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

    # Split val/test stratifié — fix méthodologique: le test set n'est plus
    # utilisé pour la sélection de checkpoint ET l'évaluation finale.
    val_dataset, test_dataset = stratified_val_test_split(full_test_dataset, test_size=0.5)
    print(f"[INFO] Split test set officiel -> val: {len(val_dataset)} | test (réservé): {len(test_dataset)}")

    # Sampler équilibré par catégorie pour l'entraînement
    sample_weights = train_dataset.category_sample_weights()
    sampler = WeightedRandomSampler(
        weights=sample_weights,
        num_samples=len(sample_weights),
        replacement=True
    )

    train_loader = DataLoader(
        train_dataset, batch_size=args.batch_size,
        sampler=sampler,  # remplace shuffle=True
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

    num_categories = len(MVTecDataset.CATEGORIES)  # fixe, pour cohérence des indices
    runner = PretrainRunner(config, num_categories=num_categories)
    runner.run(train_loader, val_loader, test_loader)


if __name__ == "__main__":
    main()