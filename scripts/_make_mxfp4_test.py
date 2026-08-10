"""Build a minimal qwen3 GGUF with MXFP4 (type 39) FFN tensors.

Purpose: prove that llama-server b9967 (llama.cpp bb7049f7) can LOAD MXFP4
tensors — the deciding question for DS V4 Flash MXFP4 variants on this rig.

Tensor shapes mirror src/models/qwen3.cpp @ bb7049f7 exactly:
  tok_embd/output     {n_embd, n_vocab}
  attn q/k/v/out      {n_embd, n_embd}            (MHA: head_count_kv == head_count)
  attn k/q norm       {n_embd_head_k}              (= n_embd/n_head = 8)
  ffn gate/up         {n_embd, n_ff}
  ffn down            {n_ff, n_embd}
  norms               {n_embd}

GGUF v3 layout: magic, version, tensor_count, kv_count, KVs, tensor infos,
32-byte aligned data section. Dims stored in ne[0..] order (matches C++ call).
"""
import struct

OUT = "scripts/.test_mxfp4.gguf"

# --- GGML types (ggml.h @ bb7049f7) ---
F32 = 0
F16 = 1
I32 = 4
MXFP4 = 39  # GGML_TYPE_MXFP4

# GGUF value types
T_U32 = 4
T_I32 = 5
T_F32 = 6
T_STR = 8
T_ARR = 9

N_EMBD = 128
N_VOCAB = 263  # 7 specials/normal + 256 byte-fallback
N_HEAD = 16
N_FF = 512
HEAD_DIM = N_EMBD // N_HEAD  # 8


def s(x: str) -> bytes:
    b = x.encode()
    return struct.pack("<Q", len(b)) + b


def kv_str(key: str, val: str) -> bytes:
    return s(key) + struct.pack("<I", T_STR) + s(val)


def kv_u32(key: str, val: int) -> bytes:
    return s(key) + struct.pack("<I", T_U32) + struct.pack("<I", val)


def kv_f32(key: str, val: float) -> bytes:
    return s(key) + struct.pack("<I", T_F32) + struct.pack("<f", val)


def kv_arr_str(key: str, items: list) -> bytes:
    out = s(key) + struct.pack("<I", T_ARR) + struct.pack("<I", T_STR) + struct.pack("<Q", len(items))
    for it in items:
        out += s(it)
    return out


def kv_arr_f32(key: str, items: list) -> bytes:
    out = s(key) + struct.pack("<I", T_ARR) + struct.pack("<I", T_F32) + struct.pack("<Q", len(items))
    for it in items:
        out += struct.pack("<f", it)
    return out


def kv_arr_i32(key: str, items: list) -> bytes:
    out = s(key) + struct.pack("<I", T_ARR) + struct.pack("<I", T_I32) + struct.pack("<Q", len(items))
    for it in items:
        out += struct.pack("<i", it)
    return out


def tensor_info(name: str, dims: list, ttype: int, offset: int) -> bytes:
    out = s(name) + struct.pack("<I", len(dims))
    for d in dims:
        out += struct.pack("<Q", d)
    out += struct.pack("<I", ttype) + struct.pack("<Q", offset)
    return out


def tensor_data(ttype: int, n_elems: int) -> bytes:
    """Zero-filled data. F32: n*4 bytes. MXFP4: ceil(n/32)*17 bytes."""
    if ttype == F32:
        return b"\x00" * (n_elems * 4)
    if ttype == MXFP4:
        n_blocks = (n_elems + 31) // 32
        return b"\x00" * (n_blocks * 17)
    raise ValueError(ttype)


