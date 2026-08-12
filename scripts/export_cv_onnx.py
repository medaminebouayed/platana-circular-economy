import torch
from pathlib import Path
import sys
import argparse
import json

# Ensure models package is discoverable
root_dir = Path(__file__).resolve().parent.parent
sys.path.append(str(root_dir))

from models.cv.model import MultiTaskDefectModel
from models.cv.dataset import DEFECT_CLASSES
from models.artifacts import promote_version, resolve_latest_artifact, write_manifest

def export_to_onnx(version_id=None):
    device = torch.device("cpu")
    checkpoint_dir = root_dir / "models" / "cv" / "checkpoints"
    if version_id:
        version_dir = checkpoint_dir / "versions" / version_id
        model_path = version_dir / "model.pth"
    else:
        model_path, version_id = resolve_latest_artifact(
            checkpoint_dir, "model.pth", pointer_name="latest_training.json"
        )
        if model_path is None:
            model_path = checkpoint_dir / "best_multitask_model.pth"
            version_id = "legacy"
        version_dir = model_path.parent
    onnx_path = version_dir / "model.onnx"
    
    if not model_path.exists():
        print(f"Error: Could not find model at {model_path}")
        raise FileNotFoundError(f"Could not find model at {model_path}")
             
    print(f"Loading PyTorch model from {model_path}...")
    
    # We pass None for mvtec_weights_path because we're loading the full finetuned state_dict
    model = MultiTaskDefectModel(num_grades=4, num_defects=len(DEFECT_CLASSES), mvtec_weights_path=None)
    
    # Load state dict
    try:
        model.load_state_dict(torch.load(model_path, map_location=device))
    except Exception as e:
        print(f"Failed to load weights natively, trying strict=False. Error: {e}")
        model.load_state_dict(torch.load(model_path, map_location=device), strict=False)
        
    model.eval()
    
    # Create dummy input (batch_size=1, channels=3, height=224, width=224)
    dummy_input = torch.randn(1, 3, 224, 224)
    
    print(f"Exporting to ONNX: {onnx_path}...")
    torch.onnx.export(
        model, 
        dummy_input, 
        str(onnx_path),
        export_params=True,
        opset_version=14,
        do_constant_folding=True,
        input_names=['input'],
        output_names=['grade_logits', 'defect_logits'],
        dynamic_axes={'input': {0: 'batch_size'}, 'grade_logits': {0: 'batch_size'}, 'defect_logits': {0: 'batch_size'}}
    )
    
    if version_id != "legacy":
        manifest_path = version_dir / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
        manifest["artifacts"] = {**manifest.get("artifacts", {}), "model": "model.pth", "onnx": "model.onnx"}
        write_manifest(version_dir, manifest)
        promote_version(checkpoint_dir, version_id, {"model": "model.pth", "onnx": "model.onnx"})
    print(f"[OK] ONNX export complete; active CV version: {version_id}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--version-id", help="Training version to export; defaults to latest training version")
    args = parser.parse_args()
    export_to_onnx(args.version_id)
