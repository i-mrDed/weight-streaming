"""Compare answer QUALITY between two quantizations of the same model.

Loads the model given by WS_TEST_MODEL on the running API server, asks a
FIXED question set (same params: temperature=0, max_tokens=512, reasoning
off), and saves the answers + measured tok/s to scripts/.quant_quality_out.json.

Usage:
    WS_TEST_MODEL="C:/.../model.gguf" WS_TEST_MODEL_ID="qwen36a3b_iq1m" \
        WS_QUANT_TAG="IQ1_M" python scripts/compare_quant_quality.py

Answers are keyed by the question id so two runs (IQ2_M vs IQ1_M) can be
diffed side by side. Requires the server on :8765 (WS_PORT to override).
"""
import json
import os
import subprocess
import sys
import time
import urllib.request

PORT = os.environ.get("WS_PORT", "8765")
BASE = f"http://127.0.0.1:{PORT}"
MODEL = os.environ.get("WS_TEST_MODEL")
MODEL_ID = os.environ.get("WS_TEST_MODEL_ID", "quantcmp")
QUANT_TAG = os.environ.get("WS_QUANT_TAG", "unknown")
OUT = os.path.join(os.path.dirname(__file__), ".quant_quality_out.json")

# Fixed question set — 5 dimensions that ultra-low-bit quant damages most.
# (id, question) — answer quality judged per dimension in analysis.
QUESTIONS = [
    (
        "fact_thai",
        "เมืองหลวงของประเทศไทยคืออะไร และแม่น้ำสายสำคัญสายหนึ่งที่ไหลผ่านคือแม่น้ำอะไร",
    ),
    (
        "math",
        "จงคำนวณ: 17 × 23 = ? (ตอบเป็นตัวเลขเท่านั้น)",
    ),
    (
        "logic",
        "มีไก่ 3 ตัว และวัว 2 ตัว รวมขาทั้งหมดกี่ขา? (ตอบเป็นตัวเลขพร้อมเหตุผลสั้นๆ)",
    ),
    (
        "code",
        "เขียนฟังก์ชัน Python ชื่อ is_palindrome(s) ที่รับ string แล้วคืน True ถ้าเป็น palindrome (อ่านจากหน้าไปหลังและหลังมาหน้าเหมือนกัน) ละเว้นช่องว่างและตัวพิมพ์ใหญ่เล็ก",
    ),
    (
        "thai_lang",
        "อธิบายความหมายของสำนวนไทย 'น้ำขึ้นให้รีบตัก' พร้อมยกตัวอย่างสถานการณ์ที่ใช้",
    ),
    # --- harder set: where ultra-low-bit quant should actually break ---
    (
        "math_multi",
        "ถ้า a = 3, b = 4, c = 5 จงหาค่า a² + b² − c² และบอกว่าผลลัพธ์เท่ากับเท่าไหร่ (แสดงวิธีคำนวณสั้นๆ)",
    ),
    (
        "price_pct",
        "สินค้าราคา 500 บาท ลด 20% แล้วบวก VAT 7% ราคาสุดท้ายเท่าไหร่? (แสดงวิธีคำนวณ)",
    ),
    (
        "thai_tonal",
        "จงแยกความหมายของคำว่า 'ข้าว' 'ข่าว' 'เข้า' 'ไข่' 'ไก่' 'ไหม' ตามเสียงวรรณยุกต์ในภาษาไทย พร้อมยกตัวอย่างประโยคสั้นๆ สำหรับแต่ละคำ",
    ),
    (
        "science",
        "น้ำ 1 ลิตรหนักประมาณกี่กิโลกรัม? แล้วน้ำ 500 มิลลิลิตรมีกี่กรัม? (ตอบเป็นตัวเลข)",
    ),
]


