"""Determinism probe: Thai tonal classification, N runs per quant.

Asks ONLY the tonal question (minimal pairs) repeatedly to see whether
IQ1_M's failure is deterministic (same error every run) or random.

Usage:
    WS_TEST_MODEL="C:/.../IQ1_M.gguf" WS_TEST_MODEL_ID="qwen36a3b_iq1m" \
        WS_QUANT_TAG="IQ1_M" WS_RUNS=3 python scripts/probe_tonal_determinism.py

Writes scripts/.tonal_probe_out.json; exits 0 always (analysis is
human-judged). WS_SKIP_GATE=1 when chained (resident model legit).
"""
import json
import os
import re
import subprocess
import sys
import time
import urllib.request

PORT = os.environ.get("WS_PORT", "8765")
BASE = f"http://127.0.0.1:{PORT}"
MODEL = os.environ.get("WS_TEST_MODEL")
MODEL_ID = os.environ.get("WS_TEST_MODEL_ID", "tonalprobe")
QUANT_TAG = os.environ.get("WS_QUANT_TAG", "unknown")
RUNS = int(os.environ.get("WS_RUNS", "3"))
MAX_TOKENS = int(os.environ.get("WS_MAX_TOKENS", "1024"))
OUT = os.path.join(os.path.dirname(__file__), ".tonal_probe_out.json")

# Minimal pairs: same consonant class (ข = high class), differing only in
# tone mark → forces real tonal discrimination. Correct answers:
#   ข้าว (ไม้โท) = เสียงโท   ข่าว (ไม้เอก) = เสียงเอก   เข้า (ไม้เอก) = เสียงเอก
#   ค้าว (ไม้โท) = เสียงโท   ค่าว (ไม้เอก) = เสียงเอก   เข่า (ไม้เอก) = เสียงเอก
QUESTION = (
    "จงระบุเสียงวรรณยุกต์ (สามัญ/เอก/โท/ตรี/จัตวา) ของคำเหล่านี้ "
    "ทีละคำ: ข้าว, ข่าว, เข้า, ค้าว, ค่าว, เข่า "
    "ตอบเป็นรายการสั้นๆ ในรูปแบบ 'ข้าว = เสียง...' สำหรับทุกคำ"
)


def req(method, path, body=None, timeout=600):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(
        f"{BASE}{path}", data=data, method=method,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(r, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def ask():
    body = {
        "model": MODEL_ID,
        "messages": [{"role": "user", "content": QUESTION}],
        "max_tokens": MAX_TOKENS,
        "temperature": 0.0,
        "top_p": 1.0,
        "stream": False,
        "reasoning_mode": "off",
    }
    r = req("POST", "/v1/chat/completions", body)
    return (r["choices"][0]["message"].get("content") or "")


def tok_s():
    st = req("GET", "/v1/stats", timeout=10)
    gen = (st.get("models") or {}).get(MODEL_ID, {}).get("generation") or {}
    return gen.get("tokens_per_sec") or gen.get("tok_s")


def main():
    if not MODEL:
        raise SystemExit("WS_TEST_MODEL is required")
    if os.environ.get("WS_SKIP_GATE") != "1":
        gate = subprocess.run(
            [sys.executable, os.path.join(os.path.dirname(__file__), "check_clean_environment.py")],
            capture_output=True, text=True, timeout=120,
        )
        print(gate.stdout)
        if gate.returncode >= 2:
            raise SystemExit("environment check FAILED")

    try:
        st = req("GET", "/v1/stats", timeout=10)
        for mid in (st.get("models") or {}):
            if mid != MODEL_ID:
                print(f"  unloading resident {mid}…")
                req("POST", "/v1/models/unload", {"model_id": mid}, timeout=120)
    except Exception as e:
        print(f"  unload skipped: {e}")
    for _ in range(30):
        out = subprocess.run(
            ["tasklist", "//FI", "IMAGENAME eq llama-server.exe"],
            capture_output=True, text=True, timeout=15,
        ).stdout
        if "llama-server.exe" not in out:
            break
        time.sleep(1)

    print(f"loading {QUANT_TAG}: {MODEL}")
    req("POST", "/v1/models/load", {
        "model_id": MODEL_ID, "model_path": MODEL,
        "n_ctx": 2048, "force": True,
    }, timeout=600)
    time.sleep(1)

    results = {"quant": QUANT_TAG, "model": MODEL_ID, "runs": []}
    for i in range(RUNS):
        raw = ask()
        results["runs"].append({"round": i + 1, "raw": raw})
        print(f"  round {i + 1}/{RUNS} done ({len(raw)} chars)")
    results["tok_s"] = tok_s()

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\nsaved {OUT}  (tok_s={results['tok_s']}, {RUNS} runs)")


if __name__ == "__main__":
    main()