def build() -> None:
    # SPM vocab: specials + normal tokens + byte-fallback tokens (0x00..0xFF)
    toks = ["<unk>", "<s>", "</s>", "\n", "a", "b", "c"]
    tok_types = [2, 3, 3, 1, 1, 1, 1]
    for i in range(256):
        toks.append(f"<0x{i:02X}>")
        tok_types.append(6)
    kv_list = [
        kv_str("general.architecture", "qwen3"),
        kv_str("general.name", "mxfp4-test"),
        kv_u32("general.file_type", 38),  # LLAMA_FTYPE_MOSTLY_MXFP4_MOE
        kv_u32("qwen3.block_count", 1),
        kv_u32("qwen3.context_length", 256),
        kv_u32("qwen3.embedding_length", N_EMBD),
        kv_u32("qwen3.feed_forward_length", N_FF),
        kv_u32("qwen3.attention.head_count", N_HEAD),
        kv_u32("qwen3.attention.head_count_kv", N_HEAD),
        kv_f32("qwen3.attention.layer_norm_rms_epsilon", 1e-6),
        kv_u32("qwen3.rope.dimension_count", HEAD_DIM),
        kv_f32("qwen3.rope.freq_base", 1000000.0),
        kv_str("tokenizer.ggml.model", "llama"),
        kv_arr_str("tokenizer.ggml.tokens", toks),
        kv_arr_f32("tokenizer.ggml.scores", [0.0] * len(toks)),
        kv_arr_i32("tokenizer.ggml.token_type", tok_types),
        kv_u32("tokenizer.ggml.bos_token_id", 1),
        kv_u32("tokenizer.ggml.eos_token_id", 2),
    ]
    kvs = b"".join(kv_list)

    # (name, dims, type) — file order
    tensors = [
        ("token_embd.weight", [N_EMBD, N_VOCAB], F32),
        ("output_norm.weight", [N_EMBD], F32),
        ("output.weight", [N_EMBD, N_VOCAB], F32),
        ("blk.0.attn_norm.weight", [N_EMBD], F32),
        ("blk.0.attn_q.weight", [N_EMBD, N_EMBD], F32),
        ("blk.0.attn_k.weight", [N_EMBD, N_EMBD], F32),
        ("blk.0.attn_v.weight", [N_EMBD, N_EMBD], F32),
        ("blk.0.attn_output.weight", [N_EMBD, N_EMBD], F32),
        ("blk.0.attn_k_norm.weight", [HEAD_DIM], F32),
        ("blk.0.attn_q_norm.weight", [HEAD_DIM], F32),
        ("blk.0.ffn_norm.weight", [N_EMBD], F32),
        ("blk.0.ffn_gate.weight", [N_EMBD, N_FF], MXFP4),
        ("blk.0.ffn_down.weight", [N_FF, N_EMBD], MXFP4),
        ("blk.0.ffn_up.weight", [N_EMBD, N_FF], MXFP4),
    ]

    header = b"GGUF" + struct.pack("<I", 3) + struct.pack("<Q", len(tensors)) + struct.pack("<Q", len(kv_list))

    # GGUF tensor offsets are RELATIVE to the data-section start (first = 0).
    infos = b""
    data_offset = 0
    for name, dims, ttype in tensors:
        infos += tensor_info(name, dims, ttype, data_offset)
        n_elems = 1
        for d in dims:
            n_elems *= d
        size = len(tensor_data(ttype, n_elems))
        data_offset += (size + 31) // 32 * 32

    body = header + kvs + infos
    pad = (-len(body)) % 32
    body += b"\x00" * pad

    with open(OUT, "wb") as f:
        f.write(body)
        for name, dims, ttype in tensors:
            n_elems = 1
            for d in dims:
                n_elems *= d
            data = tensor_data(ttype, n_elems)
            f.write(data)
            if len(data) % 32:
                f.write(b"\x00" * (32 - len(data) % 32))

    print(f"wrote {OUT}: {len(body) + sum(len(tensor_data(t, 1)) for t in [0])} bytes (data follows header)")
    import os
    print(f"  total file size = {os.path.getsize(OUT)} bytes")


if __name__ == "__main__":
    build()
