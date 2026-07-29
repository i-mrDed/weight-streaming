"""Spike: measure OS-level page-fault demand during real generation.

Why: ``StreamingBuffer.total_accesses`` stays 0 during real inference —
llama.cpp reads the GGUF through its own internal mmap and never reports
accesses back to our buffer tracker (see ADR-003 addendum 2026-07-29).
This spike tests whether OS page-fault counters give an honest
"paging demand" telemetry channel WITHOUT touching llama.cpp:

  - Windows: GetProcessMemoryInfo().PageFaultCount (cumulative hard+soft)
  - Linux:   resource.getrusage(RUSAGE_SELF).ru_minflt

Run:  python scripts/spike_page_faults.py
Needs: research/models/Qwen1.5-MoE-A2.7B_Q2_k.gguf (like verify_items_45.py)
"""
import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

MODEL_PATH = "research/models/Qwen1.5-MoE-A2.7B_Q2_k.gguf"
PAGE_SIZE = 4096
PROMPT = [{"role": "user",
           "content": "Write a detailed 300-word essay about the history of printing presses."}]
MAX_TOKENS = 128


def fault_count() -> int:
    """Cumulative page-fault count for this process (cross-platform)."""
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        pmc = PROCESS_MEMORY_COUNTERS()
        pmc.cb = ctypes.sizeof(pmc)
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        psapi.GetProcessMemoryInfo.argtypes = [
            ctypes.wintypes.HANDLE,
            ctypes.POINTER(PROCESS_MEMORY_COUNTERS),
            ctypes.wintypes.DWORD,
        ]
        psapi.GetProcessMemoryInfo.restype = ctypes.wintypes.BOOL
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.GetCurrentProcess.restype = ctypes.wintypes.HANDLE
        ok = psapi.GetProcessMemoryInfo(
            k32.GetCurrentProcess(), ctypes.byref(pmc), pmc.cb)
        if not ok:
            raise OSError(f"GetProcessMemoryInfo failed: {ctypes.get_last_error()}")
        return int(pmc.PageFaultCount)
    else:
        import resource
        return int(resource.getrusage(resource.RUSAGE_SELF).ru_minflt)


def residency(model) -> float:
    """OS page residency ratio of the model mmap, or -1 if unavailable."""
    mon = getattr(model, "_page_monitor", None)
    if mon is None:
        return -1.0
    mon.sample_resident_pages()
    return mon.get_resident_ratio()


def generate(model, label: str) -> dict:
    """Run one stream_chat generation and measure paging demand."""
    res_before = residency(model)
    f0, t0, n = fault_count(), time.perf_counter(), 0
    for _chunk in model.stream_chat(PROMPT, max_tokens=MAX_TOKENS, temperature=0.0):
        n += 1
    dt = time.perf_counter() - t0
    faults = fault_count() - f0
    res_after = residency(model)
    stats = model.get_stats().get("generation", {})
    row = {
        "label": label,
        "tokens": n,
        "seconds": round(dt, 2),
        "tok_s": round(n / dt, 2) if dt > 0 else 0,
        "faults": faults,
        "faults_per_token": round(faults / n, 1) if n else 0,
        "fault_bytes_per_token_MB": round(faults * PAGE_SIZE / n / 1e6, 2) if n else 0,
        "residency_before": round(res_before, 4),
        "residency_after": round(res_after, 4),
        "wrapper_tok_s": round(stats.get("tokens_per_sec", 0.0), 2),
        "buffer_total_accesses": model.buffer.get_stats()["total_accesses"],
    }
    print(f"[{label}] {row['tokens']} tok in {row['seconds']} s "
          f"({row['tok_s']} tok/s) | faults={faults:,} "
          f"({row['faults_per_token']}/tok ≈ {row['fault_bytes_per_token_MB']} MB/tok) "
          f"| residency {res_before:.1%} -> {res_after:.1%}")
    return row


def main():
    if not os.path.isfile(MODEL_PATH):
        print(f"FATAL: model not found: {MODEL_PATH}")
        return 1

    print(f"[spike] loading {MODEL_PATH}")
    from weight_stream.backends.llama_cpp import WeightStreamModel
    t0 = time.perf_counter()
    model = WeightStreamModel(
        MODEL_PATH, buffer_mb=64, n_ctx=512,
        n_threads=max(1, (os.cpu_count() or 4) // 2),
    )
    print(f"[spike] loaded in {time.perf_counter() - t0:.1f} s "
          f"(platform={sys.platform})")

    # Idle baseline: process noise with no generation
    f0 = fault_count()
    time.sleep(3.0)
    idle_faults = fault_count() - f0
    print(f"[baseline] idle faults over 3 s: {idle_faults:,}")

    rows = [
        generate(model, "run1-cold"),
        generate(model, "run2-warm"),
    ]

    print("\n=== summary ===")
    print(f"{'run':<12}{'tok':>5}{'tok/s':>8}{'faults':>12}{'f/tok':>10}"
          f"{'MB/tok':>9}{'res%':>14}{'buf.access':>12}")
    for r in rows:
        print(f"{r['label']:<12}{r['tokens']:>5}{r['tok_s']:>8}"
              f"{r['faults']:>12,}{r['faults_per_token']:>10}"
              f"{r['fault_bytes_per_token_MB']:>9}"
              f"{r['residency_before']*100:>6.1f}->{r['residency_after']*100:<6.1f}"
              f"{r['buffer_total_accesses']:>12}")

    warm = rows[-1]
    if warm["faults_per_token"] < 50:
        verdict = ("WARM-SET CONFIRMED: steady-state generation faults almost "
                   "nothing — the OS page cache's own LRU already holds the "
                   "working set. Paging-demand telemetry is viable and cheap.")
    else:
        verdict = ("ACTIVE PAGING: warm generation still faults heavily — "
                   "working set exceeds what the OS keeps resident; prefetch "
                   "hints may have real value.")
    print(f"\n[verdict] {verdict}")

    # Save raw results next to the other verification artifacts
    import json
    out = {"model": MODEL_PATH, "idle_faults_3s": idle_faults,
           "runs": rows, "verdict": verdict}
    os.makedirs("docs/verification", exist_ok=True)
    out_path = "docs/verification/spike_page_faults_2026-07-30.json"
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2)
    print(f"\n[spike] raw results -> {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