def req(method, path, body=None, timeout=600):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(
        f"{BASE}{path}", data=data, method=method,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(r, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def ask(qid, question):
    body = {
        "model": MODEL_ID,
        "messages": [{"role": "user", "content": question}],
        "max_tokens": 2048,  # model writes long EN think blocks; starves short budgets
        "temperature": 0.0,
        "top_p": 1.0,
        "stream": False,
        "reasoning_mode": "off",  # direct answer quality, not thinking quality
    }
    r = req("POST", "/v1/chat/completions", body)
    msg = r["choices"][0]["message"]
    return msg.get("content") or ""


def split_think(content):
    """Split raw model output into (thinking, final_answer). The backend
    may emit <think>…</think> blocks regardless of reasoning_mode; the
    FINAL answer after the close tag is what quality is judged on."""
    import re

    m = re.search(r"</think>\s*(.*)", content, re.S)
    if m:
        think = re.sub(r"<think>\s*", "", content[: m.start()], flags=re.S)
        return think.strip(), m.group(1).strip()
    return "", content.strip()


def tok_s():
    st = req("GET", "/v1/stats", timeout=10)
    # stats shape: {"models": {id: {"generation": {"tokens_per_sec": …}}}}
    gen = (st.get("models") or {}).get(MODEL_ID, {}).get("generation") or {}
    return gen.get("tokens_per_sec") or gen.get("tok_s")


def main():
    if not MODEL:
        raise SystemExit("WS_TEST_MODEL is required")
    # Clean-room gate: abort on FAIL (exit>=2) — a polluted environment
    # makes the quality comparison meaningless too. WS_SKIP_GATE=1 is set
    # when this script is chained as part of a 2-quant A/B run (the FIRST
    # quant legitimately leaves a llama-server loaded for the second).
    if os.environ.get("WS_SKIP_GATE") != "1":
        gate = subprocess.run(
            [sys.executable, os.path.join(os.path.dirname(__file__), "check_clean_environment.py")],
            capture_output=True, text=True, timeout=120,
        )
        print(gate.stdout)
        if gate.returncode >= 2:
            raise SystemExit("environment check FAILED — fix findings and re-run")
        if gate.returncode == 1:
            print("WARN: environment has warnings; continuing (quality run is short)")

    # Unload the resident model first (if any) — the llama-server backend
    # owns one port (8805), so a different quant still resident makes load
    # fail with a port-collision ModelError even with force=True. The API
    # unload needs the EXACT resident model_id (no wildcard).
    try:
        st = req("GET", "/v1/stats", timeout=10)
        for mid in (st.get("models") or {}):
            if mid != MODEL_ID:
                print(f"  unloading resident {mid}…")
                req("POST", "/v1/models/unload", {"model_id": mid}, timeout=120)
    except Exception as e:
        print(f"  unload skipped: {e}")
    # The llama-server child takes a moment to die after unload; loading a
    # different quant while it still owns port 8805 fails with a collision.
    # Poll until no llama-server.exe is left (bounded).
    for _ in range(30):
        out = subprocess.run(
            ["tasklist", "//FI", "IMAGENAME eq llama-server.exe"],
            capture_output=True, text=True, timeout=15,
        ).stdout
        if "llama-server.exe" not in out:
            break
        time.sleep(1)
    else:
        print("WARN: llama-server still running after unload — load may collide")

    print(f"loading {QUANT_TAG}: {MODEL}")
    req("POST", "/v1/models/load", {
        "model_id": MODEL_ID,
        "model_path": MODEL,
        "n_ctx": 2048,
        "force": True,  # covers an already-loaded same-model race
    }, timeout=600)
    time.sleep(1)

    results = {"quant": QUANT_TAG, "model": MODEL_ID, "tok_s": None, "answers": {}}
    t0 = time.monotonic()
    for qid, q in QUESTIONS:
        print(f"  [{qid}] asking…")
        raw = ask(qid, q)
        think, final = split_think(raw)
        results["answers"][qid] = {"final": final, "think": think[:400]}
    elapsed = time.monotonic() - t0
    elapsed = time.monotonic() - t0
    results["tok_s"] = tok_s()
    results["wall_s"] = round(elapsed, 1)

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\nsaved {OUT}  (tok_s={results['tok_s']}, {results['wall_s']}s for {len(QUESTIONS)} q)")


if __name__ == "__main__":
    main()
