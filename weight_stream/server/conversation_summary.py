"""
Conversation summarization service (Context Management POC).

Implements the "running summary in system prompt" strategy proven in
EXP/research 12 (Qwythos long-chat): compress a conversation into a
short summary that preserves key facts, so long chats keep working even
with a small context window.

Design (no conflicts with Chat Agent Tools):
- Standalone service module (new file) — does not touch ChatPage /
  api_server chat routes / workspace tools.
- Pure logic kept testable: `build_summary_prompt`, `merge_summary`,
  `estimate_tokens`, `should_compact` are pure functions.
- The actual LLM call goes through `manager.chat_completion` (existing).

Usage (server side):
    svc = ConversationSummarizer(manager)
    summary = await svc.summarize(messages, model_id, existing_summary)
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Defaults (tuned in research/12: compact every 2 turns kept memory 5/5)
DEFAULT_MAX_SUMMARY_CHARS = 5000
DEFAULT_COMPACT_EVERY_TURNS = 2
DEFAULT_SUMMARY_MAX_TOKENS = 600
DEFAULT_EST_TOKENS_PER_CHAR = 1.0  # heuristic for Thai/UTF-8 heavy text


def estimate_tokens(
    messages: List[Dict[str, Any]],
    factor: float = DEFAULT_EST_TOKENS_PER_CHAR,
) -> int:
    """Rough token estimate from message contents (heuristic only)."""
    total: float = 0.0
    for m in messages:
        c = (m.get("content") or "")
        if isinstance(c, str):
            total += len(c) * factor
    return int(total)


def build_summary_prompt(
    messages: List[Dict[str, Any]],
    existing_summary: Optional[str] = None,
    max_transcript_chars: int = 10000,
) -> str:
    """Build the summarization prompt (Thai-first, carries old summary)."""
    transcript = "\n".join(
        f"{m.get('role')}: {m.get('content')}" for m in messages[-40:]
    )
    if existing_summary:
        # Explicit instruction to KEEP the existing summary and only
        # extend it — prevents the model echoing the instruction back.
        return (
            "ต่อไปนี้คือ (ก) สรุปเดิมที่มีอยู่ และ (ข) บทสนทนาล่าสุด\n"
            "จงตอบ SUMMARY: ใหม่ ที่รวมสรุปเดิม + ข้อเท็จจริงใหม่จากบทสนทนา "
            "ภาษาไทย กระชับ ไม่เกิน 300 คำ\n"
            "ห้ามอธิบายขั้นตอน ห้ามทวนคำสั่ง ห้ามขึ้นต้นด้วยการคิด "
            "ตอบเป็น SUMMARY: เท่านั้น\n\n"
            f"(ก) สรุปเดิม:\n{existing_summary[:1500]}\n\n"
            f"(ข) บทสนทนาล่าสุด:\n{transcript[:max_transcript_chars]}\n\n"
            "SUMMARY:"
        )
    return (
        "คุณคือระบบสรุปบทสนทนา จงเขียน SUMMARY ภาษาไทย กระชับ "
        "แต่คงข้อเท็จจริงสำคัญของผู้ใช้ (ชื่อ, งานอดิเรก, สัตว์เลี้ยง, "
        "โปรเจค, สถานที่, ความชอบ) และประเด็นที่ค้างไว้\n"
        "ห้ามอธิบายขั้นตอน ห้ามทวนคำสั่ง ตอบเป็น SUMMARY: เท่านั้น\n\n"
        "บทสนทนา:\n"
        + transcript[:max_transcript_chars]
        + "\n\nSUMMARY:"
    )


def _strip_thinking(text: str) -> str:
    """Strip a leading/mid ' thinking ... response' block (Qwythos plans
    before answering even with reasoning off). Handles the space-tag
    convention this project uses (llama_cpp._strip_thinking)."""
    import re
    # pattern: optional whitespace + " thinking ... " + " response"
    m = re.search(r"[\s]*\bthinking\b(.*?)\bresponse\b", text, re.DOTALL)
    if m:
        return text[m.end():].strip()
    # fallback: leading "thinking" line(s) up to a numbered list start
    if re.match(r"^\s*thinking\s*$", text) or text.startswith("thinking\n"):
        lines = text.splitlines()
        # skip the 'thinking' marker + any plan lines until a Thai/English
        # sentence that looks like the actual summary
        for i, line in enumerate(lines):
            if i > 0 and line.strip() and not line.strip()[0].isdigit() \
                    and not line.strip().startswith(("-", "*", "1.")):
                return "\n".join(lines[i:]).strip()
        return ""
    return text


def _after_marker(line: str) -> str:
    """Text after 'SUMMARY:' (or 'SUMMARY»' / 'SUMMARY"') in a line."""
    low = line.lower()
    for mk in (":", "»", '"'):
        idx = low.find(mk)
        if idx >= 0:
            return line[idx + 1:]
    return ""


def _strip_instruction_echo(text: str) -> str:
    """Some models (Qwythos) start by restating the instruction in English
    before the actual summary (e.g. 'SUMMARY:" and not include any
    explanations or repetitions of instructions.'). Drop such leading
    echo lines until the first fact-bearing line. The 'SUMMARY:' marker
    line itself is always kept."""
    import re
    echo_words = ("explanation", "instruction", "repetition", "not include",
                  "steps", "summarize the", "draft the", "identify the",
                  "understand the", "verify", "ensure the", "response should")
    lines = text.splitlines()
    kept_marker = False
    kept = []
    reading = True
    for line in lines:
        low = line.lower()
        if not kept_marker and re.match(r"^\s*summary\s*[:」\"]", low):
            tail = _after_marker(line)
            if tail and any(w in tail for w in echo_words):
                # marker + echo on the same line -> keep marker only
                kept.append(line[:len(line) - len(tail)].strip())
            else:
                kept.append(line)          # normal SUMMARY: line
            kept_marker = True
            continue
        if reading and low.strip() and any(w in low for w in echo_words):
            continue                    # drop echo line(s)
        # drop model "plan/thinking" steps: numbered lines with **bold**
        # headers (e.g. "2. **Extract key facts:**", "7. **Structure:**")
        if reading and re.match(r"^\s*\d+\.\s*\*\*", low):
            continue
        kept.append(line)
        reading = False                 # facts start after first kept line
    return "\n".join(kept).strip()


def extract_summary(text: str, max_chars: int = DEFAULT_MAX_SUMMARY_CHARS) -> str:
    """Extract the SUMMARY: section from a model response."""
    if not text:
        return ""
    if "SUMMARY:" in text:
        text = text[text.index("SUMMARY:"):]
    # strip a trailing thinking block if the model emitted one after
    markers = ("\n\n[END]", "\n\n<")
    for mk in markers:
        idx = text.find(mk)
        if idx > 0:
            text = text[:idx]
    text = _strip_thinking(text)
    text = _strip_instruction_echo(text)
    return text.strip()[:max_chars]


def merge_summary(
    old: Optional[str],
    new: str,
    max_chars: int = DEFAULT_MAX_SUMMARY_CHARS,
) -> str:
    """Merge a new summary with the running one (prefer the new one if
    it's non-empty and different; otherwise keep old)."""
    if new and new != old:
        return new[:max_chars]
    return (old or "")[:max_chars]


def should_compact(
    messages: List[Dict[str, Any]],
    compact_every_turns: int = DEFAULT_COMPACT_EVERY_TURNS,
    threshold_tokens: int = 12000,
    turns_estimate: Optional[int] = None,
) -> bool:
    """Decide when to compact:
    - every N user turns, OR
    - when estimated tokens exceed the threshold.
    """
    if turns_estimate is not None and turns_estimate >= compact_every_turns:
        return True
    return estimate_tokens(messages) >= threshold_tokens


def rebuild_messages_with_summary(
    messages: List[Dict[str, Any]],
    summary: str,
    system_role: str = "system",
    system_hint: str = (
        "You are a helpful assistant. Answer in Thai, concise. "
        "\n\n[SUMMARY OF THIS CONVERSATION]\n"
    ),
) -> List[Dict[str, Any]]:
    """Replace history with: [system prompt + running summary] + tail
    (last user + assistant turn kept so the model can continue where it
    left off)."""
    if not messages:
        return []
    # keep the original system message if it exists (first), else build one
    base = messages[0] if messages and messages[0].get("role") == system_role else {
        "role": system_role, "content": ""
    }
    base = dict(base)
    # merge summary into the system content (preserve any existing text)
    prev_sys = base.get("content") or ""
    base["content"] = (prev_sys.rstrip() + "\n\n" + system_hint + summary).strip()

    # tail: last user + assistant (if both exist)
    tail: List[Dict[str, Any]] = []
    for m in messages[-2:]:
        if m.get("role") in ("user", "assistant"):
            tail.append(m)
    return [base] + tail


class ConversationSummarizer:
    """Server-side summarizer that calls the loaded model via ModelManager."""

    def __init__(
        self,
        manager: Any,
        summary_max_tokens: int = DEFAULT_SUMMARY_MAX_TOKENS,
        max_summary_chars: int = DEFAULT_MAX_SUMMARY_CHARS,
        temperature: float = 0.2,
    ):
        self._manager = manager
        self._summary_max_tokens = summary_max_tokens
        self._max_summary_chars = max_summary_chars
        self._temperature = temperature

    async def summarize(
        self,
        messages: List[Dict[str, Any]],
        model_id: str,
        existing_summary: Optional[str] = None,
    ) -> str:
        """Produce/refresh a running summary. Returns the summary string
        (empty on failure — caller keeps the old one)."""
        prompt = build_summary_prompt(messages, existing_summary)
        try:
            result = await self._manager.chat_completion(
                model_id=model_id,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=self._summary_max_tokens,
                temperature=self._temperature,
                top_p=0.95,
                reasoning_mode="off",  # summary should be fast + factual
                tools=None,
            )
            output = result.get("output") or ""
            return extract_summary(output, self._max_summary_chars)
        except Exception as e:  # never break the chat because of summary
            logger.warning("ConversationSummarizer failed: %s", e)
            return ""

    def compact(
        self,
        messages: List[Dict[str, Any]],
        summary: str,
    ) -> List[Dict[str, Any]]:
        """Stateless helper: merge running summary into the message list."""
        return rebuild_messages_with_summary(messages, summary)