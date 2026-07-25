"""
Backbone CNN/ViT pour l'extraction de features.
Pré-entraîné sur ImageNet ou MVTec AD.
"""

import torch
import torch.nn as nn
import timm # collection de modeles CV


def create_backbone(
    model_name: str = "vit_base_patch16_224",
    pretrained: bool = True,
    num_classes: int = 0,
    global_pool: str = "token" # Pooling des features de chaque vue
) -> tuple[nn.Module, int]:
    """
    Crée un backbone et retourne le modèle + la dimension des embeddings.
    
    Args:
        model_name: Nom du modèle timm (vit_base_patch16_224, resnet50, etc.)
        pretrained: Charger les poids pré-entraînés
        num_classes: 0 = pas de classification finale (feature extraction)
        global_pool: Stratégie de pooling
    
    Returns:
        (model, embed_dim)
    """
    model = timm.create_model(
        model_name,
        pretrained=pretrained,
        num_classes=num_classes,
        global_pool=global_pool
    )
    
    # Récupère la dimension des embeddings
    with torch.no_grad():
        dummy = torch.randn(1, 3, 224, 224)
        embed_dim = model(dummy).shape[-1]
    
    return model, embed_dim