# 🌐 P5.1 BRIEF — Hub: อุดมข้อมูลโมเดล + จัดกลุ่ม + ขนาดไฟล์ + shard-aware (จาก feedback ผู้ใช้)

> **สถานะ**: ปล่อยงานโดย PM (2026-08-01) หลังผู้ใช้ trial P5 บน 8799 แล้วแจ้ง feedback จริง · P1–P5 เขียวแล้ว · branch `feature/dashboard-theme` (HEAD `7369ddc`)
> **Source of truth**: `docs/DASHBOARD_THEME_SPEC.md` §9.6 + กฎ honest telemetry (ADR-003) · ไฟล์นี้คือ spec ของรอบแก้ (ถ้าขัดแย้ง spec หลัก ชนะ)
> **ลักษณะงาน**: **backend additive 1 endpoint + frontend Hub ยกแผง** — ไม่ใช่แค่ขัดผิว

---

## 📥 Feedback ผู้ใช้ (ต้นทางของงานนี้ — ต้องตอบโจทย์ทุกข้อ)

1. **การ์ดโมเดลชิดขอบเกินไป** — ขอจัด layout/padding ใหม่ให้อ่านสบาย
2. **ข้อมูลโมเดลมีแต่ชื่อ** — ขอทั้ง **สรุปย่อ + รายละเอียดเต็ม**: วันที่เผยแพร่/อัปเดต, จุดเด่น/ฟีเจอร์, ประสิทธิภาพ, รองรับ tools, context — เป็น "ไกด์ด่วน" ช่วยตัดสินใจเลือก
3. **จัดกลุ่ม/ประเภทโมเดล** — ใช้สี/ไอคอน/emoji แยกประเภท (เช่น code / chat / embedding / vision / MoE)
4. **Sidebar รายการไฟล์ไม่มีขนาด (MB/GB)** — ผู้ใช้ไม่กล้า download เพราะไม่รู้ขนาด
5. **สับสน shard `-00001-of-00004`** + **การ์ดแสดง "+4" แต่ sidebar มีเป็นสิบไฟล์** — ต้องอธิบาย/จัดกลุ่มให้ชัด

## 🔎 ข้อเท็จจริงที่ตรวจแล้ว (probe `/v1/hub/search` จริงบน 8799)

- HF search ปัจจุบันคืน: `repo_id, downloads (จริง), likes (null — HF search ไม่คืน), last_modified (null), gguf, files[{filename, quant, size_label}]` — **ไม่มี** created_at / tags / pipeline_tag / ขนาดไฟล์ (byte) / description → ต้องเพิ่มข้อมูล
- HF API (public, ไม่ต้อง auth) ที่ใช้เป็นข้อมูลเสริมได้:
  - `GET /api/models/{repo}` → `createdAt, lastModified, tags, pipeline_tag, library_name, downloads, likes, cardData (description/language/base_model…)`
  - `GET /api/models/{repo}/tree/main` → per-file `size` (bytes) + ระบุไฟล์ non-GGUF (README/imatrix/config)
- **Shard คืออะไร**: GGUF ตัวใหญ่ถูกหั่นเป็น `-NNNNN-of-MMMMM.gguf` (Git LFS จำกัด ~5GB/ไฟล์); shard `00001-of` มี header; **โหลดได้ต้องมีครบทุก shard ของ quant นั้นใน dir เดียวกัน**; fp16 = ไม่ quantize (ใหญ่มาก มักไม่ใช่ตัวที่อยากได้); repo มักปนหลาย quant + shard + imatrix

---

## 🎯 ขอบเขตงาน

### Backend (additive — เพิ่ม 1 endpoint, ไม่แก้ route เดิม)
**`GET /v1/hub/model/{repo_id:path}`** → on-demand detail (cache ~15 นาที, timeout, HF ล่ม→502 ซื่อๆ):
- aggregate จาก `GET /api/models/{repo}` + `GET /api/models/{repo}/tree/main` (stdlib urllib + asyncio.to_thread เหมือน search — **0 dep ใหม่**)
- payload เสนอ: `{ repo_id, author, published_at, updated_at, downloads, likes, pipeline_tag, tags[], library, description (จาก cardData/README ย่อ), context_length? (ถ้ามีใน tags/cardData — ไม่มี = null), files:[{filename, bytes, quant, size_label, shard:{index,total}|null}], non_gguf:[…], quants:[{quant, files:[…], total_bytes, sharded:bool, per_shard_bytes?}] }`
- **Search enrichment**: ตรวจว่า HF search raw response มี `tags/pipeline_tag` ไหม — ถ้ามี **pass-through** มายัง `/v1/hub/search` result ( frontend ใช้จัดกลุ่มได้โดยไม่ต้องเรียก detail)
- Honest: field ที่ HF ไม่มี = `null` (ห้ามเติม); description ไม่มี = บอก "ไม่มีคำอธิบาย"; likes null = ไม่แสดง

