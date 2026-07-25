"""
Export du modèle CV vers ONNX pour l'inférence rapide en production.
"""

import argparse

import torch
import onnx

from grading_model import MultiViewGradingModel


def export_to_onnx(
    model_path: str,
    output_path: str,
    max_views: int = 5,
    image_size: int = 224
):
    """Exporte le modèle PyTorch vers ONNX."""
    
    # Charge le modèle
    checkpoint = torch.load(model_path, map_location="cpu")
    config = checkpoint["config"]
    
    model = MultiViewGradingModel(
        max_views=max_views,
        backbone_name=config["model"]["backbone"],
        fusion_type=config["model"]["fusion_type"]
    )
    model.load_state_dict(checkpoint["model_state_dict"])
    model.eval()
    
    # Dummy input
    dummy_views = torch.randn(1, max_views, 3, image_size, image_size)
    dummy_num_views = torch.tensor([max_views])
    
    # Export
    torch.onnx.export(
        model,
        (dummy_views, dummy_num_views),
        output_path,
        export_params=True,
        opset_version=14,
        do_constant_folding=True,
        input_names=["views", "num_views"],
        output_names=["grade_logits", "defect_logits"],
        dynamic_axes={
            "views": {0: "batch_size"},
            "num_views": {0: "batch_size"},
            "grade_logits": {0: "batch_size"},
            "defect_logits": {0: "batch_size"}
        }
    )
    
    # Vérification
    onnx_model = onnx.load(output_path)
    onnx.checker.check_model(onnx_model)
    
    print(f"[OK] Modèle exporté vers {output_path}")
    print(f"  Inputs: views (batch, {max_views}, 3, {image_size}, {image_size})")
    print(f"  Outputs: grade_logits (batch, 4), defect_logits (batch, 6)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True, help="Chemin vers le .pt")
    parser.add_argument("--output", required=True, help="Chemin de sortie .onnx")
    parser.add_argument("--max_views", type=int, default=5)
    args = parser.parse_args()
    
    export_to_onnx(args.model, args.output, args.max_views)