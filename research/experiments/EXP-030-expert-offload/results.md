# EXP-030 — Results: expert offloading on Qwen (fits VRAM)

**Date:** 2026-08-13 · **Machine:** i9-9900KF + RTX 3060 12 GB + 64 GB
RAM · **Model:** Qwen1.5-MoE-A2.7B Q2_K (5.88 GB, fits 12 GB VRAM)

## Raw measurements (3 runs × 100 tokens, warm)

| config | run1 | run2 | run3 | **avg** |
|---|---:|---:|---:|---:|
| baseline (auto) | 128.18 | 83.92 | 112.73 | **108.28** |
| n-cpu-moe 10 | 23.58 | 38.32 | 33.35 | **31.75** |
| n-cpu-moe 0 (all GPU) | 127.62 | 125.78 | 126.52 | **126.64** |

## Findings

1. **Expert offloading ทำให้ช้าลง ~4× บนโมเดลที่พอดี VRAM:**
   n-cpu-moe 10 = 31.75 vs n-cpu-moe 0 = 126.64 tok/s (ratio 3.99×)
   — เพราะ experts ต้อง stream จาก RAM ข้าม PCIe แทนที่จะอ่านจาก VRAM
   (gpu-vram 61.09 vs cpu-ram 19.18 GB/s = gap 3.2×, EXP-025) + เพิ่ม
   page faults (run1: 8,878 vs 13.6 faults/tok)
2. **baseline (auto) ≠ all-GPU:** 108.28 vs 126.64 tok/s — server
   default placement วางบางส่วนไว้ CPU/ไม่เต็มที่ → **ต้องระบุ
   `--n-cpu-moe 0` อย่างชัดเจน** ถึงจะได้ full-VRAM speed (ตรง
   เซอร์ไพรส์เดิมของ EXP-012 ที่ n-cpu-moe 0 ดีกว่า auto)
3. **สอดคล้องกับ EXP-011 (35B >VRAM):** ที่นั่น n-cpu-moe 10 ≈ 47 vs
   n-cpu-moe 0 = 56–77 — offload ช่วยเฉพาะกรณีโมเดล **ไม่พอดี** VRAM
   (ต้อง stream อยู่แล้ว); พอดีแล้วมันเสียเปล่า

## Conclusion

ปิดงาน "Test llama.cpp expert offloading" (TASKS.md Phase 1):
- **กลไกใช้ได้** (injection + spawn + measure ผ่าน) — เหมือน EXP-005
- **บน PoC model (พอดี VRAM): offloading ไม่คุ้ม — ช้าลง 4×**
- **ข้อปฏิบัติ:** โหลดโมเดลพอดี VRAM ควรส่ง `--n-cpu-moe 0` เสมอ อย่า
  ปล่อย auto placement

## Verification

- `tests/test_expert_offload.py` 4/4 ผ่าน (physics: VRAM > RAM > disk;
  mixed offload slower; ratio ตรง EXP-030; gap 3.2×)
- Server คืน baseline แล้ว (reload ไม่มี extra args)
