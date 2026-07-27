"""
Custom exceptions for the weight-streaming package.

Hierarchy:
    WeightStreamError (base)
    ├── ModelError         — Model file issues (not found, corrupt, unsupported)
    ├── BufferError        — Buffer capacity or allocation failures
    ├── PrefetchError      — Prefetcher thread or I/O failures
    ├── GenerationError    — Inference engine failures during generation
    └── ConfigError        — Invalid configuration parameters
"""

from typing import Optional


class WeightStreamError(Exception):
    """Base exception for all weight-streaming errors."""
    
    def __init__(self, message: str, details: Optional[dict] = None):
        self.message = message
        self.details = details or {}
        super().__init__(self.message)
    
    def __str__(self) -> str:
        if self.details:
            detail_str = ", ".join(f"{k}={v}" for k, v in self.details.items())
            return f"{self.message} ({detail_str})"
        return self.message


class ModelError(WeightStreamError):
    """Model file or format related errors."""
    
    def __init__(
        self,
        message: str,
        model_path: Optional[str] = None,
        details: Optional[dict] = None,
    ):
        merged = dict(details or {})
        if model_path is not None:
            merged["model"] = model_path
        super().__init__(message, details=merged)


class BufferError(WeightStreamError):
    """Buffer capacity or allocation errors."""
    pass


class PrefetchError(WeightStreamError):
    """Prefetcher thread or I/O errors."""
    pass


class GenerationError(WeightStreamError):
    """Inference engine failures during generation."""
    
    def __init__(
        self,
        message: str,
        token_count: Optional[int] = None,
        details: Optional[dict] = None,
    ):
        merged = dict(details or {})
        if token_count is not None:
            merged["tokens"] = token_count
        super().__init__(message, details=merged)


class ConfigError(WeightStreamError):
    """Invalid configuration parameters."""
    pass
