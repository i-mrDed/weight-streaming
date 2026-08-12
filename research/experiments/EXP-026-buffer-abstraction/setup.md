# EXP-026: Streaming Buffer Abstraction Prototype

**วันที่:** 2026-08-13
**สถานะ:** ✅ Complete (TASKS.md #145)
**Workflow:** `streaming-buffer-prototype` (MongoModel, rev 35)

---

## ปัญหา (open gap — ARCHITECTURE.md §0)

`StreamingBuffer.total_accesses = 0` ระหว่าง real inference — tracker
ไม่เห็นอะไรเลย เพราะ llama.cpp อ่าน mmap แบบ opaque (ADR-003 no-fork:
ไม่ intercept การอ่าน)

## ทางออก

สร้าง abstraction กลางที่เชื่อมสองโลก:

1. **Simulator-backed** — `SimulatorBufferAdapter` หุ้ม `StreamingBuffer`
   เดิม (LRU/LFU/priority) โดยไม่เปลี่ยนพฤติกรรม
2. **Telemetry-backed** — `TelemetryBufferObserver` แปลง OS signals ที่
   ship อยู่แล้ว (`generation.paging`: faults_per_token, disk_mb_per_token;
   spike data) เป็น buffer-equivalent stats

ทั้งสอง implement `BufferBackend` protocol เดียวกัน → คืน `BufferStatsView`
ชุดเดียวกัน → ใช้ calibrated BW จาก EXP-025 (cpu-ram 19.18, disk-mmap
0.38 GB/s) คำนวณ predicted tok/s

## ไฟล์

- `simulator/buffer_abstraction.py` — protocol + 2 implementations + helper
- `simulator/buffer_demo.py` — demo เทียบสองทาง
- `tests/test_buffer_abstraction.py` — hermetic tests (9 ตัว)
