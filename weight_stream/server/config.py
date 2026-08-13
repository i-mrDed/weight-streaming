"""
Server configuration for the weight-streaming API server.

All configurable defaults live here. Override via environment variables
or constructor arguments in production.
"""

import os
from dataclasses import dataclass, field, fields


def _default_n_threads() -> int:
    """Leave CPU headroom for the API server, browser, and operating system."""
    return max(1, (os.cpu_count() or 4) // 2)


def get_model_search_dirs() -> list[str]:
    """Return the default GGUF model search directories (pure — no scan).

    Shared by ``/v1/models/scan``, ``/v1/config`` and the Hub download
    ``target_dir`` allow-list, so every consumer agrees on which folders
    are legitimate model locations. Honors ``WS_MODELS_DIR`` first, then
    the common local stores users actually keep GGUFs in.
    """
    dirs: list[str] = []
    ws_dir = os.environ.get("WS_MODELS_DIR", "")
    if ws_dir:
        dirs.append(ws_dir)
    dirs.extend([
        os.getcwd(),
        os.path.join(os.getcwd(), "research", "models"),
        os.path.join(os.getcwd(), "models"),
        os.path.expanduser("~/models"),
    ])
    if os.name == "nt":
        appdata = os.environ.get("APPDATA", "")
        if appdata:
            dirs.append(os.path.join(appdata, "Jan", "data", "llamacpp", "models"))
    return dirs


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
        default_factory=lambda: int(os.getenv("WS_N_CTX", "32768"))
    )
    default_n_threads: int = field(
        default_factory=lambda: int(os.getenv("WS_N_THREADS", str(_default_n_threads())))
    )
    # GPU offload control for the llama-server backend (P7.5):
    #   default_gpu_layers  — -1 = auto (llama-server decides), 0 = CPU only,
    #                         N = offload first N layers to VRAM.
    #   default_kv_cache_type — KV cache data type ("f16" default, "q8_0",
    #                         "q4_0", …); empty = llama-server's default.
    # Both only matter on the GPU backend; the CPU binding ignores them.
    default_gpu_layers: int = field(
        default_factory=lambda: int(os.getenv("WS_GPU_LAYERS", "-1"))
    )
    default_kv_cache_type: str = field(
        default_factory=lambda: os.getenv("WS_KV_CACHE_TYPE", "").strip()
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

    # CPU etiquette: run the server one priority class below normal while a
    # model is loaded, so the desktop/browser/IDE stay responsive during
    # generation (near-zero throughput cost on an idle machine).
    # Set WS_LOWER_PRIORITY=0/false to disable.
    lower_process_priority: bool = field(
        default_factory=lambda: os.getenv(
            "WS_LOWER_PRIORITY", "1"
        ).strip().lower() not in ("0", "false", "no", "off")
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


# ServerConfig field → environment variable that seeds its default. Used by
# GET /v1/config to report, per key, whether the effective value came from an
# environment variable or the built-in default.
CONFIG_ENV_KEYS: dict[str, str] = {
    "host": "WS_HOST",
    "port": "WS_PORT",
    "default_buffer_mb": "WS_BUFFER_MB",
    "default_n_ctx": "WS_N_CTX",
    "default_n_threads": "WS_N_THREADS",
    "default_gpu_layers": "WS_GPU_LAYERS",
    "default_kv_cache_type": "WS_KV_CACHE_TYPE",
    "idle_unload_timeout": "WS_IDLE_TIMEOUT",
    "max_loaded_models": "WS_MAX_MODELS",
    "lower_process_priority": "WS_LOWER_PRIORITY",
    "max_concurrent_requests": "WS_MAX_REQUESTS",
    "request_queue_depth": "WS_QUEUE_DEPTH",
    "log_level": "WS_LOG_LEVEL",
}


def describe_config(cfg: ServerConfig) -> dict[str, dict]:
    """Describe each config key as ``{"value": …, "source": "env"|"default"}``.

    ``source`` is determined by re-checking ``os.getenv`` for the key's
    ``WS_*`` variable (the dataclass reads env at construction but records no
    source). Honest limitation: a value injected through the CLI constructor
    with no matching env var is reported as ``"default"`` — the effective
    value is still correct, we simply cannot distinguish CLI from default
    without extra instrumentation (not worth it in P4).
    """
    out: dict[str, dict] = {}
    overrides = set(getattr(cfg, "_runtime_overrides", set()))
    for f in fields(cfg):
        env_key = CONFIG_ENV_KEYS.get(f.name)
        if f.name in overrides:
            source = "runtime"  # mutated via PATCH /v1/config
        elif env_key and os.getenv(env_key) is not None:
            source = "env"
        else:
            source = "default"
        out[f.name] = {"value": getattr(cfg, f.name), "source": source}
    return out
