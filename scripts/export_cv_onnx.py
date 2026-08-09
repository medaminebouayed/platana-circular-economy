import torch
from pathlib import Path
import sys

# Ensure models package is discoverable
root_dir = Path(__file__).resolve().parent.parent
sys.path.append(str(root_dir))

from models.cv.model import MultiTaskDefectModel
from models.cv.dataset import DEFECT_CLASSES

def export_to_onnx():
    device = torch.device("cpu")
    model_path = root_dir / "models" / "cv" / "checkpoints" / "best_multitask_model.pth"
    onnx_path = root_dir / "models" / "cv" / "checkpoints" / "best_multitask_model.onnx"
    
    if not model_path.exists():
        print(f"Error: Could not find model at {model_path}")
        # Try best_grading_model.pth
        model_path = root_dir / "best_grading_model.pth"
        if not model_path.exists():
             print(f"Error: Could not find model at {model_path} either.")
             return
             
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
    
    print("Export successful!")

if __name__ == "__main__":
    export_to_onnx()
