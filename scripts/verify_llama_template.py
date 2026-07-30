"""Verify native GGUF chat-template handling on a Llama-family model.

Acceptance (HANDOFF_STREAMING_RELIABILITY.md item 5): native template
output remains correct for at least one Qwen-family AND one Llama-family
GGUF. Qwen was verified 2026-07-29; this covers the Llama side.

Checks:
1. The GGUF embeds a chat template (tokenizer.chat_template metadata).
2. stream_chat() uses the NATIVE create_chat_completion path (no
   fallback-to-prompt-formatter warning) and streams real deltas.
3. Output contains no leaked template markers.
4. Generation stats + paging telemetry are recorded.

Run:  python scripts/verify_llama_template.py
Needs: research/models/Llama-3.2-1B-Instruct-Q2_K.gguf
"""
import os
import sys
import json
import logging

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

MODEL_PATH = "research/models/Llama-3.2-1B-Instruct-Q2_K.gguf"
LEAK_MARKERS = ["<|", "|>", "start_header_id", "end_header_id",
                "eot_id", "im_start", "im_end"]


class FallbackDetector(logging.Handler):
    def __init__(self):
        super().__init__()
        self.fallback_triggered = False

    def emit(self, record):
        if "Native chat template unavailable" in record.getMessage():
            self.fallback_triggered = True


def main():
    if not os.path.isfile(MODEL_PATH):
        print(f"FATAL: model not found: {MODEL_PATH}")
        return 1

    detector = FallbackDetector()
    logging.getLogger("weight_stream.backends.llama_cpp").addHandler(detector)

    from weight_stream.backends.llama_cpp import WeightStreamModel
    model = WeightStreamModel(MODEL_PATH, n_ctx=512,
                              n_threads=max(1, (os.cpu_count() or 4) // 2))

    results = {}

    # 1. Embedded chat template
    meta = getattr(model._llm, "metadata", {}) or {}
    tmpl = meta.get("tokenizer.chat_template", "")
    results["has_embedded_template"] = bool(tmpl)
    print(f"[check1] embedded chat_template: "
          f"{'YES' if tmpl else 'NO'} ({len(tmpl)} chars)")

    # 2+3. Native streaming + no leaked markers
    msgs = [{"role": "user",
             "content": "Reply with exactly one word: hello"}]
    chunks = []
    for ch in model.stream_chat(msgs, max_tokens=24, temperature=0.0):
        chunks.append(ch)
    text = "".join(chunks)
    leaks = [m for m in LEAK_MARKERS if m in text]
    results["native_path_used"] = not detector.fallback_triggered
    results["chunks"] = len(chunks)
    results["leaked_markers"] = leaks
    results["response_preview"] = text[:120]
    print(f"[check2] native path used (no fallback): "
          f"{not detector.fallback_triggered} | {len(chunks)} chunks")
    print(f"[check3] leaked template markers: {leaks or 'none'}")
    print(f"         response: {text[:120]!r}")

    # 4. Stats + paging recorded
    stats = model._last_gen_stats or {}
    paging = stats.get("paging")
    results["stats_token_count"] = stats.get("token_count")
    results["paging"] = paging
    print(f"[check4] stats: token_count={stats.get('token_count')} "
          f"tok/s={stats.get('tokens_per_sec', 0):.1f} | paging="
          f"{json.dumps(paging)}")

    ok = (results["has_embedded_template"] and results["native_path_used"]
          and results["chunks"] > 0 and not leaks
          and (stats.get("token_count") or 0) > 0 and paging is not None)
    print(f"\n=== {'PASS' if ok else 'FAIL'}: Llama-family native template "
          f"verification {'succeeded' if ok else 'FAILED'} ===")

    os.makedirs("docs/verification", exist_ok=True)
    with open("docs/verification/llama_template_2026-07-30.json", "w",
              encoding="utf-8") as fh:
        json.dump({"model": MODEL_PATH, "results": results, "pass": ok},
                  fh, indent=2, ensure_ascii=False)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