### Frontend (Hub page)
1. **Card layout ใหม่** — เว้นระยะ/จัด hierarchy (ชื่อ · author · category chip · badges · stats) ไม่ชิดขอบ; hover/micro-interaction พองามตาม design system เดิม
2. **Category chip** — จาก `pipeline_tag`/tags → สี + ไอคอน/emoji แยกประเภท (text-generation 💬 / code 💻 / embedding 🔢 / vision 👁 / audio 🎧 / MoE 🧩 ฯลฯ — fallback "อื่นๆ" ซื่อๆ) + tag badges (function-calling, vision, Thai…)
3. **Model detail** (drawer หรือ panel ตาม Drawer.tsx CONVENTION) — 2 ชั้น:
   - **สรุปย่อ (ไกด์ด่วน)**: ประเภท · วันที่เผยแพร่/อัปเดต · downloads · ขนาดพารามิเตอร์ · context (ถ้ามี) · RAM โดยประมาณต่อ quant (**คำนวณจาก bytes จริง** = ซื่อ) · ฟีเจอร์จาก tags (tools/function-calling/vision) · description ย่อ
   - **รายละเอียดเต็ม**: tags ครบ · base_model · ไฟล์ทั้งหมดพร้อมขนาด + shard
   - **จุดเด่น/จุดด้อย/ประสิทธิภาพ = ห้ามแต่งเอง** — HF ไม่มีข้อมูลนี้; แสดงเฉพาะที่ derive จากข้อมูลจริง (tags/description/ขนาด) + หมายเหตุซื่อๆ ว่า "HF ไม่ได้ให้ข้อมูล benchmark" (กัน hallucination)
4. **Sidebar ไฟล์ใหม่**:
   - **แสดงขนาด byte เป็น MB/GB** ทุกไฟล์ (จาก detail endpoint)
   - **จัดกลุ่มตาม quant** — quant เดียวรวมกลุ่ม, **shard-aware**: ระบุ "ต้องใช้พร้อมกัน N ส่วน" + ขนาดแต่ละส่วน + รวม + ปุ่ม **"ดาวน์โหลดทั้งชุด (N ไฟล์)"** (queue ทุก shard ต่อเนื่อง); single-file quant = ปุ่มเดียว
   - แยก/ติดป้าย fp16 ("ไม่ quantize — ใหญ่มาก") และไฟล์ non-GGUF (imatrix/README) ให้ชัด
   - **ยอด download**: มีแค่ระดับ repo (HF ไม่ให้รายไฟล์) → แสดงที่การ์ด/หัว sidebar **ห้าม fake รายไฟล์**
   - อธิบายความต่าง "การ์ด = จัดกลุ่มตาม quant (เช่น 4 quants)" vs "sidebar = ไฟล์ทั้งหมด (รวม shard)" ให้ผู้ใช้เข้าใจ (เช่น caption "M ไฟล์ ใน N quants")

### i18n + polish
- keys ใหม่ (detail/shard/category/size) ผ่าน translation-kit → TH → `npm run i18n:verify` PASS
- bundle **< 150 kB gzip** · `/app` 0 diff · 0 console error

---

## 🔒 กฎเหล็ก
1. **Additive** — ไม่แก้ route/contract เดิม; `/app` ต้อง 0 diff; main 8765 + trial 8799 **ห้ามแตะ/ห้าม restart** (ผู้ใช้กำลัง trial อยู่!) → Dev เทสต์ด้วย **server ชั่วคราวพอร์ตอื่น (เช่น 8804)** จาก worktree ชี้ `WS_LOG_FILE/WS_USAGE_HISTORY_FILE` ไป tmp แล้วปิดเอง
2. **Honest telemetry** — ขนาด/วันที่/downloads/tags = ค่าจริงจาก HF เท่านั้น; ไม่มี = null/n-a + หมายเหตุซื่อ; **ห้ามสร้าง description/จุดเด่น/benchmark เอง**
3. **Offline-first tests** — detail endpoint ต้องเทสต์ด้วย monkeypatch HF (ห้ามยิง HF จริงใน pytest); search enrichment ก็เช่นกัน
4. **XSS-safe** — description/tags/filename จาก HF ต้อง escape; markdown pipeline เดิมห้ามเปลี่ยน
5. Drawer direction ตาม CONVENTION; Preact signals gotcha; i18n ห้าม hardcode

## ✅ เกณฑ์จบ (QA gates)
1. Search card: layout ใหม่ไม่ชิดขอบ + category chip + tags + downloads จริง
2. `GET /v1/hub/model/{repo}` คืน published/updated/tags/sizes (bytes) ถูก (เทสต์ offline) + cache + 502 ซื่อ
3. Detail drawer: สรุปย่อ (RAM/quant จาก bytes จริง, context ถ้ามี, ฟีเจอร์จาก tags) + เต็ม (tags/files/shard) + ไม่มีข้อมูลแต่งเอง
4. Sidebar ไฟล์: มีขนาด MB/GB ทุกไฟล์ · จัดกลุ่มตาม quant · shard แสดง "N ส่วน + ดาวน์โหลดทั้งชุด" · fp16/non-GGUF ติดป้าย · caption อธิบายจำนวน
5. Regression: pytest baseline (166/6/9) + tests ใหม่ผ่าน · mypy clean · `/app` 0 diff · bundle<150kB · i18n PASS · 0 console error
6. Honest audit: ไม่มีขนาด/วันที่/description/จุดเด่นปลอม

## ▶️ ลำดับ
`Dev สร้าง (backend detail endpoint → frontend → i18n → self-verify + commit) → QA อิสระ (detail ถูกต้อง + shard UX + honest audit + regression) → PM ตรวจ + รายงานผู้ใช้`
