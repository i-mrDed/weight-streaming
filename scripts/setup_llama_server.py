"""One-command setup: find or download a llama-server binary (llama.cpp).

This lets you run weight-streaming on a NEW machine WITHOUT installing
Jan. The server code finds the binary in this order (llama_server.py):
  1) $WS_LLAMA_SERVER (explicit path)
  2) Jan's bundled backends (%APPDATA%/Jan/...)
  3) PATH (shutil.which("llama-server"))

This script automates that: it locates an existing binary (steps 1-3),
or downloads a prebuilt llama.cpp release matching your platform/GPU,
then prints the exact command to export WS_LLAMA_SERVER (or writes a
.env file).

Usage:
    python scripts/setup_llama_server.py            # find existing, else prompt to download
    python scripts/setup_llama_server.py --check     # just report what's available (no writes)
    python scripts/setup_llama_server.py --download  # force download even if one exists
    python scripts/setup_llama_server.py --backend cuda   # cuda | vulkan | metal | cpu
    python scripts/setup_llama_server.py --write-env # write .env (WS_LLAMA_SERVER=...)

Prereq: Python >= 3.11. Downloads need internet; the binary lands in
./.llama/ by default (add to .gitignore).
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

# console-safe UTF-8 (Windows cp874 console can't print emoji/Thai)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

LLAMA_CPP_REPO = "ggml-org/llama.cpp"
DEFAULT_DEST = Path(".llama")
GITHUB_API = "https://api.github.com/repos/ggml-org/llama.cpp/releases/latest"


def log(msg: str) -> None:
    print(msg, flush=True)


def find_existing() -> list[Path]:
    """Return candidate llama-server binaries (env -> Jan -> PATH)."""
    found: list[Path] = []
    env = os.environ.get("WS_LLAMA_SERVER")
    if env and Path(env).is_file():
        found.append(Path(env))
    jan = Path(os.environ.get("APPDATA", "")) / "Jan" / "data" / "llamacpp" / "backends"
    if jan.is_dir():
        for p in jan.rglob("llama-server*"):
            if p.is_file() and (p.suffix in ("", ".exe")):
                found.append(p)
    which = shutil.which("llama-server")
    if which:
        found.append(Path(which))
    # dedupe by resolved path
    seen, uniq = set(), []
    for p in found:
        r = str(p.resolve())
        if r not in seen:
            seen.add(r)
            uniq.append(p)
    return uniq


def detect_gpu_backend() -> str:
    """Best-guess llama.cpp backend for this machine."""
    if platform.system() == "Darwin":
        return "metal"
    # NVIDIA via nvidia-smi
    if shutil.which("nvidia-smi"):
        try:
            r = subprocess.run(["nvidia-smi", "-L"], capture_output=True,
                               text=True, timeout=10)
            if r.returncode == 0 and r.stdout.strip():
                return "cuda"
        except Exception:
            pass
    # AMD/Intel GPU present? (vulkan is the portable fallback)
    if shutil.which("vulkaninfo") or (platform.system() == "Windows" and
                                      Path("C:/Windows/System32/vulkan-1.dll").exists()):
        return "vulkan"
    return "cpu"


def llama_asset_name(backend: str) -> str:
    """llama.cpp release asset naming (2026 era)."""
    sys_name = platform.system().lower()          # windows / linux / darwin
    arch = platform.machine().lower()
    if sys_name == "windows":
        return f"llama-*-bin-win-{backend}-x64.zip"
    if sys_name == "darwin":
        return f"llama-*-bin-macos-{backend}-{'arm64' if arch in ('arm64','aarch64') else 'x64'}.zip"
    return f"llama-*-bin-ubuntu-{backend}-{arch}.tar.gz"


def fetch_latest_release() -> dict:
    req = urllib.request.Request(GITHUB_API, headers={"User-Agent": "weight-streaming-setup"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def pick_asset(release: dict, backend: str) -> tuple[str, str] | None:
    """Return (asset_name, browser_download_url) matching backend.

    Real llama.cpp asset names embed the build tag and (for CUDA) the
    toolkit version, e.g.:
      llama-b10375-bin-win-cuda-12.4-x64.zip
      llama-b10375-bin-win-cuda-13.3-x64.zip
      llama-b10375-bin-win-vulkan-x64.zip
      llama-b10375-bin-win-cpu-x64.zip
    So we match on tokens, preferring the newest toolkit when multiple
    CUDA assets exist.
    """
    sys_name = platform.system().lower()
    arch = platform.machine().lower()
    arch_tok = "arm64" if arch in ("arm64", "aarch64") else "x64"
    sys_tok = "win" if sys_name == "windows" else (
        "macos" if sys_name == "darwin" else "ubuntu")
    candidates: list[tuple[str, str]] = []
    for a in release.get("assets", []):
        name: str = a["name"]
        if not name.startswith("llama-"):
            continue  # skip cudart-*, etc.
        # strip the .zip/.tar.gz suffix so arch token compares clean
        core = name.rsplit(".", 1)[0]
        toks = core.split("-")
        # e.g. ['llama','b10375','bin','win','cuda','12.4','x64']
        if "bin" not in toks or sys_tok not in toks or arch_tok not in toks:
            continue
        if backend == "cpu" and "cpu" in toks:
            candidates.append((name, a["browser_download_url"]))
        elif backend == "vulkan" and "vulkan" in toks:
            candidates.append((name, a["browser_download_url"]))
        elif backend == "metal" and "metal" in toks:
            candidates.append((name, a["browser_download_url"]))
        elif backend == "cuda" and "cuda" in toks:
            candidates.append((name, a["browser_download_url"]))
    if not candidates:
        return None
    # prefer the one with the newest toolkit version (cuda 13.x > 12.x)
    def sort_key(item: tuple[str, str]) -> tuple[int, str]:
        name = item[0]
        toks = name.split("-")
        # find the token right after 'cuda' (e.g. '12.4', '13.3')
        try:
            idx = toks.index("cuda")
            ver = toks[idx + 1] if idx + 1 < len(toks) else "0"
            major = int(ver.split(".")[0]) if ver and ver[0].isdigit() else 0
            return (major, ver)
        except (ValueError, IndexError):
            return (0, name)
    candidates.sort(key=sort_key, reverse=True)
    return candidates[0]


def download_and_extract(url: str, dest: Path) -> Path | None:
    """Download zip/tar.gz asset and return path to llama-server binary."""
    dest.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.gettempdir()) / url.rsplit("/", 1)[-1]
    log(f"  downloading {url.split('/')[-1]} ...")
    urllib.request.urlretrieve(url, tmp)  # noqa: S310 — pinned to llama.cpp releases
    log(f"  extracting -> {dest}")
    if tmp.suffix == ".zip":
        with zipfile.ZipFile(tmp) as z:
            z.extractall(dest)
    else:
        import tarfile
        with tarfile.open(tmp) as t:
            t.extractall(dest)
    # find llama-server inside
    for p in dest.rglob("llama-server*"):
        if p.is_file() and p.suffix in ("", ".exe"):
            return p
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="report only, no writes")
    ap.add_argument("--download", action="store_true", help="force download")
    ap.add_argument("--backend", choices=["cuda", "vulkan", "metal", "cpu"], default=None)
    ap.add_argument("--write-env", action="store_true",
                    help="write .env with WS_LLAMA_SERVER=...")
    ap.add_argument("--dest", default=str(DEFAULT_DEST), help="download dir (default .llama)")
    args = ap.parse_args()

    log(f"== llama-server setup ==  platform={platform.system()} "
        f"arch={platform.machine()}")

    existing = find_existing()
    if existing and not args.download:
        log(f"✅ found existing llama-server: {existing[0]}")
        log(f"   candidates: {[str(p) for p in existing]}")
        if args.check:
            return 0
        log("   (no download needed)")
        log(f"   -> export WS_LLAMA_SERVER={existing[0]}")
        return 0

    if args.check:
        log("--check: no local llama-server found; would download "
            f"({llama_asset_name(args.backend or detect_gpu_backend())})")
        return 1

    backend = args.backend or detect_gpu_backend()
    log(f"backend detected/selected: {backend}")
    log("fetching latest llama.cpp release ...")
    release = fetch_latest_release()
    tag = release.get("tag_name", "?")
    log(f"  latest release: {tag}")
    asset = pick_asset(release, backend)
    if not asset:
        log(f"❌ no asset for backend={backend} in {tag}")
        log("   available: " + ", ".join(a["name"] for a in release.get("assets", [])[:10]))
        return 1
    name, url = asset
    log(f"  asset: {name}")
    dest = Path(args.dest)
    binary = download_and_extract(url, dest)
    if not binary:
        log("❌ extracted, but llama-server binary not found")
        return 1
    log(f"✅ installed: {binary}")

    if args.write_env:
        env_path = Path(".env")
        lines = []
        if env_path.exists():
            lines = [l for l in env_path.read_text(encoding="utf-8").splitlines()
                     if not l.startswith("WS_LLAMA_SERVER")]
        lines.append(f"WS_LLAMA_SERVER={binary}")
        env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        log(f"✅ wrote {env_path} (WS_LLAMA_SERVER={binary})")
    else:
        log("")
        log("Next step (Windows PowerShell):")
        log(f'  $env:WS_LLAMA_SERVER = "{binary}"')
        log("  weight-streaming server")
        log("")
        log("Or persist it:  python scripts/setup_llama_server.py --write-env")
    return 0


if __name__ == "__main__":
    sys.exit(main())