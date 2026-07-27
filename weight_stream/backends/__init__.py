"""Backend abstractions for weight streaming inference.

Each backend wraps an inference engine (llama.cpp, etc.) with:
1. Weight access interception (buffer integration)
2. Expert routing for MoE models
3. Streaming-aware token generation

Usage:
    from weight_stream.backends import WeightStreamBackend, WeightStreamModel
"""

from ._base import WeightStreamBackend
from .llama_cpp import WeightStreamModel
