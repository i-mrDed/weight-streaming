"""Curated \"proven on this rig\" model recommendations for the Hub.

Every entry is backed by a measured experiment under ``research/experiments/``
— the project's honest-telemetry rule (ADR-003) applies to curated data too:
a model earns a slot here only after a CLEAN-ROOM measurement on the
reference rig (12 GB VRAM / 64 GB RAM, Jan llama-server b9967) that includes
the Thai quality gate (9 fixed questions + the tonal discriminator). No
entry is ranked by marketing, downloads, or hearsay — the ``experiment``
field links to the evidence, and the numbers are the measured ranges.

The ``files`` list is the exact download set (byte sizes verified against HF
at curation time). The Hub UI downloads exactly these files, so a user gets
the quant we actually measured — not a look-alike. Human-readable fields
(``tagline``/``notes``) are locale dicts ``{"en": …, "th": …}`` — the
frontend picks the active language while the measured numbers stay one
source of truth.

Hardware caveat (honest): the tok/s ranges were measured on THIS machine
(i9-9900KF + RTX 3060 12 GB + 64 GB DDR4). Other GPUs/CPUs will differ; the
Thai verdict and the *relative* ordering between quants are the portable
part.
"""

from __future__ import annotations

# Roles drive the badge + placement in the Hub UI.
ROLE_THAI = "thai"       # Thai-safe daily driver (gate 9/9 + tonal pass)
ROLE_SPEED = "speed"     # fastest measured; Thai tonal NOT safe
ROLE_BALANCED = "balanced"  # Thai-safe but slower than the speed tier

