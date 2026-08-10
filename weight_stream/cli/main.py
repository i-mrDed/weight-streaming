"""
weight-streaming CLI — run GGUF models with speculative weight streaming.

Usage:
    python -m weight_stream run model.gguf --prompt "Hello" --max-tokens 100
    python -m weight_stream stats model.gguf
    python -m weight_stream benchmark model.gguf --buffer-mb 64
    python -m weight_stream --help
"""

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Optional

from ..backends.llama_cpp import WeightStreamModel
from ..core.exceptions import WeightStreamError, ModelError


def main():
    parser = argparse.ArgumentParser(
        prog="weight-streaming",
        description="Run LLMs larger than your RAM — speculative weight streaming from NVMe",
        epilog="Example: python -m weight_stream run model.gguf --prompt 'Hello' --max-tokens 100",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--version", action="version",
        version=f"weight-streaming v{_get_version()}",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    
    # ── run ─────────────────────────────────────────────────────────
    run_p = sub.add_parser("run", help="Generate text with weight streaming")
    run_p.add_argument("model", type=str, help="Path to GGUF model file")
    run_p.add_argument("--prompt", "-p", type=str, default="Hello",
                       help="Input prompt text (default: 'Hello')")
    run_p.add_argument("--max-tokens", "-n", type=int, default=128,
                       help="Maximum tokens to generate (default: 128)")
    run_p.add_argument("--buffer-mb", "-b", type=int, default=64,
                       help="Buffer size in MB (default: 64)")
    run_p.add_argument("--temperature", "-t", type=float, default=0.7,
                       help="Sampling temperature 0.0-2.0 (default: 0.7)")
    run_p.add_argument("--verbose", "-v", action="store_true",
                       help="Enable debug logging")
    run_p.add_argument("--json", "-j", action="store_true",
                       help="Output results as JSON (machine-readable)")
    
    # ── stats ────────────────────────────────────────────────────────
    stats_p = sub.add_parser("stats", help="Show model metadata and buffer configuration")
    stats_p.add_argument("model", type=str, help="Path to GGUF model file")
    stats_p.add_argument("--buffer-mb", "-b", type=int, default=64,
                         help="Buffer size in MB for estimation (default: 64)")
    
    # ── benchmark ────────────────────────────────────────────────────
    bench_p = sub.add_parser("benchmark", help="Benchmark generation throughput")
    bench_p.add_argument("model", type=str, help="Path to GGUF model file")
    bench_p.add_argument("--buffer-mb", "-b", type=int, default=64,
                          help="Buffer size in MB (default: 64)")
    bench_p.add_argument("--max-tokens", "-n", type=int, default=256,
                          help="Tokens to generate for measurement (default: 256)")
    bench_p.add_argument("--no-warmup", action="store_true",
                          help="Skip warmup phase (less accurate but faster)")
    bench_p.add_argument("--json", "-j", action="store_true",
                          help="Output results as JSON")
    
    # ── server / serve ────────────────────────────────────────────────
    server_p = sub.add_parser("server", aliases=["serve"], help="Start API server for frontends and IDE integration",
                              epilog="Example: python -m weight_stream server --model model.gguf")
    server_p.add_argument("--host", type=str, default="127.0.0.1",
                          help="Bind address (default: 127.0.0.1)")
    server_p.add_argument("--port", "-p", type=int, default=8765,
                          help="Bind port (default: 8765)")
    server_p.add_argument("--model", "-m", type=str, default=None,
                          help="Auto-load a model on startup (path to GGUF)")
    server_p.add_argument("--model-id", type=str, default="default",
                          help="Model ID for auto-loaded model (default: 'default')")
    server_p.add_argument("--buffer-mb", "-b", type=int, default=64,
                          help="Buffer size in MB (default: 64)")
    server_p.add_argument("--n-ctx", type=int, default=512,
                          help="Context window size (default: 512)")
    server_p.add_argument("--n-threads", type=int, default=None,
                          help="Number of CPU threads (default: half of logical CPU cores)")
    server_p.add_argument("--idle-unload-timeout", type=float, default=None,
                          help="Seconds before unloading an idle model; 0 disables it (default: 0)")
    server_p.add_argument("--auto-tune", action="store_true",
                          help="Auto-tune buffer & thread settings based on hardware profiler")
    server_p.add_argument("--verbose", "-v", action="store_true",
                          help="Enable debug logging")

    # ── auto-tune ─────────────────────────────────────────────────────
    tune_p = sub.add_parser("auto-tune", help="Hardware profiler — recommend optimal streaming config")
    tune_p.add_argument("--model-size-gb", type=float, default=14.0, help="Model size in GB")
    tune_p.add_argument("--json", action="store_true", help="Output raw JSON")

    # ── repack ────────────────────────────────────────────────────────
    repack_p = sub.add_parser("repack", help="Repack model weights for contiguous popularity layout")
    repack_p.add_argument("input", help="Input GGUF model path")
    repack_p.add_argument("output", help="Output repacked model path")
    repack_p.add_argument("--shard-size-mb", type=float, default=4.0, help="Shard size in MB (default: 4.0)")

    # ── inspect ───────────────────────────────────────────────────────
    inspect_p = sub.add_parser("inspect", help="Inspect GGUF model metadata & detect architecture")
    inspect_p.add_argument("model", help="Path to GGUF model file")
    
    # ── ui ────────────────────────────────────────────────────────────
    ui_p = sub.add_parser("ui", help="Launch the Gradio Web UI",
                          epilog="Example: python -m weight_stream ui --server http://localhost:8765")
    ui_p.add_argument("--server", "-s", type=str, default="http://127.0.0.1:8765",
                      help="API server URL (default: http://127.0.0.1:8765)")
    ui_p.add_argument("--share", action="store_true",
                      help="Create a public shareable link (use with caution)")
    
    # ── tui ───────────────────────────────────────────────────────────
    tui_p = sub.add_parser("tui", help="Launch the Textual terminal UI",
                           epilog="Example: python -m weight_stream tui --server http://localhost:8765")
    tui_p.add_argument("--server", "-s", type=str, default="http://127.0.0.1:8765",
                       help="API server URL (default: http://127.0.0.1:8765)")
    
    # ── issues ────────────────────────────────────────────────────────
    issues_p = sub.add_parser("issues", help="Issue tracking (report / list / manage)")
    issues_sub = issues_p.add_subparsers(dest="issues_cmd", required=True)
    
    ir = issues_sub.add_parser("report", help="Report a new issue")
    ir.add_argument("--title", "-t", required=True, help="Issue title")
    ir.add_argument("--desc", "-d", required=True, help="Description")
    ir.add_argument("--severity", "-s", default="medium",
                    choices=["low", "medium", "high", "critical"])
    ir.add_argument("--expected", default="", help="Expected behavior")
    ir.add_argument("--actual", default="", help="Actual behavior")
    
    il = issues_sub.add_parser("list", help="List issues")
    il.add_argument("--status", default=None, help="Filter by status")
    il.add_argument("--severity", default=None, help="Filter by severity")
    
    iss = issues_sub.add_parser("show", help="Show issue detail")
    iss.add_argument("id", help="Issue ID (e.g. ISSUE-001)")
    
    ist = issues_sub.add_parser("set-status", help="Update issue status (maintainer)")
    ist.add_argument("id", help="Issue ID")
    ist.add_argument("status", help="New status")
    ist.add_argument("--root-cause", default=None)
    ist.add_argument("--fix", default=None, dest="fix_summary")
    ist.add_argument("--commit", default=None)
    ist.add_argument("--verify-steps", default=None)
    ist.add_argument("--note", default=None)
    
    iv = issues_sub.add_parser("verify", help="Verify a fix")
    iv.add_argument("id", help="Issue ID")
    iv.add_argument("--fail", action="store_true", help="Mark as still broken")
    iv.add_argument("--note", default="")
    
    ie = issues_sub.add_parser("export", help="Export issues summary markdown")
    
    args = parser.parse_args()
    
    # Route command
    try:
        if args.command in ("server", "serve"):
            cmd_server(args)
        elif args.command == "auto-tune":
            cmd_auto_tune(args)
        elif args.command == "repack":
            cmd_repack(args)
        elif args.command == "inspect":
            cmd_inspect(args)
        elif args.command == "run":
            cmd_run(args)
        elif args.command == "stats":
            cmd_stats(args)
        elif args.command == "benchmark":
            cmd_benchmark(args)
        elif args.command == "ui":
            cmd_ui(args)
        elif args.command == "tui":
            cmd_tui(args)
        elif args.command == "issues":
            cmd_issues(args)
    except WeightStreamError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nInterrupted by user", file=sys.stderr)
        sys.exit(130)


def _get_version() -> str:
    """Return package version without importing __init__ conflicts."""
    try:
        from weight_stream import __version__
        return __version__
    except ImportError:
        return "unknown"


def _setup_logging(verbose: bool = False):
    """Configure logging with clean format."""
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(levelname)s: %(message)s",
        force=True,
    )


