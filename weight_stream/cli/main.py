"""
weight-streaming CLI: Run GGUF models with speculative weight streaming.

Usage:
    python -m weight_stream run model.gguf --prompt "Hello" --max-tokens 100
    python -m weight_stream stats model.gguf
    python -m weight_stream benchmark model.gguf --buffer-mb 64
"""
import argparse
import json
import logging
import sys
import time
from pathlib import Path

from ..backends.llama_cpp import WeightStreamModel


def main():
    parser = argparse.ArgumentParser(
        description="weight-streaming: Run LLMs larger than your RAM",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    
    # run
    run_p = sub.add_parser("run", help="Generate text with weight streaming")
    run_p.add_argument("model", type=str, help="Path to GGUF model")
    run_p.add_argument("--prompt", type=str, default="Hello", help="Input prompt")
    run_p.add_argument("--max-tokens", type=int, default=128, help="Max tokens to generate")
    run_p.add_argument("--buffer-mb", type=int, default=64, help="Buffer size in MB")
    run_p.add_argument("--temperature", type=float, default=0.7, help="Sampling temperature")
    run_p.add_argument("--verbose", action="store_true", help="Enable debug logging")
    run_p.add_argument("--json", action="store_true", help="Output as JSON")
    
    # stats
    stats_p = sub.add_parser("stats", help="Show model metadata")
    stats_p.add_argument("model", type=str, help="Path to GGUF model")
    stats_p.add_argument("--buffer-mb", type=int, default=64)
    
    # benchmark
    bench_p = sub.add_parser("benchmark", help="Benchmark throughput")
    bench_p.add_argument("model", type=str, help="Path to GGUF model")
    bench_p.add_argument("--buffer-mb", type=int, default=64)
    bench_p.add_argument("--max-tokens", type=int, default=256)
    bench_p.add_argument("--no-warmup", action="store_true")
    
    args = parser.parse_args()
    
    if args.command == "run":
        cmd_run(args)
    elif args.command == "stats":
        cmd_stats(args)
    elif args.command == "benchmark":
        cmd_benchmark(args)


def cmd_run(args):
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(message)s",
    )
    
    model = WeightStreamModel(
        args.model,
        buffer_mb=args.buffer_mb,
        verbose=args.verbose,
    )
    
    try:
        output = model.generate(
            prompt=args.prompt,
            max_tokens=args.max_tokens,
            temperature=args.temperature,
        )
        
        if args.json:
            result = {
                "output": output,
                "stats": model.get_stats(),
                "buffer_mb": args.buffer_mb,
            }
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            sys.stdout.buffer.write(f"\n{'='*60}\n".encode('utf-8'))
            sys.stdout.buffer.write(output.encode('utf-8', errors='replace'))
            sys.stdout.buffer.write(f"\n{'='*60}\n".encode('utf-8'))
            
            stats = model.get_stats()
            sys.stdout.buffer.write(
                f"\nBuffer: {stats['buffer']['hot_shards']}/{stats['buffer']['capacity_shards']} shards hot, "
                f"hit rate: {stats['buffer']['hit_rate']:.1%}\n"
                f"Prefetches: {stats['prefetcher']['prefetched']}"
                f"\n\nNOTE: Expert routing interception requires C++ patch (Phase 4).\n"
                f"      Current hit rate reflects tracked prefetches, not actual weight access.\n".encode('utf-8')
            )
            stats = model.get_stats()
            print(f"\nBuffer hit rate: {stats['buffer']['hit_rate']:.1%}")
            print(f"  Hits: {stats['buffer']['hits']}, "
                  f"Misses: {stats['buffer']['misses']}")
            print(f"  Hot shards: {stats['buffer']['hot_shards']}/"
                  f"{stats['buffer']['capacity_shards']}")
            if stats['prefetcher']['prefetched'] > 0:
                print(f"  Prefetches: {stats['prefetcher']['prefetched']}")
    finally:
        model.close()


def cmd_stats(args):
    """Show model metadata and buffer configuration"""
    path = Path(args.model)
    if not path.exists():
        print(f"Error: file not found: {args.model}", file=sys.stderr)
        sys.exit(1)
    
    file_size = path.stat().st_size
    print(f"Model: {path.name}")
    print(f"  Path: {path.absolute()}")
    print(f"  Size: {file_size / 1024**3:.2f} GB ({file_size:,} bytes)")
    print(f"  Shards: {(file_size + (4*1024*1024) - 1) // (4*1024*1024)} "
          f"(at 4 MB each)")
    print(f"Buffer: {args.buffer_mb} MB")
    print(f"  Hot set: ~{args.buffer_mb // 4} shards")
    print(f"  Estimated mode: ", end="")
    
    # Heuristic based on file size
    if file_size > 100 * 1024**3:  # >100 GB
        print("Streaming required (file >> RAM)")
    elif file_size > args.buffer_mb * 1024**2:
        print("Partial streaming (buffer < file)")
    else:
        print("Fits in buffer (file <= buffer)")
    
    print(f"\nTo run: python -m weight_stream run \"{path}\" --prompt \"Hello\"")


def cmd_benchmark(args):
    """Run throughput benchmark"""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    
    # Warmup
    if not args.no_warmup:
        print("Warming up...")
        warmup = WeightStreamModel(
            args.model,
            buffer_mb=args.buffer_mb,
            verbose=False,
        )
        try:
            warmup.generate("Hello", max_tokens=5)
        finally:
            warmup.close()
        print("Warmup complete.\n")
    
    # Benchmark
    print(f"Benchmarking: {args.model}")
    print(f"  Buffer: {args.buffer_mb} MB")
    print(f"  Max tokens: {args.max_tokens}")
    print()
    
    model = WeightStreamModel(
        args.model,
        buffer_mb=args.buffer_mb,
        verbose=False,
    )
    
    try:
        start_time = time.time()
        _ = model.generate("The future of AI is", max_tokens=args.max_tokens)
        elapsed = time.time() - start_time
        
        stats = model.get_stats()
        tokens = stats['buffer']['total_accesses']
        # We can't count actual tokens from generate, so estimate
        # The generate method doesn't return token count easily
        
        stats_output = model.get_stats()
        print(f"\n{'='*60}")
        print(f"Results:")
        print(f"  Elapsed: {elapsed:.2f}s")
        print(f"  Buffer hit rate: {stats_output['buffer']['hit_rate']:.1%}")
        print(f"  Total accesses: {stats_output['buffer']['total_accesses']}")
        print(f"  Hits: {stats_output['buffer']['hits']}")
        print(f"  Misses: {stats_output['buffer']['misses']}")
        print(f"  Evictions: {stats_output['buffer']['evictions']}")
        print(f"  Prefetches: {stats_output['prefetcher']['prefetched']}")
        print(f"{'='*60}")
    
    finally:
        model.close()


if __name__ == "__main__":
    main()
