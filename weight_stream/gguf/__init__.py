"""GGUF model parser — maps tensor names to file offsets.

Wraps the official `gguf` library with expert-aware features:
- Tensor name → file offset lookup
- Per-expert offset ranges for targeted prefetching
- Model metadata extraction
"""
from .parser import GGUFParser, TensorInfo, ExpertRange
