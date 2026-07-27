"""
Abstract backend interface for weight-streaming model adapters.

All model backends (llama-cpp-python, HuggingFace, vLLM, etc.) must
implement this interface to work with the weight-streaming pipeline.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


class WeightStreamBackend(ABC):
    """
    Abstract interface for a weight-streaming model backend.
    
    Each backend wraps a specific inference engine (llama-cpp-python,
    HuggingFace transformers, etc.) and provides:
    
    - Model loading with mmap overlay for OS page cache monitoring
    - Expert-aware tensor mapping via GGUF parser
    - Text generation with speculative weight prefetch
    - Resource cleanup via context manager protocol
    """
    
    @abstractmethod
    def generate(
        self,
        prompt: str,
        max_tokens: int = 128,
        temperature: float = 0.7,
        top_p: float = 0.9,
        **kwargs,
    ) -> str:
        """
        Generate text with weight streaming.
        
        During generation, the prefetcher runs in background,
        predicting and loading hot shards during compute time.
        
        Args:
            prompt: Input text prompt
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature (0.0 = greedy)
            top_p: Nucleus sampling threshold
            **kwargs: Additional backend-specific args
            
        Returns:
            Generated text string
            
        Raises:
            WeightStreamError: On generation failure
        """
        ...
    
    @abstractmethod
    def close(self):
        """
        Clean up all resources.
        
        Releases mmap, closes file handles, stops prefetcher thread,
        and shuts down the underlying inference engine.
        
        Must be safe to call multiple times.
        """
        ...
    
    @abstractmethod
    def get_stats(self) -> Dict[str, Any]:
        """
        Return performance and state statistics.
        
        Returns:
            Dict with keys:
            - 'buffer': buffer stats (hit_rate, hot_shards, capacity, ...)
            - 'generation': last generation stats (tokens, elapsed, tok/s)
            - 'page_cache': resident ratio (if monitor active) or None
            - 'model': model info (path, size, ...)
        """
        ...
    
    # ── Context manager protocol ──────────────────────────────────
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False  # Don't suppress exceptions
    
    # ── Optional hooks ────────────────────────────────────────────
    
    @property
    def model_path(self) -> Optional[str]:
        """Path to the model file, or None if not loaded."""
        return getattr(self, '_model_path', None)
    
    @property
    def is_loaded(self) -> bool:
        """True if the model is loaded and ready for inference."""
        return False