def _print_stats_table(stats: dict):
    """Print formatted statistics table."""
    buf = stats.get("buffer") or {}
    pref = stats.get("prefetcher") or {}
    gen = stats.get("generation", {})
    page = stats.get("page_cache") or {}

    if stats.get("buffer") is None:
        # LlamaServerBackend (GPU): weights are managed inside llama-server,
        # so there is no shard-level streaming buffer to report.
        print(" " * 4 + "Buffer: n/a (backend manages weights internally)")
        print()
    else:
        print(" " * 4 + "Buffer Statistics:")
        print(f"{'':>6}Capacity:    {buf.get('capacity_shards', '?')} shards ({buf.get('capacity_mb', '?')} MB)")
        print(f"{'':>6}Hot shards:  {buf.get('hot_shards', '?')} / {buf.get('capacity_shards', '?')}")
        print(f"{'':>6}Hit rate:    {buf.get('hit_rate', 0):.1%}")
        print(f"{'':>6}Hits:        {buf.get('hits', 0)}")
        print(f"{'':>6}Misses:      {buf.get('misses', 0)}")
        print(f"{'':>6}Evictions:   {buf.get('evictions', 0)}")
        print(f"{'':>6}Prefetches:  {buf.get('prefetches', 0)}")
        print()
    
    if pref:
        print(" " * 4 + "Prefetcher:")
        print(f"{'':>6}Queued:      {pref.get('queued', 0)}")
        print(f"{'':>6}Prefetched:  {pref.get('prefetched', 0)}")
        print()
    
    if gen:
        print(" " * 4 + "Generation:")
        print(f"{'':>6}Tokens:      {gen.get('token_count', 0)}")
        print(f"{'':>6}Time:        {gen.get('elapsed', 0):.2f}s")
        print(f"{'':>6}Speed:       {gen.get('tokens_per_sec', 0):.2f} tok/s")
        print()
    
    if page:
        print(" " * 4 + "Page Cache (OS mmap):")
        ratio = page.get("resident_ratio", 0)
        print(f"{'':>6}Resident:    {ratio:.1%} in physical RAM")
        print(f"{'':>6}Size:        {page.get('resident_gb', 0):.1f} GB / {page.get('total_gb', 0):.1f} GB")
        print()


