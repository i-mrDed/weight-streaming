"""Resume-capable single-file downloader (HF resolve URLs, Range-append).

Recovers from interrupted plain-urllib downloads (no .part): if the target
file exists but is shorter than EXPECTED, this re-opens the HTTP stream
with `Range: bytes=<have>-`, appends, and verifies the final size exactly
(project lesson: task "done" without a Content-Length check is how we got
a 3.8 GB file reported as 10.05 GB — this script refuses to exit until the
byte count matches).

Usage:
    python scripts/resume_download.py URL TARGET EXPECTED_BYTES

Run it in background (nohup / separate terminal); it retries on network
errors and exits 0 only when the file size == EXPECTED_BYTES.
"""
import os
import sys
import time
import urllib.request

CHUNK = 1 << 20  # 1 MiB


def main() -> int:
    url, target, expected = sys.argv[1], sys.argv[2], int(sys.argv[3])
    have = os.path.getsize(target) if os.path.exists(target) else 0
    if have >= expected:
        print(f"already complete: {have} bytes (nothing to do)")
        return 0
    print(f"resuming {target}: {have}/{expected} bytes "
          f"({have / expected * 100:.1f}%)", flush=True)

    attempts = 0
    while have < expected:
        attempts += 1
        req = urllib.request.Request(url, method="GET")
        if have:
            req.add_header("Range", f"bytes={have}-")
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                with open(target, "ab") as f:
                    while True:
                        chunk = resp.read(CHUNK)
                        if not chunk:
                            break
                        f.write(chunk)
                        have = os.path.getsize(target)
            if have < expected:
                raise ConnectionError(
                    f"stream ended early at {have}/{expected}")
        except Exception as e:
            print(f"  attempt {attempts} failed: {e} — retrying in 5s",
                  flush=True)
            time.sleep(5)
            continue
        print(f"  after attempt {attempts}: {have}/{expected} bytes "
              f"({have / expected * 100:.1f}%)", flush=True)

    # Final honest check — refuse success on a size mismatch.
    if os.path.getsize(target) != expected:
        print(f"FINAL SIZE MISMATCH: {os.path.getsize(target)} != {expected}",
              file=sys.stderr)
        return 2
    print(f"COMPLETE: {target} ({expected} bytes)", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
