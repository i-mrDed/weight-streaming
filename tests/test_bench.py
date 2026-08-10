"""Offline tests for the weight_stream.bench harness (no server, no GPU).

Covers the pure logic: question set integrity, think-splitting, cmdline
verification, /v1/stats shape normalization, the quality-gate flow (with a
fake HTTP transport), and report formatting.
"""

from weight_stream.bench import measure, report, split_think, thai


# ── thai: question set + think splitting ───────────────────────────────


def test_question_set_has_9_fixed_questions_with_unique_ids():
    ids = [qid for qid, _ in thai.QUESTIONS]
    assert len(thai.QUESTIONS) == 9
    assert len(set(ids)) == 9
    for qid, q in thai.QUESTIONS:
        assert qid and q.strip()


def test_split_think_with_think_block():
    content = "<think>let me reason carefully</think>Final answer here."
    think, final = split_think(content)
    assert think == "let me reason carefully"
    assert final == "Final answer here."


def test_split_think_no_think_block():
    think, final = split_think("plain answer")
    assert think == ""
    assert final == "plain answer"


def test_quality_gate_truncates_think_to_400_chars():
    class _LongThinkHttp:
        def __call__(self, method, path, body=None):
            if path == "/v1/chat/completions":
                return {"choices": [{"message": {"content": "<think>" + "x" * 500 + "</think>done"}}]}
            if path == "/v1/stats":
                return {"models": {}}
            raise AssertionError(f"unexpected request: {method} {path}")

    gate = thai.run_quality_gate("http://x", "bench", http=_LongThinkHttp())
    think = gate["answers"]["fact_thai"]["think"]
    assert len(think) == 400


# ── thai: quality gate with fake transport ─────────────────────────────


class _FakeHttp:
    """Stand-in for the urllib transport: chat completions echo the prompt,
    /v1/stats returns a fixed tok/s."""

    def __init__(self):
        self.chat_calls = 0
        self.stats_calls = 0

    def __call__(self, method, path, body=None):
        if path == "/v1/chat/completions":
            self.chat_calls += 1
            return {
                "choices": [{"message": {"content": f"answer:{body['messages'][0]['content'][:6]}"}}]
            }
        if path == "/v1/stats":
            self.stats_calls += 1
            return {
                "models": {
                    "bench": {"generation": {"tokens_per_sec": 42.0}},
                }
            }
        raise AssertionError(f"unexpected request: {method} {path}")


def test_run_quality_gate_asks_all_questions_and_reads_stats():
    http = _FakeHttp()
    gate = thai.run_quality_gate("http://x", "bench", http=http)
    assert http.chat_calls == 9
    assert http.stats_calls == 1
    assert gate["tok_s"] == 42.0
    assert set(gate["answers"]) == {qid for qid, _ in thai.QUESTIONS}
    assert gate["answers"]["fact_thai"]["final"].startswith("answer:")


# ── measure: cmdline verification ──────────────────────────────────────


def test_verify_extra_args_passes_when_all_present():
    cmd = "llama-server.exe -m model.gguf -t 8 -fa on --cpu-moe"
    assert measure.verify_extra_args(cmd, "--cpu-moe -fa on -t 8") == []


def test_verify_extra_args_detects_missing_flag():
    cmd = "llama-server.exe -m model.gguf -t 8"
    problems = measure.verify_extra_args(cmd, "--cpu-moe -t 8")
    assert any("missing" in p for p in problems)


def test_verify_extra_args_detects_value_override():
    # Presence-only check would pass (-t is there); value check must catch
    # the silent drop from 16 back to 8.
    cmd = "llama-server.exe -m model.gguf -t 8"
    problems = measure.verify_extra_args(cmd, "--cpu-moe -t 16")
    assert any("-t=8, expected -t=16" in p for p in problems)


def test_verify_extra_args_last_occurrence_wins():
    # Load request emits -t 8 BEFORE extra args; llama.cpp keeps the last.
    cmd = "llama-server.exe -m model.gguf -t 8 -t 16"
    assert measure.verify_extra_args(cmd, "-t 16") == []


# ── measure: /v1/stats shape normalization ─────────────────────────────


def test_normalize_stats_keyed_shape():
    raw = {
        "models": {
            "bench": {
                "generation": {
                    "tokens_per_sec": 12.3,
                    "elapsed": 9.7,
                    "token_count": 120,
                    "paging": {"faults_per_token": 500, "disk_mb_per_token": 2.0},
                },
                "gpu": {"n_gpu_layers": 99, "used_vram_mb": 8000,
                        "total_vram_mb": 12288},
            }
        }
    }
    s = measure.normalize_stats(raw, "bench")
    assert s["tok_s"] == 12.3
    assert s["faults_per_token"] == 500
    assert s["disk_mb_per_token"] == 2.0
    assert s["used_vram_mb"] == 8000


def test_normalize_stats_direct_shape_with_query_param():
    # ?model=<id> returns the model's dict DIRECTLY under models.
    raw = {
        "models": {
            "generation": {"tokens_per_sec": 7.5, "paging": {}},
            "gpu": {},
        }
    }
    s = measure.normalize_stats(raw, "bench")
    assert s["tok_s"] == 7.5
    assert s["faults_per_token"] is None  # missing paging -> None, no crash


# ── report ─────────────────────────────────────────────────────────────


def _fake_matrix_result():
    return [
        {
            "config": "cpu-moe t8", "extra_args": "--cpu-moe -fa on -t 8",
            "flag_in_cmdline": True,
            "cold": {"tok_s": 1.5, "faults_per_token": 40000,
                     "disk_mb_per_token": 150.0},
            "warm": {"tok_s": 1.9, "faults_per_token": 100,
                     "disk_mb_per_token": 0.4, "used_vram_mb": 6000},
        },
        {
            "config": "oom config", "extra_args": "--n-cpu-moe 0",
            "flag_in_cmdline": False, "error": "CUDA out of memory",
        },
    ]


def test_matrix_to_markdown_includes_cold_warm_and_error_rows():
    md = report.matrix_to_markdown(_fake_matrix_result(), "model.gguf")
    assert "**cpu-moe t8**" in md
    assert "1.50" in md  # cold tok/s
    assert "40000 / 150.00" in md  # cold faults / disk MB
    assert "1.90" in md  # warm tok/s
    assert "6000 MiB" in md  # VRAM
    assert "❌ CUDA out of memory" in md  # honest failure row


def test_matrix_to_json_round_trips():
    import json

    text = report.matrix_to_json(_fake_matrix_result(), "m.gguf")
    parsed = json.loads(text)
    assert parsed["harness"] == "weight_stream.bench"
    assert len(parsed["results"]) == 2
