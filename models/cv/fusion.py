"""
Modules de fusion multi-vues.
Gère un nombre VARIABLE de vues (1 à N).
"""

import torch
import torch.nn as nn
import torch.nn.functional as F


class FusionModule(nn.Module):
    """Base class pour la fusion."""
    pass


class MeanFusion(FusionModule):
    """Fusion par moyenne simple (robuste, pas de paramètres)."""
    
    def forward(self, embeddings: torch.Tensor, mask: torch.Tensor) -> tuple:
        """
        Args:
            embeddings: (B, N, D)
            mask: (B, N) — True pour les vues valides
        Returns:
            fused: (B, D), weights: (B, N)
        """
        counts = mask.sum(dim=1, keepdim=True).float().clamp(min=1)
        fused = (embeddings * mask.unsqueeze(-1).float()).sum(dim=1) / counts
        weights = mask.float() / counts
        return fused, weights


class AttentionFusion(FusionModule):
    """Fusion par attention learnable."""
    
    def __init__(self, embed_dim: int):
        super().__init__()
        self.attention = nn.Sequential(
            nn.Linear(embed_dim, embed_dim // 4),
            nn.Tanh(),
            nn.Linear(embed_dim // 4, 1)
        )
    
    def forward(self, embeddings: torch.Tensor, mask: torch.Tensor) -> tuple:
        """
        Args:
            embeddings: (B, N, D)
            mask: (B, N)
        Returns:
            fused: (B, D), weights: (B, N)
        """
        # Scores d'attention
        scores = self.attention(embeddings).squeeze(-1)  # (B, N)
        
        # Masquer les vues invalides
        scores = scores.masked_fill(~mask, float('-inf'))
        
        # Softmax sur les vues valides
        weights = F.softmax(scores, dim=1)  # (B, N)
        
        # Pondération
        fused = torch.bmm(weights.unsqueeze(1), embeddings).squeeze(1)  # (B, D)
        
        return fused, weights


class TransformerFusion(FusionModule):
    """Fusion par Transformer (CLS token)."""
    
    def __init__(self, embed_dim: int, num_layers: int = 2, num_heads: int = 8, dropout: float = 0.3):
        super().__init__()
        self.cls_token = nn.Parameter(torch.randn(1, 1, embed_dim))
        self.transformer = nn.TransformerEncoder(
            nn.TransformerEncoderLayer(
                d_model=embed_dim,
                nhead=num_heads,
                dim_feedforward=embed_dim * 4,
                dropout=dropout,
                batch_first=True
            ),
            num_layers=num_layers
        )
    
    def forward(self, embeddings: torch.Tensor, mask: torch.Tensor) -> tuple:
        """
        Args:
            embeddings: (B, N, D)
            mask: (B, N)
        Returns:
            fused: (B, D), weights: (B, N)
        """
        B, N, D = embeddings.shape
        
        # CLS token
        cls = self.cls_token.expand(B, -1, -1)  # (B, 1, D)
        sequence = torch.cat([cls, embeddings], dim=1)  # (B, 1+N, D)
        
        # Masque pour le transformer (True = masqué)
        transformer_mask = torch.cat([
            torch.zeros(B, 1, dtype=torch.bool, device=embeddings.device),
            ~mask
        ], dim=1)
        
        # Forward
        output = self.transformer(sequence, src_key_padding_mask=transformer_mask)
        fused = output[:, 0]  # CLS token
        
        # Poids uniformes (simplifié)
        weights = mask.float() / mask.sum(dim=1, keepdim=True).clamp(min=1)
        
        return fused, weights