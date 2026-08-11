"""
Top-level package for model components (cv, pricing).
Provides easy import of subpackages.
"""

# Do not eagerly import subpackages here. In particular, importing ``cv``
# loads the PyTorch/timm training stack and defeats ONNX-only production use.
