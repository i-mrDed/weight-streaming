"""
Model capability detection (P7.1a).

Determines what a GGUF model can do — reasoning (extended thinking),
tool calling, and vision — from its metadata + name heuristics.

Why this matters (P7): the console must only show controls a model can
actually use (e.g. the brain toggle for reasoning models only, like Jan).
Honest capability labels: detection is heuristic, never a guarantee —
a model may be *capable* but weak at a task. The UI shows the label as
"detected", not "guaranteed".

Detection sources (in priority order):
1. GGUF metadata: `general.architecture` (e.g. qwen35, deepseek2, qwen2vl)
2. GGUF metadata: `general.name` (model family keywords)
3. Chat template markers (thinking tags / tool-call tags)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

# ── Reasoning-capable architectures (extended thinking / CoT) ─────────
# qwen35 = Qwen3.5 family (Qwythos, Ornith, etc. are qwen35 fine-tunes)
_REASONING_ARCHS = {
    "qwen35", "qwen3", "deepseek2", "deepseek3", "deepseek-r1",
    "qwq", "glm4", "kimi", "moonshot",
}

# ── Vision-capable architectures ───────────────────────────────────────
_VISION_ARCHS = {
    "qwen2vl", "qwen2.5vl", "qwen3vl", "llava", "llava16", "llava17",
    "minicpmv", "internvl", "phi3v", "gemma3", "qwen35vl",
}

# ── Model-name keywords → capability hints ─────────────────────────────
_NAME_REASONING = (
    "r1", "qwq", "thinking", "reason", "mythos", "ornith", "qwythos",
    "deepseek", "kimi", "glm-z1", "glm-z", "qwen3", "qwen35",
)
_NAME_VISION = ("vl", "vision", "llava", "minicpm-v", "internvl", "gemma3")
_NAME_TOOLS = ("tool", "function", "agent", "hermes", "mistral", "qwen", "glm")

# ── Chat-template markers ──────────────────────────────────────────────
_TEMPLATE_THINKING = ("<|thinking|>", " thinking", "reasoning", "chain-of-thought")
_TEMPLATE_TOOLS = ("<|tool_call|>", "tool_call", "function_call", "<tool_call>", "get_function_calls")


@dataclass
class ModelCapabilities:
    """Detected capabilities of a model (heuristic — honest labels)."""
    reasoning: bool = False
    tools: bool = False
    vision: bool = False
    arch: str = ""
    name: str = ""
    detection: str = "unknown"  # which source drove the decision
    hints: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "reasoning": self.reasoning,
            "tools": self.tools,
            "vision": self.vision,
            "arch": self.arch,
            "name": self.name,
            "detection": self.detection,
            "hints": self.hints,
        }


def detect_capabilities(
    arch: str = "",
    name: str = "",
    chat_template: str = "",
) -> ModelCapabilities:
    """Detect model capabilities from available metadata (all optional).

    Args:
        arch: GGUF `general.architecture` (e.g. "qwen35", "deepseek2").
        name: GGUF `general.name` (e.g. "Qwythos 9B Claude Mythos").
        chat_template: GGUF `tokenizer.chat_template` (may be empty).

    Returns:
        ModelCapabilities with heuristic flags + detection source.
    """
    arch_l = (arch or "").lower()
    name_l = (name or "").lower()
    template_l = (chat_template or "").lower()
    caps = ModelCapabilities(arch=arch, name=name)
    hints: list[str] = []

    # 1. Architecture-based detection (strongest signal)
    if arch_l in _REASONING_ARCHS:
        caps.reasoning = True
        hints.append(f"arch:{arch_l}")
    if arch_l in _VISION_ARCHS:
        caps.vision = True
        hints.append(f"arch:{arch_l}")

    # 2. Name-based detection (fine-tunes keep base arch but change name)
    if not caps.reasoning:
        for kw in _NAME_REASONING:
            if kw in name_l:
                caps.reasoning = True
                hints.append(f"name:{kw}")
                break
    if not caps.vision:
        for kw in _NAME_VISION:
            if kw in name_l:
                caps.vision = True
                hints.append(f"name:{kw}")
                break
    if not caps.tools:
        for kw in _NAME_TOOLS:
            if kw in name_l:
                caps.tools = True
                hints.append(f"name:{kw}")
                break

    # 3. Chat-template markers (thinking tags / tool-call tags)
    if template_l:
        if any(m in template_l for m in _TEMPLATE_THINKING):
            caps.reasoning = True
            hints.append("template:thinking")
        if any(m in template_l for m in _TEMPLATE_TOOLS):
            caps.tools = True
            hints.append("template:tools")

    # Detection source label (honest)
    if hints:
        caps.detection = ",".join(hints[:3])
    else:
        caps.detection = "unknown"
    caps.hints = hints
    return caps


def detect_from_parser(parser) -> ModelCapabilities:
    """Detect capabilities from an open GGUFParser instance.

    Reads `general.architecture` + `general.name` from parser metadata.
    Chat template is not exposed by the parser, so template markers are
    skipped here (name/arch heuristics still apply).
    """
    md = getattr(parser, "metadata", None) or {}
    arch = str(md.get("general.architecture", ""))
    name = str(md.get("general.name", ""))
    return detect_capabilities(arch=arch, name=name)