def cmd_run(args):
    """Generate text with weight streaming."""
    _setup_logging(args.verbose)
    
    # Validate model file exists early
    model_path = Path(args.model)
    if not model_path.exists():
        print(f"Error: model file not found: {args.model}", file=sys.stderr)
        sys.exit(1)
    
    # Validate parameters
    if args.buffer_mb < 1:
        print("Error: --buffer-mb must be >= 1", file=sys.stderr)
        sys.exit(1)
    if args.max_tokens < 1:
        print("Error: --max-tokens must be >= 1", file=sys.stderr)
        sys.exit(1)
    if not 0 <= args.temperature <= 2:
        print("Error: --temperature must be between 0.0 and 2.0", file=sys.stderr)
        sys.exit(1)
    
    model = WeightStreamModel(
        str(model_path),
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
            # Print generation output
            print("\n" + "=" * 60)
            sys.stdout.buffer.write(output.encode("utf-8", errors="replace"))
            print("\n" + "=" * 60)
            print()
            
            # Print stats
            stats = model.get_stats()
            _print_stats_table(stats)
            
            # Buffer hit rate note (or {} — buffer may be an explicit null on
            # the llama-server GPU backend, which has no shard buffer).
            hit = (stats.get("buffer") or {}).get("hit_rate", 0)
            if hit == 0:
                print(
                    "  Note: Hit rate is 0% because expert routing is opaque\n"
                    "  from Python. The buffer tracks prefetched shards, not\n"
                    "  actual weight access. Hit rate will be meaningful with\n"
                    "  the C++ backend patch.\n"
                )
    
    except ModelError as e:
        print(f"Model error: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        model.close()


def cmd_stats(args):
    """Show model metadata and buffer configuration."""
    path = Path(args.model)
    if not path.exists():
        print(f"Error: file not found: {args.model}", file=sys.stderr)
        sys.exit(1)
    
    file_size = path.stat().st_size
    shard_size = 4 * 1024 * 1024  # 4 MB
    
    print(f"Model: {path.name}")
    print(f"{'':>4}Path:       {path.absolute()}")
    print(f"{'':>4}Size:       {file_size / 1024**3:.2f} GB ({file_size:,} bytes)")
    print(f"{'':>4}Shards:     {(file_size + shard_size - 1) // shard_size:,} (at 4 MB each)")
    print()
    print(f"Buffer: {args.buffer_mb} MB")
    print(f"{'':>4}Hot set:    ~{args.buffer_mb // 4} shards")
    print(f"{'':>4}Mode:       ", end="")
    
    if file_size > 100 * 1024**3:
        print("Streaming required (file >> RAM)")
    elif file_size > args.buffer_mb * 1024**2:
        print("Partial streaming (buffer < file)")
    else:
        print("Fits in buffer (file <= buffer)")
    
    print()
    n_tokens_estimate = int(file_size / 2_000_000)  # ~2 bytes/param for Q2_K
    print(f"  Estimated tokens: ~{n_tokens_estimate:,} in file")
    print(f"  Context window:   default 512 tokens (configurable)")
    print()
    print(f"  Run: python -m weight_stream run \"{path}\" --prompt \"Hello\"")


def cmd_benchmark(args):
    """Run throughput benchmark with optional warmup."""
    _setup_logging(verbose=False)
    
    model_path = Path(args.model)
    if not model_path.exists():
        print(f"Error: file not found: {args.model}", file=sys.stderr)
        sys.exit(1)
    
    # Warmup phase
    if not args.no_warmup:
        print("Warming up (loading model into cache)...", end=" ", flush=True)
        warmup = WeightStreamModel(
            str(model_path),
            buffer_mb=args.buffer_mb,
            verbose=False,
        )
        try:
            warmup.generate("Hello world", max_tokens=5)
        finally:
            warmup.close()
        print("done.")
    
    # Benchmark phase
    print(f"\nBenchmarking: {model_path.name}")
    print(f"{'':>4}Buffer:     {args.buffer_mb} MB")
    print(f"{'':>4}Max tokens: {args.max_tokens}")
    
    model = WeightStreamModel(
        str(model_path),
        buffer_mb=args.buffer_mb,
        verbose=False,
    )
    
    try:
        start_time = time.time()
        output = model.generate(
            "The future of AI is",
            max_tokens=args.max_tokens,
        )
        elapsed = time.time() - start_time
        stats = model.get_stats()
        
        # Estimate tokens generated
        gen_stats = stats.get("generation", {})
        token_count = gen_stats.get("token_count", 0)
        tok_per_sec = token_count / elapsed if elapsed > 0 and token_count > 0 else 0
        
        if args.json:
            result = {
                "model": str(model_path),
                "buffer_mb": args.buffer_mb,
                "max_tokens": args.max_tokens,
                "elapsed_seconds": round(elapsed, 3),
                "tokens_generated": token_count,
                "tokens_per_second": round(tok_per_sec, 2),
                "stats": stats,
            }
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(f"\n{'=' * 60}")
            print(f"Results:")
            print(f"{'':>4}Elapsed:    {elapsed:.2f}s")
            print(f"{'':>4}Tokens:     {token_count}")
            print(f"{'':>4}Speed:      {tok_per_sec:.2f} tok/s")
            print()
            _print_stats_table(stats)
            print(f"{'=' * 60}")
    
    finally:
        model.close()


if __name__ == "__main__":
    main()


def cmd_server(args):
    """Start the weight-streaming API server."""
    import logging
    import os

    if getattr(args, "auto_tune", False):
        from weight_stream.tools.auto_tune import get_system_profile, recommend_config
        profile = get_system_profile()
        tuned = recommend_config(profile)
        print(f"⚡ Auto-Tuned Settings: buffer={tuned['buffer_mb']}MB, threads={tuned['n_threads']}, n_ctx={tuned['n_ctx']}")
        os.environ["WS_BUFFER_MB"] = str(tuned["buffer_mb"])
        os.environ["WS_N_THREADS"] = str(tuned["n_threads"])
        os.environ["WS_N_CTX"] = str(tuned["n_ctx"])
        args.buffer_mb = tuned["buffer_mb"]
        args.n_threads = tuned["n_threads"]
        args.n_ctx = tuned["n_ctx"]

    logging.basicConfig(
        level=logging.DEBUG if getattr(args, "verbose", False) else logging.INFO,
        format="%(levelname)s: %(name)s: %(message)s",
    )
    
    import uvicorn
    
    # Set auto-load env vars if --model specified
    if getattr(args, "model", None):
        os.environ["WS_AUTO_MODEL_PATH"] = args.model
        os.environ["WS_AUTO_MODEL_ID"] = args.model_id
        os.environ["WS_BUFFER_MB"] = str(args.buffer_mb)
        os.environ["WS_N_CTX"] = str(args.n_ctx)
        if args.n_threads:
            os.environ["WS_N_THREADS"] = str(args.n_threads)
    
    print(f"\n  Weight Streaming API Server v0.11.0")
    print(f"  Listening on http://{args.host}:{args.port}")
    print(f"  API docs: http://{args.host}:{args.port}/docs")
    print(f"  Web app:  http://{args.host}:{args.port}/app")
    if getattr(args, "model", None):
        print(f"  Auto-load: {args.model} (id={args.model_id})")
    print(f"  Press Ctrl+C to stop\n")
    
    # Create app, pass directly (not via factory string)
    from weight_stream.server.api_server import create_app
    from weight_stream.server.config import ServerConfig, set_config
    config = ServerConfig(
        host=args.host, port=args.port,
        default_buffer_mb=args.buffer_mb,
        default_n_ctx=args.n_ctx,
        default_n_threads=args.n_threads or max(1, (os.cpu_count() or 4) // 2),
        idle_unload_timeout=(
            args.idle_unload_timeout
            if args.idle_unload_timeout is not None
            else float(os.getenv("WS_IDLE_TIMEOUT", "0"))
        ),
    )
    set_config(config)
    app, manager = create_app(config)
    
    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        log_level="debug" if getattr(args, "verbose", False) else "info",
    )


def cmd_auto_tune(args):
    """Run hardware profiler and recommend optimal settings."""
    from weight_stream.tools.auto_tune import get_system_profile, recommend_config, print_recommendation
    profile = get_system_profile()
    config = recommend_config(profile, model_size_gb=args.model_size_gb)
    if args.json:
        print(json.dumps(config, indent=2))
    else:
        print_recommendation(config)


def cmd_repack(args):
    """Repack GGUF model weights for contiguous popularity layout."""
    from weight_stream.tools.shard_repacker import ShardRepacker
    repacker = ShardRepacker(args.input, args.output, shard_size_mb=args.shard_size_mb)
    res = repacker.repack()
    print("Repack Completed:", res)


def cmd_inspect(args):
    """Inspect GGUF model metadata & detect architecture."""
    from weight_stream.gguf.parser import GGUFParser
    with GGUFParser(args.model) as parser_obj:
        arch_info = parser_obj.detect_architecture()
        print("\n🔍 GGUF Architecture Specs:")
        print(json.dumps(arch_info, indent=2))


def cmd_ui(args):
    """Launch the Gradio Web UI."""
    print(f"  Starting Gradio Web UI...")
    print(f"  API Server: {args.server}")
    print(f"  Make sure the API server is running:")
    print(f"    python -m weight_stream server --model model.gguf\n")
    
    from weight_stream.ui.gradio_app import launch
    launch(server_url=args.server, share=args.share)


def cmd_tui(args):
    """Launch the Textual terminal UI."""
    print(f"  Starting Textual TUI...")
    print(f"  API Server: {args.server}")
    print(f"  Make sure the API server is running:")
    print(f"    python -m weight_stream server --model model.gguf\n")
    
    from weight_stream.tui.app import WeightStreamTUI
    app = WeightStreamTUI(server_url=args.server)
    app.run()


def cmd_issues(args):
    """Issue tracking CLI."""
    from weight_stream.issues import (
        IssueCreate,
        IssueService,
        IssueUpdate,
        IssueVerify,
        Severity,
        IssueStatus,
        collect_debug_context,
    )
    
    svc = IssueService()
    cmd = args.issues_cmd
    
    if cmd == "report":
        issue = svc.create(IssueCreate(
            title=args.title,
            description=args.desc,
            severity=Severity(args.severity),
            expected=args.expected,
            actual=args.actual,
            context=collect_debug_context(),
        ))
        print(f"Created {issue.id}: {issue.title}")
        print(f"  Status: {issue.status.value}")
        print(f"  Saved: data/issues/{issue.id}.json")
    
    elif cmd == "list":
        issues = svc.list(status=args.status, severity=args.severity)
        if not issues:
            print("No issues found.")
            return
        print(f"{'ID':<12} {'Status':<16} {'Sev':<10} Title")
        print("-" * 70)
        for i in issues:
            print(f"{i.id:<12} {i.status.value:<16} {i.severity.value:<10} {i.title[:40]}")
    
    elif cmd == "show":
        issue = svc.get(args.id)
        if not issue:
            print(f"Issue {args.id} not found")
            sys.exit(1)
        print(f"{issue.id}: {issue.title}")
        print(f"  Status:   {issue.status.value}")
        print(f"  Severity: {issue.severity.value}")
        print(f"  Created:  {issue.created_at} by {issue.created_by}")
        print(f"  Updated:  {issue.updated_at}")
        print(f"\nDescription:\n  {issue.description}")
        if issue.root_cause:
            print(f"\nRoot cause:\n  {issue.root_cause}")
        if issue.fix_summary:
            print(f"\nFix:\n  {issue.fix_summary}")
        if issue.verify_steps:
            print(f"\nVerify:\n  {issue.verify_steps}")
        if issue.timeline:
            print("\nTimeline:")
            for ev in issue.timeline:
                note = f" — {ev.note}" if ev.note else ""
                print(f"  {ev.at}  {ev.event}  ({ev.by}){note}")
    
    elif cmd == "set-status":
        try:
            status = IssueStatus(args.status)
        except ValueError:
            print(f"Invalid status: {args.status}")
            print(f"Valid: {[s.value for s in IssueStatus]}")
            sys.exit(1)
        try:
            issue = svc.update(args.id, IssueUpdate(
                status=status,
                root_cause=args.root_cause,
                fix_summary=args.fix_summary,
                commit=args.commit,
                verify_steps=args.verify_steps,
                note=args.note,
            ))
            print(f"Updated {issue.id} → {issue.status.value}")
        except ValueError as e:
            print(f"Error: {e}")
            sys.exit(1)
    
    elif cmd == "verify":
        try:
            issue = svc.verify(args.id, IssueVerify(
                verified=not args.fail,
                note=args.note,
            ))
            print(f"{issue.id} → {issue.status.value}")
        except ValueError as e:
            print(f"Error: {e}")
            sys.exit(1)
    
    elif cmd == "export":
        md = svc.export_markdown()
        print(md)
        print(f"\n(Saved to data/issues/ISSUES_SUMMARY.md)")
