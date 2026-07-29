"""
weight-streaming: Run LLMs larger than your RAM using NVMe as extension of memory.

Usage:
    from weight_stream import WeightStreamModel
    
    model = WeightStreamModel("model.gguf", buffer_mb=64)
    output = model.generate("Hello, world")
"""

__version__ = "0.13.0"

from .backends.llama_cpp import WeightStreamModel
from .core.exceptions import (
    WeightStreamError,
    ModelError,
    BufferError,
    PrefetchError,
    GenerationError,
    ConfigError,
)
