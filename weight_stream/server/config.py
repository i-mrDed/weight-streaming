"""
Server configuration for the weight-streaming API server.

All configurable defaults live here. Override via environment variables
or constructor arguments in production.
"""

import os
from dataclasses import dataclass, field


def _default_n_threads() -> int:
    """Leave CPU headroom for the API server, browser, and operating system."""
    return max(1, (os.cpu_count() or 4) // 2)


@dataclass
class ServerConfig:
    """API server configuration."""
    
    # Network
    host: str = field(
        default_factory=lambda: os.getenv("WS_HOST", "127.0.0.1")
    )
    port: int = field(
        default_factory=lambda: int(os.getenv("WS_PORT", "8765"))
    )
    
    # Model defaults
    default_buffer_mb: int = field(
        default_factory=lambda: int(os.getenv("WS_BUFFER_MB", "64"))
    )
    default_n_ctx: int = field(
        default_factory=lambda: int(os.getenv("WS_N_CTX", "2048"))
    )
    default_n_threads: int = field(
        default_factory=lambda: int(os.getenv("WS_N_THREADS", str(_default_n_threads())))
    )
    
    # Model lifecycle
    idle_unload_timeout: float = field(
        # A local interactive chat should keep its loaded model by default.
        # Set a positive number of seconds to enable resource reclamation.
        default_factory=lambda: float(os.getenv("WS_IDLE_TIMEOUT", "0"))
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
