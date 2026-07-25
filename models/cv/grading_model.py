"""
Modèle de grading multi-vues complet.
Assemble: Backbone + Fusion + Classifier + DefectDetector
Gère un nombre VARIABLE de vues (1 à max_views).
"""

import torch
import torch.nn as nn
import torch.nn.functional as F

from .backbone import create_backbone
from .fusion import MeanFusion, AttentionFusion, TransformerFusion
from .classifier import GradeClassifier, DefectDetector


class MultiViewGradingModel(nn.Module):
    """
    Modèle de grading avec N vues variables.
    
    Args:
        max_views: Nombre maximum de vues supporté
        num_classes: Nombre de grades (4: A/B/C/D)
        backbone_name: Architecture du backbone
        fusion_type: 'mean', 'attention', 'transformer'
        pretrained: Charger les poids ImageNet
        dropout: Taux de dropout
    """
    
    GRADE_LABELS = {0: "A", 1: "B", 2: "C", 3: "D"}
    IDX_TO_GRADE = {v: k for k, v in GRADE_LABELS.items()}
    
    def __init__(
        self,
        max_views: int = 5,
        num_classes: int = 4,
        backbone_name: str = "vit_base_patch16_224",
        fusion_type: str = "attention",
        pretrained: bool = True,
        dropout: float = 0.3
    ):
        super().__init__()
        
        self.max_views = max_views
        
        # === BACKBONE ===
        self.backbone, self.embed_dim = create_backbone(
            model_name=backbone_name,
            pretrained=pretrained,
            num_classes=0,
            global_pool="token"
        )
        
        # Projection optionnelle
        self.projection = nn.Sequential(
            nn.LayerNorm(self.embed_dim),
            nn.Linear(self.embed_dim, self.embed_dim),
            nn.GELU(),
            nn.Dropout(dropout)
        )
        
        # === FUSION ===
        if fusion_type == "mean":
            self.fusion = MeanFusion()
        elif fusion_type == "attention":
            self.fusion = AttentionFusion(self.embed_dim)
        elif fusion_type == "transformer":
            self.fusion = TransformerFusion(self.embed_dim, dropout=dropout)
        else:
            raise ValueError(f"fusion_type '{fusion_type}' non supporté")
        
        # === HEADS ===
        self.grade_classifier = GradeClassifier(self.embed_dim, num_classes, dropout)
        self.defect_detector = DefectDetector(self.embed_dim, 6, dropout)
    
    def forward(self, views: torch.Tensor, num_views: torch.Tensor = None) -> dict:
        """
        Forward pass avec nombre variable de vues.
        
        Args:
            views: (B, N_max, C, H, W) — padding avec zéros pour les vues manquantes
            num_views: (B,) — nombre réel de vues (1 à N_max). Si None, utilise toutes.
        
        Returns:
            dict avec les prédictions et métadonnées
        """
        B, N_max, C, H, W = views.shape
        
        # 1. Extraction des embeddings
        views_flat = views.view(B * N_max, C, H, W)
        embeddings_flat = self.backbone(views_flat)
        embeddings_flat = self.projection(embeddings_flat)
        embeddings = embeddings_flat.view(B, N_max, self.embed_dim)
        
        # 2. Masquage des vues manquantes
        if num_views is not None:
            mask = torch.arange(N_max, device=views.device).unsqueeze(0) < num_views.unsqueeze(1)
            embeddings = embeddings * mask.unsqueeze(-1).float()
        else:
            mask = torch.ones(B, N_max, dtype=torch.bool, device=views.device)
        
        # 3. Fusion
        fused, attention_weights = self.fusion(embeddings, mask)
        
        # 4. Prédictions
        grade_logits = self.grade_classifier(fused)
        defect_logits = self.defect_detector(fused)
        
        # 5. Probabilités
        grade_probs = F.softmax(grade_logits, dim=1)
        confidence, predicted_grade = grade_probs.max(dim=1)
        
        return {
            "grade_logits": grade_logits,
            "grade_probs": grade_probs,
            "predicted_grade": predicted_grade,
            "confidence": confidence,
            "defect_logits": defect_logits,
            "attention_weights": attention_weights,
            "num_views_used": mask.sum(dim=1)
        }
    
    def freeze_backbone(self):
        """Gèle le backbone pour le transfer learning."""
        for param in self.backbone.parameters():
            param.requires_grad = False
    
    def unfreeze_backbone(self):
        """Dégèle le backbone."""
        for param in self.backbone.parameters():
            param.requires_grad = True
    
    def load_pretrained_backbone(self, checkpoint_path: str):
        """Charge un backbone pré-entraîné (ex: sur MVTec)."""
        checkpoint = torch.load(checkpoint_path, map_location="cpu")
        self.backbone.load_state_dict(checkpoint["backbone_state_dict"])
        print(f"[OK] Backbone chargé depuis {checkpoint_path}")


# === TEST ===
if __name__ == "__main__":
    print("=" * 60)
    print("TEST DU MODELE MULTI-VUES VARIABLES")
    print("=" * 60)
    
    model = MultiViewGradingModel(max_views=5, fusion_type="attention")
    
    tests = [
        ("5 vues", torch.tensor([5, 5])),
        ("3 vues", torch.tensor([3, 3])),
        ("1 vue", torch.tensor([1])),
        ("Mixte (4+2)", torch.tensor([4, 2])),
    ]
    
    for name, num_views in tests:
        print(f"\n[TEST] {name}")
        batch_size = len(num_views)
        views = torch.randn(batch_size, 5, 3, 224, 224)
        
        with torch.no_grad():
            out = model(views, num_views)
        
        grades = [model.GRADE_LABELS[g.item()] for g in out["predicted_grade"]]
        print(f"  Grades: {grades}")
        print(f"  Confiance: {out['confidence'].tolist()}")
        print(f"  Vues utilisées: {out['num_views_used'].tolist()}")
    
    total = sum(p.numel() for p in model.parameters())
    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    print(f"\n[INFO] Paramètres: {total:,} total, {trainable:,} entraînables")
    print("[OK] Tous les tests passés!")