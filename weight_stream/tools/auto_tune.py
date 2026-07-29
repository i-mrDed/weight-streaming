"""Auto-tuning hardware profiler for Weight-Streaming.

Inspects the user's system (RAM, CPU, NVMe bandwidth) and recommends
optimal configuration parameters (buffer_mb, eviction_policy, prefetch_depth,
n_threads) automatically.

Usage:
    python -m weight_stream.tools.auto_tune
    # or via CLI flag:
    python -m weight_stream serve --auto-tune
"""

import os
import sys
import platform
import json
import shutil
from typing import Dict, Any, Optional
from pathlib import Path


def get_system_profile() -> Dict[str, Any]:
    """Gather hardware specifications of the current system."""
    import multiprocessing

    profile: Dict[str, Any] = {
        "platform": platform.system(),
        "arch": platform.machine(),
        "cpu_model": platform.processor() or "unknown",
        "cpu_threads": multiprocessing.cpu_count() or 4,
        "ram_total_gb": 0.0,
        "nvme_estimated_bandwidth_gbps": 0.0,
        "disk_free_gb": 0.0,
    }

    # RAM detection
    try:
        if sys.platform == "win32":
            import ctypes
            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]
            ms = MEMORYSTATUSEX()
            ms.dwLength = ctypes.sizeof(ms)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(ms))
            profile["ram_total_gb"] = round(ms.ullTotalPhys / (1024 ** 3), 1)
            profile["ram_available_gb"] = round(ms.ullAvailPhys / (1024 ** 3), 1)
        else:
            with open("/proc/meminfo") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        kb = int(line.split()[1])
                        profile["ram_total_gb"] = round(kb / (1024 ** 2), 1)
                    elif line.startswith("MemAvailable:"):
                        kb = int(line.split()[1])
                        profile["ram_available_gb"] = round(kb / (1024 ** 2), 1)
    except Exception:
        pass

    # Disk free space
    try:
        usage = shutil.disk_usage(os.getcwd())
        profile["disk_free_gb"] = round(usage.free / (1024 ** 3), 1)
    except Exception:
        pass

    # Estimate NVMe bandwidth (heuristic based on platform)
    if profile["platform"] == "Windows":
        profile["nvme_estimated_bandwidth_gbps"] = 3.5  # Gen4 typical
    elif profile["platform"] == "Linux":
        # Try to detect NVMe gen from sysfs
        try:
            for dev in Path("/sys/class/nvme/").iterdir():
                with open(dev / "device" / "max_link_speed") as f:
                    speed = f.read().strip()
                    if "16.0 GT/s" in speed:
                        profile["nvme_estimated_bandwidth_gbps"] = 7.0  # Gen4
                    elif "32.0 GT/s" in speed:
                        profile["nvme_estimated_bandwidth_gbps"] = 14.0  # Gen5
                    else:
                        profile["nvme_estimated_bandwidth_gbps"] = 3.5
                break
        except Exception:
            profile["nvme_estimated_bandwidth_gbps"] = 3.5
    else:
        profile["nvme_estimated_bandwidth_gbps"] = 3.5

    return profile


def recommend_config(profile: Dict[str, Any], model_size_gb: float = 14.0) -> Dict[str, Any]:
    """Compute optimal Weight-Streaming configuration based on hardware profile."""
    ram_gb = profile.get("ram_total_gb", 16.0)
    ram_available_gb = profile.get("ram_available_gb", ram_gb * 0.6)
    cpu_threads = profile.get("cpu_threads", 4)
    nvme_bw = profile.get("nvme_estimated_bandwidth_gbps", 3.5)

    # Buffer size: use 50-70% of available RAM, capped by model size
    usable_ram_mb = int(ram_available_gb * 1024 * 0.6)
    model_size_mb = int(model_size_gb * 1024)
    buffer_mb = min(usable_ram_mb, model_size_mb)
    buffer_mb = max(buffer_mb, 128)  # Minimum 128 MB

    # Buffer residency ratio target
    residency_ratio = round(buffer_mb / model_size_mb, 2) if model_size_mb > 0 else 0.5

    # Eviction policy
    if residency_ratio >= 0.8:
        eviction_policy = "lru"           # Most of model fits → simple LRU
    elif residency_ratio >= 0.3:
        eviction_policy = "priority-lru"  # Partial fit → prioritize attention layers
    else:
        eviction_policy = "lfu"           # Very low residency → frequency-based

    # Prefetch depth based on NVMe bandwidth
    if nvme_bw >= 7.0:
        prefetch_depth = 8   # Gen4/5 NVMe → aggressive prefetching
    elif nvme_bw >= 3.0:
        prefetch_depth = 4   # Standard NVMe
    else:
        prefetch_depth = 2   # SATA SSD / slow storage

    # Thread count for compute
    n_threads = max(1, cpu_threads - 2)  # Reserve 2 threads for I/O + system

    # Context window recommendation
    if ram_gb >= 32:
        n_ctx = 4096
    elif ram_gb >= 16:
        n_ctx = 2048
    else:
        n_ctx = 1024

    return {
        "buffer_mb": buffer_mb,
        "eviction_policy": eviction_policy,
        "prefetch_depth": prefetch_depth,
        "n_threads": n_threads,
        "n_ctx": n_ctx,
        "residency_ratio": residency_ratio,
        "model_size_gb": model_size_gb,
        "hardware_profile": profile,
    }


def print_recommendation(config: Dict[str, Any]):
    """Pretty-print the auto-tuned configuration."""
    profile = config.get("hardware_profile", {})
    print()
    print("╔═══════════════════════════════════════════════════════════╗")
    print("║           ⚡ Weight-Streaming Auto-Tune Report            ║")
    print("╠═══════════════════════════════════════════════════════════╣")
    print(f"║  Platform:         {profile.get('platform', '?'):>37s} ║")
    print(f"║  CPU:              {profile.get('cpu_model', '?')[:37]:>37s} ║")
    print(f"║  CPU Threads:      {profile.get('cpu_threads', '?'):>37} ║")
    print(f"║  RAM Total:        {profile.get('ram_total_gb', 0):>33.1f} GB ║")
    print(f"║  NVMe Bandwidth:   {profile.get('nvme_estimated_bandwidth_gbps', 0):>31.1f} GB/s ║")
    print("╠═══════════════════════════════════════════════════════════╣")
    print(f"║  buffer_mb:        {config['buffer_mb']:>37} ║")
    print(f"║  eviction_policy:  {config['eviction_policy']:>37s} ║")
    print(f"║  prefetch_depth:   {config['prefetch_depth']:>37} ║")
    print(f"║  n_threads:        {config['n_threads']:>37} ║")
    print(f"║  n_ctx:            {config['n_ctx']:>37} ║")
    print(f"║  residency_ratio:  {config['residency_ratio']:>35.0%}   ║")
    print("╚═══════════════════════════════════════════════════════════╝")
    print()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Weight-Streaming Auto-Tune")
    parser.add_argument("--model-size-gb", type=float, default=14.0, help="Model size in GB")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    profile = get_system_profile()
    config = recommend_config(profile, model_size_gb=args.model_size_gb)

    if args.json:
        print(json.dumps(config, indent=2))
    else:
        print_recommendation(config)
