"""Thai quality gate — the project's quality floor for every measured model.

Port of the fixed question set proven in EXP-009/EXP-011: ultra-low-bit
quants (IQ1_M on Qwen3.6-35B-A3B) fail Thai tonal accuracy while heavier
quants pass. The gate exists so a benchmark number is never reported
without the QUALITY side of the trade — 70 tok/s that cannot distinguish
"ข้าว" from "ข่าว" is not a win.

The 9 questions are fixed (same params: temperature=0, max_tokens=2048,
reasoning_mode=off) so runs across quants/models are diffable side by side.
"""

from __future__ import annotations

import json
import time
import urllib.request
from typing import Any, Callable, Optional

# (id, question) — the fixed set; 5 "easy" dimensions + 4 harder ones where
# ultra-low-bit quant should actually break (math_multi, price_pct,
# thai_tonal, science).
QUESTIONS: list[tuple[str, str]] = [
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

HttpFn = Callable[[str, str, Optional[dict]], Any]


def _req(base: str, method: str, path: str, body: Optional[dict] = None) -> Any:
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(
        f"{base}{path}",
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(r, timeout=600) as resp:
        return json.loads(resp.read().decode("utf-8"))


def split_think(content: str) -> tuple[str, str]:
    """Split raw model output into (thinking, final_answer).

    The backend may emit thinking blocks regardless of reasoning_mode; the
    FINAL answer after the block closes is what quality is judged on.
    Handles two known formats:

    - ``<think>…</think>`` (Qwen family, EXP-011/018)
    - ``<|channel>thought …<channel|>`` (Gemma 4, EXP-019)
    """
    import re

    # Gemma 4 emits <|channel>thought …<channel|> (or an unclosed variant).
    m = re.search(r"<channel\|>\s*(.*)", content, re.S)
    if m:
        think = re.sub(r"<\|channel\|?\s*>", "", content[: m.start()],
                       flags=re.S)
        return think.strip(), m.group(1).strip()
    m = re.search(r"</think>\s*(.*)", content, re.S)
    if m:
        think = re.sub(r"<think>\s*", "", content[: m.start()], flags=re.S)
        return think.strip(), m.group(1).strip()
    return "", content.strip()


def ask(
    base: str,
    model_id: str,
    question: str,
    max_tokens: int = 2048,
    http: Optional[HttpFn] = None,
) -> str:
    """Ask one fixed question and return the raw model content."""

    def _default_http(method: str, path: str, body: Optional[dict] = None) -> Any:
        return _req(base, method, path, body)

    req = http or _default_http
    body = {
        "model": model_id,
        "messages": [{"role": "user", "content": question}],
        "max_tokens": max_tokens,  # model writes long EN think blocks
        "temperature": 0.0,
        "top_p": 1.0,
        "stream": False,
        "reasoning_mode": "off",  # direct answer quality, not thinking quality
    }
    r = req("POST", "/v1/chat/completions", body)
    msg = r["choices"][0]["message"]
    return msg.get("content") or ""


def run_quality_gate(
    base: str,
    model_id: str,
    max_tokens: int = 2048,
    http: Optional[HttpFn] = None,
) -> dict[str, Any]:
    """Ask the full 9-question set; return answers + tok/s + wall time.

    Answers are keyed by question id so two runs (e.g. IQ2_M vs IQ1_M) can
    be diffed side by side. tok_s is read from /v1/stats after the run.
    """
    def _default_http(method: str, path: str, body: Optional[dict] = None) -> Any:
        return _req(base, method, path, body)

    req = http or _default_http
    answers: dict[str, dict[str, str]] = {}
    t0 = time.monotonic()
    for qid, q in QUESTIONS:
        raw = ask(base, model_id, q, max_tokens=max_tokens, http=http)
        think, final = split_think(raw)
        # FULL think is kept — it is the evidence (e.g. EXP-018: the model's
        # own think shows the wrong Thai tones; truncating it would hide the
        # finding). Display layers truncate; the JSON record must not.
        answers[qid] = {"final": final, "think": think}
    wall_s = round(time.monotonic() - t0, 1)

    tok_s = None
    try:
        st = req("GET", "/v1/stats", None)
        gen = (st.get("models") or {}).get(model_id, {}).get("generation") or {}
        tok_s = gen.get("tokens_per_sec") or gen.get("tok_s")
    except Exception:
        pass

    return {
        "model": model_id,
        "tok_s": tok_s,
        "wall_s": wall_s,
        "answers": answers,
    }
