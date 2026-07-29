"""Command-line interface for weight-streaming."""

import argparse
import sys
import json

def main():
    parser = argparse.ArgumentParser(
        prog="weight-stream",
        description="⚡ Weight-Streaming: High-Performance Speculative MoE Weight Streaming Engine"
    )
    subparsers = parser.add_subparsers(dest="command", help="Available sub-commands")

    # 1. Repack subcommand
    repack_parser = subparsers.add_parser("repack", help="Repack model weights into contiguous popularity layout")
    repack_parser.add_argument("input", help="Input GGUF model path")
    repack_parser.add_argument("output", help="Output repacked model path")
    repack_parser.add_argument("--shard-size-mb", type=float, default=4.0, help="Shard size in MB (default: 4.0)")

    # 2. Dashboard subcommand
    dash_parser = subparsers.add_parser("dashboard", help="Start Live Streaming Web Dashboard")
    dash_parser.add_argument("--port", type=int, default=8766, help="Web server port (default 8766)")
    dash_parser.add_argument("--host", type=str, default="127.0.0.1", help="Host address (default 127.0.0.1)")

    # 3. Auto-tune subcommand
    tune_parser = subparsers.add_parser("auto-tune", help="Hardware profiler — recommend optimal streaming config")
    tune_parser.add_argument("--model-size-gb", type=float, default=14.0, help="Model size in GB")
    tune_parser.add_argument("--json", action="store_true", help="Output raw JSON")

    # 4. Benchmark subcommand
    bench_parser = subparsers.add_parser("benchmark", help="Run reproducible benchmark suite")
    bench_parser.add_argument("--model", type=str, default="Kimi-K3-2.8T-MXFP4", help="Model name tag")
    bench_parser.add_argument("--buffer-mb", type=int, default=512, help="Buffer capacity in MB")
    bench_parser.add_argument("--tokens", type=int, default=128, help="Token count for benchmark")
    bench_parser.add_argument("--export", type=str, default="", help="Export report path (.md)")

    # 5. Inspect subcommand (GGUF Arch Auto-Detector)
    inspect_parser = subparsers.add_parser("inspect", help="Inspect GGUF model metadata & detect architecture")
    inspect_parser.add_argument("model", help="Path to GGUF model file")

    # 6. Serve subcommand (Production API Server)
    serve_parser = subparsers.add_parser("serve", help="Start OpenAI-compatible API server")
    serve_parser.add_argument("--host", type=str, default="127.0.0.1", help="Host address (default 127.0.0.1)")
    serve_parser.add_argument("--port", type=int, default=8765, help="Server port (default 8765)")
    serve_parser.add_argument("--auto-tune", action="store_true", help="Auto-tune buffer & thread settings before launch")

    args = parser.parse_args()

    if args.command == "repack":
        from weight_stream.tools.shard_repacker import ShardRepacker
        repacker = ShardRepacker(args.input, args.output, shard_size_mb=args.shard_size_mb)
        res = repacker.repack()
        print("Repack Completed:", res)

    elif args.command == "dashboard":
        from weight_stream.server.dashboard_server import run_dashboard_server
        run_dashboard_server(args.port)

    elif args.command == "auto-tune":
        from weight_stream.tools.auto_tune import get_system_profile, recommend_config, print_recommendation
        profile = get_system_profile()
        config = recommend_config(profile, model_size_gb=args.model_size_gb)
        if args.json:
            print(json.dumps(config, indent=2))
        else:
            print_recommendation(config)

    elif args.command == "benchmark":
        from weight_stream.tools.benchmark_suite import BenchmarkSuite
        suite = BenchmarkSuite(model_name=args.model, buffer_size_mb=args.buffer_mb)
        res = suite.run_benchmark(num_tokens=args.tokens)
        print("Benchmark Completed:\n", json.dumps(res, indent=2))
        if args.export:
            suite.export_report_markdown(args.export)

    elif args.command == "inspect":
        from weight_stream.gguf.parser import GGUFParser
        with GGUFParser(args.model) as parser_obj:
            arch_info = parser_obj.detect_architecture()
            print("\n🔍 GGUF Architecture Specs:")
            print(json.dumps(arch_info, indent=2))

    elif args.command == "serve":
        if args.auto_tune:
            from weight_stream.tools.auto_tune import get_system_profile, recommend_config
            profile = get_system_profile()
            tuned = recommend_config(profile)
            print(f"⚡ Auto-Tuned Settings: buffer={tuned['buffer_mb']}MB, threads={tuned['n_threads']}, n_ctx={tuned['n_ctx']}")
            # Set environment variables for config override
            import os
            os.environ["WS_BUFFER_SIZE_MB"] = str(tuned["buffer_mb"])
            os.environ["WS_N_THREADS"] = str(tuned["n_threads"])
            os.environ["WS_N_CTX"] = str(tuned["n_ctx"])

        import uvicorn
        print(f"🚀 Starting Weight-Streaming API Server on http://{args.host}:{args.port}...")
        uvicorn.run("weight_stream.server.app:app", host=args.host, port=args.port, reload=False)

    else:
        parser.print_help()

if __name__ == "__main__":
    main()
