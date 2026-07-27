"""
Weight Streaming API Server.

Provides REST API and WebSocket endpoints for text generation
with speculative weight streaming from NVMe.

Usage:
    python -m weight_stream.server --model path/to/model.gguf
    python -m weight_stream server --model path/to/model.gguf
"""

from .api_server import create_app
from .config import ServerConfig, get_config, set_config
from .model_manager import ModelManager
