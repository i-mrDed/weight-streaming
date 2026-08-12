"""Tests for ConversationSummarizer (context-management POC)."""
import pytest

from weight_stream.server.conversation_summary import (
    ConversationSummarizer,
    build_summary_prompt,
    estimate_tokens,
    extract_summary,
    merge_summary,
    rebuild_messages_with_summary,
    should_compact,
)


class TestPure:
    def test_estimate_tokens(self):
        msgs = [{"role": "user", "content": "สวัสดี"}, {"role": "assistant", "content": "hello"}]
        assert estimate_tokens(msgs) > 0
        assert estimate_tokens([]) == 0

    def test_build_summary_prompt_includes_facts_instruction(self):
        p = build_summary_prompt([{"role": "user", "content": "A"}])
        assert "SUMMARY" in p
        assert "ข้อเท็จจริง" in p

    def test_build_summary_prompt_carries_old(self):
        p = build_summary_prompt(
            [{"role": "user", "content": "A"}], existing_summary="OLDSUM")
        assert "OLDSUM" in p

    def test_build_summary_prompt_carry_instructs_no_echo(self):
        # With an existing summary the prompt must instruct the model to
        # answer directly (no step-by-step echo), and end with "SUMMARY:".
        p = build_summary_prompt(
            [{"role": "user", "content": "ใหม่"}], existing_summary="OLD")
        assert "ห้ามทวนคำสั่ง" in p
        assert "ห้ามอธิบายขั้นตอน" in p
        assert p.rstrip().endswith("SUMMARY:")

    def test_build_summary_prompt_fresh_no_carry(self):
        p = build_summary_prompt([{"role": "user", "content": "A"}])
        assert "ห้ามทวนคำสั่ง" in p
        assert p.rstrip().endswith("SUMMARY:")

    def test_extract_summary(self):
        assert extract_summary("SUMMARY: เนื้อหา") == "SUMMARY: เนื้อหา"
        assert extract_summary("blah\nSUMMARY: x") == "SUMMARY: x"
        assert extract_summary("no marker") == "no marker"

    def test_extract_summary_strips_instruction_echo(self):
        # Qwythos sometimes restates the instruction in English first.
        s = ('SUMMARY:" and not include any explanations or repetitions of '
             'instructions.\n2. **Extract key facts:**\n'
             '* *Name:* คุณนายแดง\n* *Project:* weight-streaming\n'
             'สรุป: คุณนายแดง ทำงานกับโปรเจค weight-streaming')
        out = extract_summary(s)
        assert "explanations" not in out.lower()
        assert "คุณนายแดง" in out

    def test_extract_summary_keeps_clean_input(self):
        s = "SUMMARY:\n- ชื่อ: คุณนายแดง\n- โปรเจค: weight-streaming"
        out = extract_summary(s)
        assert out.startswith("SUMMARY:")
        assert "คุณนายแดง" in out

    def test_extract_summary_limits(self):
        s = extract_summary("SUMMARY: " + "x" * 10000, max_chars=500)
        assert len(s) <= 500

    def test_merge_summary_prefers_new(self):
        assert merge_summary("old", "new") == "new"
        assert merge_summary("old", "") == "old"
        assert merge_summary("old", "old") == "old"

    def test_should_compact_by_turns(self):
        assert should_compact([], compact_every_turns=2, turns_estimate=2) is True
        assert should_compact([], compact_every_turns=2, turns_estimate=1) is False

    def test_should_compact_by_tokens(self):
        msgs = [{"role": "user", "content": "x" * 20000}]
        assert should_compact(msgs, threshold_tokens=12000) is True

    def test_rebuild_keeps_system_and_tail(self):
        msgs = [
            {"role": "system", "content": "SYS"},
            {"role": "user", "content": "U1"},
            {"role": "assistant", "content": "A1"},
            {"role": "user", "content": "U2"},
            {"role": "assistant", "content": "A2"},
        ]
        new = rebuild_messages_with_summary(msgs, "SUMMARY-TEXT")
        assert new[0]["role"] == "system"
        assert "SUMMARY-TEXT" in new[0]["content"]
        assert "SYS" in new[0]["content"]
        # tail = last user + assistant
        roles = [m["role"] for m in new[1:]]
        assert roles == ["user", "assistant"]
        assert new[-1]["content"] == "A2"


class _FakeManager:
    """Minimal stand-in for ModelManager.chat_completion."""

    def __init__(self, output="SUMMARY: fake summary"):
        self._out = output
        self.calls = []

    async def chat_completion(self, **kwargs):
        self.calls.append(kwargs)
        return {"output": self._out, "tokens_generated": 10}


class TestSummarizer:
    @pytest.mark.asyncio
    async def test_summarize_ok(self):
        mgr = _FakeManager("SUMMARY: hello summary")
        svc = ConversationSummarizer(mgr)
        out = await svc.summarize(
            [{"role": "user", "content": "hi"}], model_id="m")
        assert "hello summary" in out
        assert mgr.calls[0]["reasoning_mode"] == "off"

    @pytest.mark.asyncio
    async def test_summarize_failure_returns_empty(self):
        class Boom:
            async def chat_completion(self, **kwargs):
                raise RuntimeError("boom")

        svc = ConversationSummarizer(Boom())
        out = await svc.summarize([{"role": "user", "content": "x"}], model_id="m")
        assert out == ""

    def test_compact(self):
        svc = ConversationSummarizer(_FakeManager())
        msgs = [{"role": "user", "content": "U"}, {"role": "assistant", "content": "A"}]
        new = svc.compact(msgs, "SUMMARY-X")
        assert "SUMMARY-X" in new[0]["content"]