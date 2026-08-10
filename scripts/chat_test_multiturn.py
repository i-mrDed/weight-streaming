"""Multi-turn REAL-CHAT test between two quants of the same model.

Unlike compare_quant_quality.py (single-shot Q&A), this simulates an actual
work session: ONE long conversation where each turn builds on the previous
context — writing, revising, summarizing, debugging, writing tests. This is
where quant damage shows up differently (context drift, instruction decay).

Usage (same env contract as compare_quant_quality.py):
    WS_TEST_MODEL="C:/.../IQ1_M.gguf" WS_TEST_MODEL_ID="qwen36a3b_iq1m" \
        WS_QUANT_TAG="IQ1_M" python scripts/chat_test_multiturn.py

Output: scripts/.chat_quality_out.json (first run) and
        scripts/.chat_quality_out.<quant>.json (per-quant copy) — the
        harness copies each quant's result to its own tagged file so the
        A/B diff survives even if the last run overwrites the shared OUT.
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
MODEL_ID = os.environ.get("WS_TEST_MODEL_ID", "chattest")
QUANT_TAG = os.environ.get("WS_QUANT_TAG", "unknown")
OUT = os.path.join(os.path.dirname(__file__), ".chat_quality_out.json")

# One realistic work session: each turn references the previous turn's
# output (context accumulation), like a user actually chatting.
SAMPLE_EMAIL_DRAFT = (
    "สวัสดีครับคุณสมชาย ผมอยากขอเลื่อนประชุมโครงการวันศุกร์นี้ เพราะมีงาน "
    "ด่วนที่ต้องส่งลูกค้า หวังว่าคุณจะสะดวกเลื่อนเป็นสัปดาห์หน้า"
)
SAMPLE_BUGGY_CODE = (
    "def calc_total(prices, discount_pct):\n"
    "    total = 0\n"
    "    for p in prices:\n"
    "        total += p\n"
    "    return total * (100 - discount_pct) / 100\n"
    "    # ปัญหา: คิด discount ซ้ำกับราคาที่ลดแล้ว?\n"
    "print(calc_total([100, 200, 300], 10))"
)

TURNS = [
    ("write_email", f"ช่วยปรับ draft อีเมลนี้ให้สุภาพและเป็นทางการมากขึ้น:\n\n{SAMPLE_EMAIL_DRAFT}"),
    ("revise_shorter", "ดีขึ้นแล้ว แต่ยาวเกินไป ช่วยตัดให้สั้นลงเหลือไม่เกิน 3 ประโยค โดยคงความสุภาพไว้ และเพิ่มประโยคขอโทษ"),
    ("summarize_bullets", "ช่วยสรุปเนื้อหาต่อไปนี้เป็น bullet 5 ข้อ:\n\n'การทำงานจากระยะไกลกลายเป็นเรื่องปกติหลังปี 2020 บริษัทหลายแห่งพบว่าพนักงานมี productivity สูงขึ้น 20-30% แต่ก็พบปัญหาความโดดเดี่ยวและการสื่อสารที่ช้าลง การผสมผสานระหว่างทำงานออฟฟิศและที่บ้าน (hybrid) กลายเป็นทางเลือกที่นิยมที่สุด เพราะได้ทั้งสองข้อดี ขณะเดียวกันก็ต้องลงทุนกับเครื่องมือ collaboration และการจัดการทีมแบบใหม่'"),
    ("reformat_formal", "สรุปได้ดี ช่วยเขียนใหม่เป็นภาษาไทยแบบทางการ เหมาะสำหรับใส่ในรายงานบริษัท"),
    ("debug_code", f"โค้ด Python นี้มีบั๊ก ช่วยหาว่าอะไรผิดและแก้ให้:\n\n{SAMPLE_BUGGY_CODE}"),
    ("write_tests", "โค้ดที่แก้แล้วดีมาก ช่วยเขียน unit test ด้วย pytest ครอบ 3 กรณี: ราคาปกติ, ส่วนลด 0%, และ list ว่าง"),
]


def req(method, path, body=None, timeout=600):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(
        f"{BASE}{path}", data=data, method=method,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(r, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def chat(messages):
    body = {
        "model": MODEL_ID,
        "messages": messages,
        "max_tokens": 2048,
        "temperature": 0.0,
        "top_p": 1.0,
        "stream": False,
        "reasoning_mode": "off",
    }
    r = req("POST", "/v1/chat/completions", body)
    msg = r["choices"][0]["message"]
    return msg.get("content") or ""


def split_think(content):
    m = re.search(r"</think>\s*(.*)", content, re.S)
    if m:
        think = re.sub(r"<think>\s*", "", content[: m.start()], flags=re.S)
        return think.strip(), m.group(1).strip()
    return "", content.strip()


def tok_s():
    st = req("GET", "/v1/stats", timeout=10)
    gen = (st.get("models") or {}).get(MODEL_ID, {}).get("generation") or {}
    return gen.get("tokens_per_sec") or gen.get("tok_s")


def unload_resident():
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
    else:
        print("WARN: llama-server still running after unload — load may collide")


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
            raise SystemExit("environment check FAILED — fix findings and re-run")
        if gate.returncode == 1:
            print("WARN: environment has warnings; continuing (chat run is short)")

    unload_resident()

    print(f"loading {QUANT_TAG}: {MODEL}")
    req("POST", "/v1/models/load", {
        "model_id": MODEL_ID,
        "model_path": MODEL,
        "n_ctx": 4096,
        "force": True,
    }, timeout=600)
    time.sleep(1)

    results = {"quant": QUANT_TAG, "model": MODEL_ID, "tok_s": None, "turns": {}}
    messages = []
    t0 = time.monotonic()
    for tid, question in TURNS:
        messages.append({"role": "user", "content": question})
        print(f"  [{tid}] chatting…")
        raw = chat(messages)
        think, final = split_think(raw)
        results["turns"][tid] = {"final": final, "think": think[:300]}
        messages.append({"role": "assistant", "content": final or raw})
    results["wall_s"] = round(time.monotonic() - t0, 1)
    results["tok_s"] = tok_s()

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    tagged = OUT.replace(".json", f".{QUANT_TAG.lower()}.json")
    with open(tagged, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\nsaved {OUT} + {tagged}  (tok_s={results['tok_s']}, {results['wall_s']}s for {len(TURNS)} turns)")


if __name__ == "__main__":
    main()
