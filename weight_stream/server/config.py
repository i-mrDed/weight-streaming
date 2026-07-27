"""
Server configuration for the weight-streaming API server.

All configurable defaults live here. Override via environment variables
or constructor arguments in production.
"""

import os
from dataclasses import dataclass, field


@dataclass
class ServerConfig:
    """API server configuration."""
    
    # Network
    host: str = field(
        default_factory=lambda: os.getenv("WS_HOST", "127.0.0.1")
    )
    port: int = field(
        default_factory=lambda: int(os.getenv("WS_PORT", "8080"))
    )
    
    # Model defaults
    default_buffer_mb: int = field(
        default_factory=lambda: int(os.getenv("WS_BUFFER_MB", "64"))
    )
    default_n_ctx: int = field(
        default_factory=lambda: int(os.getenv("WS_N_CTX", "512"))
    )
    default_n_threads: int = field(
        default_factory=lambda: int(os.getenv("WS_N_THREADS", str(os.cpu_count() or 4)))
    )
    
    # Model lifecycle
    idle_unload_timeout: float = field(
        default_factory=lambda: float(os.getenv("WS_IDLE_TIMEOUT", "300"))
    )
    max_loaded_models: int = field(
        default_factory=lambda: int(os.getenv("WS_MAX_MODELS", "4"))
    )
    
    # Request limits
    max_concurrent_requests: int = field(
        default_factory=lambda: int(os.getenv("WS_MAX_REQUESTS", "3"))
    )
    request_queue_depth: int = field(
        default_factory=lambda: int(os.getenv("WS_QUEUE_DEPTH", "3"))
    )
    
    # Logging
    log_level: str = field(
        default_factory=lambda: os.getenv("WS_LOG_LEVEL", "info")
    )


# Singleton default config
_default_config: ServerConfig | None = None


def get_config() -> ServerConfig:
    """Get the global server configuration."""
    global _default_config
    if _default_config is None:
        _default_config = ServerConfig()
    return _default_config


def set_config(config: ServerConfig):
    """Override the global server configuration."""
    global _default_config
    _default_config = config
