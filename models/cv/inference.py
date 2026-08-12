"""ONNX Runtime inference for the CV grading service.

This module intentionally has no PyTorch, torchvision, or timm imports.  Model
training and ONNX export remain development-time operations; production loads
only the exported ``.onnx`` artifact.
"""

from pathlib import Path
from typing import Iterable
import argparse
import sys

import numpy as np
import onnxruntime as ort
from PIL import Image


IDX_TO_GRADE = {0: "A", 1: "B", 2: "C", 3: "D"}
DEFECT_CLASSES = ["no_defect", "screen_crack", "cosmetic_scratch"]
_IMAGE_SIZE = (224, 224)
_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)


class MultiViewGrader:
    """Run a multi-view grading model exported to ONNX on the CPU.

    Preprocessing matches the former torchvision validation transform:
    resize to 224x224, convert RGB pixels to [0, 1], and apply ImageNet
    normalization.  The model is evaluated once for all submitted views.
    """

    def __init__(self, model_path: str | Path):
        self.model_path = Path(model_path)
        if self.model_path.suffix.lower() != ".onnx":
            raise ValueError(
                "CV production inference accepts an ONNX model only. "
                f"Expected a .onnx file, received: {self.model_path}"
            )
        if not self.model_path.is_file():
            raise FileNotFoundError(f"ONNX model not found: {self.model_path}")

        self.session = ort.InferenceSession(
            str(self.model_path), providers=["CPUExecutionProvider"]
        )
        self.input_name = self.session.get_inputs()[0].name
        self.output_names = {output.name for output in self.session.get_outputs()}
        required_outputs = {"grade_logits", "defect_logits"}
        if not required_outputs.issubset(self.output_names):
            raise ValueError(
                "Unexpected ONNX outputs. Expected grade_logits and defect_logits; "
                f"received {sorted(self.output_names)}. Re-export the model with "
                "scripts/export_cv_onnx.py."
            )

    @staticmethod
    def _preprocess(path: str | Path) -> np.ndarray:
        with Image.open(path) as image:
            image = image.convert("RGB").resize(_IMAGE_SIZE, Image.Resampling.BILINEAR)
            pixels = np.asarray(image, dtype=np.float32) / 255.0

        normalized = (pixels - _MEAN) / _STD
        return np.ascontiguousarray(np.transpose(normalized, (2, 0, 1)))

    @staticmethod
    def _softmax(logits: np.ndarray) -> np.ndarray:
        shifted = logits - np.max(logits, axis=1, keepdims=True)
        exp = np.exp(shifted)
        return exp / np.sum(exp, axis=1, keepdims=True)

    @staticmethod
    def _sigmoid(logits: np.ndarray) -> np.ndarray:
        return 1.0 / (1.0 + np.exp(-logits))

    def predict_defects_and_grade(self, image_paths: Iterable[str | Path]) -> tuple[str, list[str]]:
        paths = list(image_paths)
        if not paths:
            return "Unknown", ["no_defect"]

        batch = np.stack([self._preprocess(path) for path in paths]).astype(np.float32)
        grade_logits, defect_logits = self.session.run(
            ["grade_logits", "defect_logits"], {self.input_name: batch}
        )

        grade_indices = np.argmax(self._softmax(grade_logits), axis=1)
        view_grades = [IDX_TO_GRADE[int(index)] for index in grade_indices]
        # Preserve the previous conservative late-fusion rule: the worst view wins.
        final_grade = max(view_grades)

        max_defect_probabilities = np.max(self._sigmoid(defect_logits), axis=0)
        defects = [
            defect
            for defect, probability in zip(DEFECT_CLASSES, max_defect_probabilities)
            if probability > 0.5 and defect != "no_defect"
        ]
        if not defects:
            defects = ["no_defect"]

        if "screen_crack" in defects:
            final_grade = "D"

        return final_grade, defects


def _resolve_cli_model(model_path: str | None, version_id: str | None) -> Path:
    if model_path and version_id:
        raise ValueError("Use either --model-path or --version-id, not both.")
    if model_path:
        return Path(model_path)
    checkpoint_dir = Path(__file__).resolve().parent / "checkpoints"
    if version_id:
        from models.artifacts import resolve_version_artifact
        return resolve_version_artifact(checkpoint_dir, version_id, "model.onnx")
    from models.artifacts import resolve_latest_artifact
    active_model, _ = resolve_latest_artifact(checkpoint_dir, "model.onnx")
    return active_model or (checkpoint_dir / "best_multitask_model.onnx")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run versioned ONNX CV inference.")
    parser.add_argument("images", nargs="+", help="One or more image paths")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--version-id", help="Immutable CV version under checkpoints/versions")
    group.add_argument("--model-path", help="Explicit ONNX model path")
    args = parser.parse_args()
    model_path = _resolve_cli_model(args.model_path, args.version_id)
    grade, defects = MultiViewGrader(model_path).predict_defects_and_grade(args.images)
    print({"model_path": str(model_path), "grade": grade, "detected_defects": defects})


if __name__ == "__main__":
    # Allows `python models/cv/inference.py ...` as well as module execution.
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    main()