RECOMMENDED: list[dict] = [
    {
        "repo_id": "unsloth/gemma-4-12B-it-qat-GGUF",
        "name": "Gemma 4 12B",
        "arch": "dense 12B",
        "role": ROLE_THAI,
        "tagline": {
            "en": "Fastest Thai-safe model measured on this rig — fits fully in VRAM",
            "th": "โมเดลไทยปลอดภัยที่เร็วสุดที่วัดได้บนเครื่องนี้ — พอดี VRAM",
        },
        "quants": [
            {
                "quant": "UD-Q4_K_XL + MTP draft Q8_0",
                "files": [
                    {"filename": "gemma-4-12B-it-qat-UD-Q4_K_XL.gguf",
                     "bytes": 6_716_356_800},
                    {"filename": "MTP/mtp-gemma-4-12B-it-Q8_0.gguf",
                     "bytes": 465_127_936},
                ],
                "total_bytes": 7_181_484_736,
                "tok_s_min": 68,
                "tok_s_max": 76,
                "thai_correct": 9,
                "thai_total": 9,
                "thai_tonal_correct": 6,
                "thai_tonal_total": 6,
                "experiment": "research/experiments/EXP-022-gemma4-12b",
                "notes": {
                    "en": ("Fits entirely in 12 GB VRAM (no CPU spill) — the "
                           "fastest Thai-safe model measured on this rig: "
                           "75.7 tok/s sustained with Thai gate 9/9 + tonal "
                           "6/6 (EXP-022). +52% faster than the 26B QAT at "
                           "the same Thai quality; threads don't matter "
                           "(t8 = t12)."),
                    "th": ("พอดี VRAM 12 GB ทั้งหมด (ไม่ spill) — โมเดลที่เร็ว "
                           "สุดและไทยปลอดภัยที่วัดได้บนเครื่องนี้: 75.7 tok/s "
                           "ต่อเนื่อง + Thai gate 9/9 + วรรณยุกต์ 6/6 "
                           "(EXP-022) เร็วกว่า 26B QAT +52% ด้วยคุณภาพไทย "
                           "เท่ากัน"),
                },
                "flags": "-t 8 --spec-type draft-mtp --spec-draft-n-max 2",
            },
        ],
    },
    {
        "repo_id": "unsloth/gemma-4-26B-A4B-it-qat-GGUF",
        "name": "Gemma 4 26B-A4B",
        "arch": "MoE 26B-A4B",
        "role": ROLE_THAI,
        "tagline": {
            "en": "Thai-safe quality-first — the stronger 26B-A4B, ~50 tok/s",
            "th": "คุณภาพนำ ไทยปลอดภัย — 26B-A4B ที่เก่งกว่า, ~50 tok/s",
        },
        "quants": [
            {
                "quant": "UD-Q4_K_XL + MTP draft Q8_0",
                "files": [
                    {"filename": "gemma-4-26B-A4B-it-qat-UD-Q4_K_XL.gguf",
                     "bytes": 14_249_047_104},
                    {"filename": "MTP/mtp-gemma-4-26B-A4B-it-Q8_0.gguf",
                     "bytes": 461_785_600},
                ],
                "total_bytes": 14_710_832_704,
                "tok_s_min": 47,
                "tok_s_max": 51,
                "thai_correct": 9,
                "thai_total": 9,
                "thai_tonal_correct": 6,
                "thai_tonal_total": 6,
                "experiment": "research/experiments/EXP-019-gemma4-qat",
                "notes": {
                    "en": ("QAT (quantization-aware training) sidesteps the "
                           "IQ-quant quality cliff — the ONLY tested model with "
                           "a perfect Thai tonal score (EXP-019). MTP gives "
                           "~+20%; -t 12 (EXP-020) adds ~+13% more (49-51 "
                           "tok/s sustained)."),
                    "th": ("QAT (การฝึกแบบตระหนักถึง quantization) ข้ามหน้าผา "
                           "คุณภาพของ IQ quant — โมเดลเดียวที่ทดสอบแล้วได้ "
                           "คะแนนวรรณยุกต์ไทยเต็ม (EXP-019) MTP ให้ +~20% "
                           "และ -t 12 (EXP-020) เพิ่มอีก ~+13% (49-51 tok/s "
                           "ต่อเนื่อง)"),
                },
                "flags": "-t 12 --spec-type draft-mtp --spec-draft-n-max 2",
            },
        ],
    },
    {
        "repo_id": "unsloth/Qwen3.6-35B-A3B-GGUF",
        "name": "Qwen3.6-35B-A3B",
        "arch": "MoE 35B-A3B",
        "role": ROLE_BALANCED,
        "tagline": {
            "en": "The proven 12 GB workhorse — pick the quant by priority",
            "th": "ม้าศึก 12 GB ที่พิสูจน์แล้ว — เลือก quant ตามลำดับความสำคัญ",
        },
        "quants": [
            {
                "quant": "UD-IQ2_M",
                "files": [
                    {"filename": "Qwen3.6-35B-A3B-UD-IQ2_M.gguf",
                     "bytes": 11_522_702_304},
                ],
                "total_bytes": 11_522_702_304,
                "tok_s_min": 43,
                "tok_s_max": 56,
                "thai_correct": 9,
                "thai_total": 9,
                "thai_tonal_correct": 6,
                "thai_tonal_total": 6,
                "experiment": "research/experiments/EXP-011-iq1m-quant",
                "notes": {
                    "en": ("Largest quant of the family that still PASSES the "
                           "Thai tonal gate (EXP-011). Slower than the IQ2_XXS "
                           "tier — quality-first pick when Gemma 4 is too big."),
                    "th": ("quant ใหญ่สุดในตระกูลที่ยังผ่าน gate วรรณยุกต์ไทย "
                           "(EXP-011) ช้ากว่า tier IQ2_XXS — ตัวเลือกเน้นคุณภาพ "
                           "เมื่อ Gemma 4 ใหญ่เกินไป"),
                },
                "flags": None,
            },
            {
                "quant": "UD-IQ2_XXS",
                "files": [
                    {"filename": "Qwen3.6-35B-A3B-UD-IQ2_XXS.gguf",
                     "bytes": 10_756_586_464},
                ],
                "total_bytes": 10_756_586_464,
                "tok_s_min": 61,
                "tok_s_max": 66,
                "thai_correct": 8,
                "thai_total": 9,
                "thai_tonal_correct": 1,
                "thai_tonal_total": 6,
                "experiment": "research/experiments/EXP-018-iq2xxs-harness",
                "notes": {
                    "en": ("Fastest Thai-mostly quant — but the tonal "
                           "discriminator FAILS (1/6, EXP-018), same failure "
                           "class as IQ1_M. Fine for non-Thai speed work."),
                    "th": ("quant ที่เร็วสุดในกลุ่มที่ไทยพอใช้ — แต่ตัวแยก "
                           "วรรณยุกต์ล้มเหลว (1/6, EXP-018) ความล้มเหลวแบบเดียว "
                           "กับ IQ1_M เหมาะกับงานเร็วที่ไม่ใช่ภาษาไทย"),
                },
                "flags": None,
            },
            {
                "quant": "UD-IQ1_M",
                "files": [
                    {"filename": "Qwen3.6-35B-A3B-UD-IQ1_M.gguf",
                     "bytes": 10_047_749_088},
                ],
                "total_bytes": 10_047_749_088,
                "tok_s_min": 72,
                "tok_s_max": 78,
                "thai_correct": 8,
                "thai_total": 9,
                "thai_tonal_correct": 0,
                "thai_tonal_total": 6,
                "experiment": "research/experiments/EXP-011-iq1m-quant",
                "notes": {
                    "en": ("Speed-first: fastest measured on this rig — but "
                           "Thai tonal is wrong with confidence (0/6, EXP-011). "
                           "Only for non-Thai / speed-critical work."),
                    "th": ("เน้นความเร็ว: เร็วสุดที่วัดได้บนเครื่องนี้ — แต่ "
                           "วรรณยุกต์ไทยผิดอย่างมั่นใจ (0/6, EXP-011) ใช้เฉพาะ "
                           "งานไม่ใช้ภาษาไทย/งานที่ต้องเร็วมาก"),
                },
                "flags": None,
            },
        ],
    },
]


def to_payload() -> dict:
    """Serializable payload for GET /v1/hub/recommended (no network I/O)."""
    return {"recommended": RECOMMENDED, "count": len(RECOMMENDED)}
