"""
Synthetic GGUF fixtures for hermetic parser tests.

Builds tiny, valid GGUF files with the *same tensor names and shape
conventions* as the real models the parsers were written against, so the
tests exercise the real code paths (expert detection, per-expert offset
maps, split-shard global offsets) without needing multi-GB model files.

Key detail — GGUF byte shapes for quantized tensors:
    The `gguf` writer takes a data array whose last dim is a *byte* count
    and converts it to a quant shape (`last // type_size * block_size`)
    before storing dims **reversed** on disk.  So to make the reader report
    `shape == (rows, cols_bytes, n_experts)` — which is what the parsers
    use for `n_experts = shape[-1]` — we pass data shaped
    `(n_experts, cols_bytes, rows)`.
"""
from pathlib import Path

import numpy as np
from gguf import GGUFWriter
from gguf.constants import GGMLQuantizationType

# Q4_K: block_size=256 weights, type_size=144 bytes per block.
# One block per expert per row: cols_bytes = 144, rows must be a multiple
# of 144 → rows = 288. Reader reports shape (512, 144, N_EXPERTS).
Q4K_EXPERT_SHAPE = (4, 144, 288)

BASE_SHARD = "DeepSeek-V4-Flash-0731-SYNTH-{n}-of-00004.gguf"

#: Metadata shared by both fixtures (mirrors the real models' KV keys).
MOE_META = dict(
    block_count=2,
    expert_count=4,
    expert_used_count=2,
    context_length=4096,
    embedding_length=64,
    feed_forward_length=256,
    file_type=15,
)

EXPERT_PROJECTIONS = ("gate", "up", "down")


def _write_gguf(path: Path, arch: str, name: str, meta: dict, tensors: list) -> None:
    """Write one GGUF file. `tensors` = [(name, ndarray, raw_dtype|None)]."""
    h = GGUFWriter(str(path), arch, endianess="little")
    h.add_name(name)
    h.add_quantization_version(2)
    h.add_custom_alignment(32)
    for key, value in meta.items():
        getattr(h, f"add_{key}")(value)
    for tensor_name, data, raw_dtype in tensors:
        h.add_tensor(tensor_name, data, raw_dtype=raw_dtype)
    h.write_header_to_file(str(path))
    h.write_kv_data_to_file()
    h.write_tensors_to_file()
    h.close()


def _expert_tensor(blk: int, proj: str):
    return (
        f"blk.{blk}.ffn_{proj}_exps.weight",
        np.zeros(Q4K_EXPERT_SHAPE, dtype=np.uint8),
        GGMLQuantizationType.Q4_K,
    )


def build_qwen2moe(path: Path) -> Path:
    """Single-file MoE model (mirrors research/models/Qwen1.5-MoE-A2.7B)."""
    tensors = [
        ("token_embd.weight", np.zeros((32, 64), dtype=np.float16), None),
        ("output.weight", np.zeros((32, 64), dtype=np.float16), None),
        ("blk.0.attn_q.weight", np.zeros((16, 32), dtype=np.float16), None),
        ("blk.0.ffn_gate.weight", np.zeros((16, 32), dtype=np.float16), None),
    ]
    for blk in (0, 1):
        for proj in EXPERT_PROJECTIONS:
            tensors.append(_expert_tensor(blk, proj))
    _write_gguf(path, "qwen2moe", "Synthetic-Qwen2MoE", MOE_META, tensors)
    return path


def build_dsv4_shards(dir_path: Path) -> list[Path]:
    """Four tiny shards (mirrors the DS V4 Flash 4-shard UD-IQ3_XXS)."""
    # Every shard carries the full KV set: the split parser takes metadata
    # from the first shard with >5 fields, and even "data-only" shards get
    # arch/name/quantization_version/alignment from the writer.
    f16_2d = np.zeros((32, 64), dtype=np.float16)
    e3 = np.zeros(Q4K_EXPERT_SHAPE, dtype=np.uint8)
    q4k = GGMLQuantizationType.Q4_K

    shards = {
        1: [("token_embd.weight", f16_2d, None)],
        2: [("output.weight", f16_2d, None),
            ("blk.0.ffn_gate_exps.weight", e3, q4k)],
        3: [("blk.0.ffn_up_exps.weight", e3, q4k),
            ("blk.0.ffn_down_exps.weight", e3, q4k)],
        4: [("blk.1.ffn_gate_exps.weight", e3, q4k),
            ("blk.1.ffn_up_exps.weight", e3, q4k),
            ("blk.1.ffn_down_exps.weight", e3, q4k)],
    }

    paths = []
    for n in sorted(shards):
        path = dir_path / BASE_SHARD.format(n=f"{n:05d}")
        _write_gguf(path, "deepseek4", "Synthetic-DSV4", MOE_META, shards[n])
        paths.append(path)
    return paths
