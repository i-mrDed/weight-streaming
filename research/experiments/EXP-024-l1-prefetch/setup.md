# EXP-024 — Setup & Method (L1 Prefetch A/B)

## Environment
- **Server:** `python -m weight_stream.server --port 8766` + `WS_LLAMA_BACKEND_PORT=8806`
  (พอร์ตแยกจากระบบอื่นที่ใช้ 8765/8805 — PR #1 `31c099f`)
- **Model:** `~/models/UD-IQ3_XXS\DeepSeek-V4-Flash-0731-UD-IQ3_XXS-0000N-of-00004.gguf` (97.05GB)
- **Load:** shard1 path (split-aware) · n_ctx 2048/1024 · threads 8/6 · t 100/80 tokens · reasoning off

## Protocol (E2b-v2 — แก้จาก E2 ที่ bias)
```
unload model → drop standby cache (memory pressure, alloc ≥ 15GB = ผ่าน)
→ load 97GB → warmup 6-8 tokens → cold sample → warm sample
```
- Drop cache: memory-pressure (alloc 70–85% ของ free RAM บังคับ OS trim standby) — admin ไม่ต้องใช้ EmptyStandbyList (ไม่อยู่ใน download server แล้ว)
- Delay 6s หลัง drop ให้ OS settle
- Guard: alloc < 15GB → โยน warning (cache ไม่แน่ใจว่า cold)

## Prefetch worker
- ข้อมูล: `GGUFSplitParser.get_expert_map_global()` (33,024 expert ranges + 6 shared tensors)
- วิธี: เปิด shards read-only → อ่าน shared ครั้งเดียว (869MB) → round-robin expert ranges ตาม global offset
- Batch: 64KB · Rate-limit: 300 (ต่ำ) / 700 (เต็ม) MB/s
- อยู่ process เดียวกับ bench script (ไม่ใช่ server) — อ่านเองผ่าน mmap/read

## Metrics (จาก /v1/stats)
- `tokens_per_sec` · `faults_per_token` (paging) · drop GB ที่ได้

## Gate
- ✅ G0 ผ่าน (E1: random wall 35–183×; E3: layout ต่อเนื่อง)
- ❌ G1 ไม่ผ่าน (faults ลด ≤ 20% / เพิ่ม 69% ที่สเปคเต็ม; tok/s ลด 10–42% ทุกรอบ) → CLOSED

## Scripts (อยู่ใน temp, ยังไม่เข้า repo)
- `e1_nvme_bench.py` — NVMe random vs sequential
- `e3_gguf_reader.py` / `e3b_real_shard2.py` / `e3c_contiguity.py` — GGUF layout
- `e2_readahead.py` / `e2b_v2.py` — prefetch A/B (protocol ถูก)
- `drop_cache.py` (NtSetSystemInformation — privilege policy บล็อก) / `drop_cache_pressure.py` (memory pressure — ใช้ได้) / `drop_cache.ps1` (C# version)

> ⚠️ ควรย้าย scripts เหล่านี้เข้าสู่ `scripts/` ของ repo ในงานถัดไป (ทำความสะอาด) ก่อนเปิดทาง A