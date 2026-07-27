"""python -m weight_stream.server entry point.

Starts the weight-streaming API server, optionally auto-loading a model.

Usage:
    python -m weight_stream.server --model path/to/model.gguf
    python -m weight_stream.server --host 0.0.0.0 --port 8080
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

import uvicorn

from .config import ServerConfig, get_config, set_config


def main():
    parser = argparse.ArgumentParser(
        description="Weight Streaming API Server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Example:\n"
            "  python -m weight_stream.server --model model.gguf\n"
            "  python -m weight_stream.server --host 0.0.0.0 --port 8080 --model model.gguf"
        ),
    )
    parser.add_argument(
        "--host", default="127.0.0.1",
        help="Bind address (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port", type=int, default=8765,
        help="Bind port (default: 8765)",
    )
    parser.add_argument(
        "--model", type=str, default=None,
        help="Auto-load a model on startup (path to GGUF file)",
    )
    parser.add_argument(
        "--model-id", type=str, default="default",
        help="Model ID for auto-loaded model (default: 'default')",
    )
    parser.add_argument(
        "--buffer-mb", type=int, default=64,
        help="Buffer size in MB (default: 64)",
    )
    parser.add_argument(
        "--n-ctx", type=int, default=512,
        help="Context window size (default: 512)",
    )
    parser.add_argument(
        "--n-threads", type=int, default=None,
        help="Number of CPU threads (default: CPU count)",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Enable debug logging",
    )
    
    args = parser.parse_args()
    
    # Configure logging
    log_level = "DEBUG" if args.verbose else "INFO"
    logging.basicConfig(
        level=getattr(logging, log_level),
        format="%(levelname)s: %(name)s: %(message)s",
    )
    
    # Configure server
    config = ServerConfig(
        host=args.host,
        port=args.port,
        default_buffer_mb=args.buffer_mb,
        default_n_ctx=args.n_ctx,
        default_n_threads=args.n_threads or (os.cpu_count() or 4),
    )
    set_config(config)
    
    logger = logging.getLogger(__name__)
    logger.info(f"Weight Streaming API Server v0.11.0")
    logger.info(f"Listening on http://{args.host}:{args.port}")
    logger.info(f"API docs: http://{args.host}:{args.port}/docs")
    logger.info(f"Web app:  http://{args.host}:{args.port}/app")
    
    if args.model:
        logger.info(f"Auto-loading model: {args.model} (id={args.model_id})")
        os.environ["WS_AUTO_MODEL_PATH"] = args.model
        os.environ["WS_AUTO_MODEL_ID"] = args.model_id
    
    # Create app and manager, then pass app directly to uvicorn
    from .api_server import create_app
    from .config import get_config
    app, manager = create_app(get_config())
    
    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        log_level=log_level.lower(),
    )


if __name__ == "__main__":
    main()
