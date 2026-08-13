# 🎨 P5 BRIEF — Weight Streaming Console: Hub page + เดินสาย Settings/Overview ใช้ P4 + full TH sweep

> **สถานะ**: ปล่อยงานโดย PM แล้ว (2026-08-01) · P1–P4 เสร็จ + **P4 QA PASS อิสระ** + ผู้ใช้อนุมัติให้เริ่ม P5 · run ต้นทาง `run-1785386652753-35chx9`
> **Source of truth**: `docs/DASHBOARD_THEME_SPEC.md` — โดยเฉพาะ **§9.1** (Overview Activity), **§9.4** (Models Library), **§9.6** (Hub), **§9.8** (Settings server), **§13** (เกณฑ์จบ P5) + `docs/CONSOLE_ROADMAP.md` (cross-phase rules) · ไฟล์นี้ = brief ย่อยสำหรับ Dev/QA (ถ้าขัดแย้งกัน spec ชนะ)
> **Branch / worktree**: `feature/dashboard-theme` ที่ `~/worktrees/dashboard-theme/weight-streaming` (HEAD `cb1165b`)
> **Frontend source**: `frontend/` (Preact+Vite) → build ออก `weight_stream/server/static/console/`

---

## 🎯 เป้าหมาย + ขอบเขตเฟส

**P5 = frontend ล้วน** — สร้างหน้า **Hub** ใหม่ 100% (§9.6) + **เดินสายหน้าที่คอย P4** ให้ใช้ endpoint จริง (Overview Activity §9.1, Settings server §9.8, Models Library §9.4) + **full TH sweep** + polish — แทนที่ placeholder ซื่อๆ ของ P3/P4 ด้วยข้อมูลจริง **ห้ามแก้ backend route** (งาน backend เสร็จแล้วที่ P4) — ยกเว้น **P4 hardening #1–3** ที่พับมาทำด้วย (แตะ `hub.py` นิดเดียว)

| งาน | รายละเอียด | endpoint ที่ใช้ |
|-----|-----------|----------------|
| **🌐 Hub page** (§9.6) | search-first · การ์ด GGUF · file picker · download + SSE progress · downloads panel · curated shelves · target dir · offline banner | `/v1/hub/{search,download,downloads,progress/{id},download/{id}/cancel}` |
| **🏠 Overview Activity** (§9.1) | generate ล่าสุด 5 รายการ (model/tokens/tok-s/เวลา) แทน placeholder | `/v1/usage/history?limit=5` |
| **⚙️ Settings server** (§9.8) | Server(read) ค่าจริง+source · runtime edit safe subset · log tail viewer | `/v1/config` (GET+PATCH), `/v1/logs/tail` |
| **🧠 Models Library** (§9.4 P4+) | โฟลเดอร์ models + สถานะ loaded/on-disk + Hub shortcut | `/v1/config` (models_dirs) + `/v1/models` |
| **🔧 P4 hardening** | #1 `.part` O_NOFOLLOW/O_EXCL · #2 เพิ่ม test `content_length=None` · (#3 disk-free note) | แตะ `hub.py`+`test_p4_hub.py` |
| **🇹🇭 i18n full TH sweep** | keys ใหม่ของ Hub/Settings-server/Overview-activity ผ่าน translation-kit → small-model agent → verify | `npm run i18n:verify` |

---

## 🔒 กฎเหล็ก (ห้ามละเมิด — เหมือน P1–P4)

1. **Additive frontend เท่านั้น** — ไม่แก้ backend route signature; **`/app` (legacy SPA) ต้อง 0 diff vs main**; ไม่แตะ main 8765
2. **Honest telemetry (ADR-003)** — progress/speed/ETA ของ Hub = **ค่าจริงจาก SSE** (backend คำนวณให้แล้ว) ห้ามตกแต่ง; HF unreachable/empty → **banner/empty state ซื่อๆ** ห้าม fake รายการ; capability ที่ยังไม่มี (resume, delete file, agent tool-exec) → tooltip ตามจริง
3. **XSS-safe** — ชื่อ repo/author/filename จาก server ต้อง **escape** (ห้าม `dangerouslySetInnerHTML` ข้อมูล server ตรงๆ); markdown pipeline เดิม (marked→DOMPurify→hljs) ห้ามเปลี่ยน
4. **Drawer/overlay direction** (cross-phase rule 6) — slide edge ต้องตรงกับมุม trigger; Hub drawer/panel **ทำตาม CONVENTION comment ใน `frontend/src/components/Drawer.tsx`**
5. **i18n** — ห้าม hardcode string; keys ใหม่ผ่าน sealed translation-kit → small-model agent แปล TH → `npm run i18n:verify` ผ่าน + native TH อ่านลื่น
6. **Preact signals gotcha** — bumped-but-unread signal ไม่ re-render; อย่าส่ง mutated same-ref array เป็น prop
7. **Bundle budget** — รักษา **< 150 kB gzip** (P3 = 112.54); SSE/EventSource ใช้ของ native อย่าเพิ่ม lib ใหญ่; ถ้าจะเกินต้อง flag PM

---

## 📐 การออกแบบรายงาน (Dev ตั้งต้นจากนี้)

### A. 🌐 Hub page (§9.6 — reference UX: Jan.ai Hub)
- **Search bar**: debounce 400ms → `GET /v1/hub/search?q=&sort=downloads|likes|recent&limit=` (backend กรอง GGUF + parse quant/size + cache 5 นาทีให้แล้ว) → การ์ด: ชื่อ · author · badges (quant ที่มี + ขนาดไฟล์ต่อ quant) · downloads/likes/updated
- **File picker**: ปุ่ม "ดูไฟล์" → แผงเลือกไฟล์ GGUF ใน repo (ชื่อ/size/quant) → **Download**
- **Download flow**: `POST /v1/hub/download {repo_id, filename, target_dir?}` → `202 + task_id` → ติดตามด้วย **SSE** `GET /v1/hub/progress/{task_id}` (bytes/%/speed/ETA/status = ค่าจริง) → toast + progress bar; เสร็จ (`done`) → ชวน **"โหลดเลย?"** เรียก `/v1/models/load` ต่อ; `failed` → retry ใหม่ (v1 ไม่มี resume); `cancelled` → cleanup
- **Downloads panel**: `GET /v1/hub/downloads` (คิว/ประวัติ status queued/downloading/done/failed) + cancel ต่อรายการ (`POST /v1/hub/download/{id}/cancel`)
- **Curated shelves**: แถวแนะนำ client-side JSON ("ยอดนิยมสำหรับ 16GB RAM", "MoE ที่รองรับ", "ภาษาไทยดี") ลิงก์ไป search · label ซื่อ "รายการแนะนำโดยทีม"
- **Target dir**: default = models dir (จาก `/v1/config` models_dirs); เปลี่ยนได้ต่อรายการ (browse-dir)
- **Offline/error**: HF unreachable (502/503) → banner + ลิงก์ "เปิด huggingface.co" + วิธี manual drop-in · empty result → empty state ซื่อ
- **SSE lifecycle**: visibility-aware — หยุดเมื่อ tab hidden, ต่อเมื่อ visible; จัดการ reconnect/timeout

### B. 🏠 Overview Activity (§9.1)
- `GET /v1/usage/history?limit=5` → ตาราง/การ์ด: model · tokens · tok/s · เวลา (relative) · แสดงเท่าที่มี (tok_s อาจ = null → แสดง "–" ไม่แต่ง)
- **Empty state**: "เริ่มเก็บข้อมูลหลัง generate ถัดไป" (ซื่อ — history เริ่มจาก P4)

### C. ⚙️ Settings server (§9.8)
- **Server (read)**: `GET /v1/config` → แสดงค่าจริงทุก key + **source badge (env/default/runtime)** + models_dirs + issues_dir + version (จาก debug context)
- **Server (runtime edit)**: form แก้ **safe subset** {`idle_unload_timeout`, `max_loaded_models`} → `PATCH /v1/config` (มีผลจริง); **gated** {buffer/n_ctx/n_threads} → เตือน "มีผลเฉพาะโมเดลที่โหลดภายหลัง"; **อื่น** → รับ `409 + snippet` แสดง snippet ให้ copy (อย่า toast เหมือนพัง)
- **Diagnostics → log tail**: `GET /v1/logs/tail?lines=` viewer + ดาวน์โหลด (`data/server.log` มีจริงแล้วจาก P4)

### D. 🧠 Models Library (§9.4 P4+)
- แสดง models dirs (จาก `/v1/config`) + สถานะ loaded/on-disk + **Hub shortcut** สำหรับโมเดลที่ยังไม่มี · **ไม่มีลบไฟล์** (future — ความเสี่ยงบน server ไม่มี auth)

### E. 🔧 P4 hardening (#1–3, แตะ backend นิดเดียว)
- **#1** `hub.py`: เปิด `.part` ด้วย `os.open(path, O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW)` (หรือเทียบเท่า Windows) ปิด symlink-TOCTOU; ถ้า file มีอยู่แล้วให้จัดการให้สอดคล้องกับ retry
- **#2** `tests/test_p4_hub.py`: เพิ่ม test size-guard กรณี `content_length=None` (mid-stream guard นับ byte จริงทะลุเพดานไม่ได้)
- **#3** (optional) note พฤติกรรม disk-free guard เมื่อไม่มี Content-Length ใน docstring
- ห้ามเปลี่ยน contract; suite ต้องยังเขียว

### F. 🇹🇭 i18n full TH sweep
- keys ใหม่ทั้งหมด (Hub/Settings-server/Overview-activity/Models-library) → translation-kit → **small-model agent แปล TH** → `npm run i18n:verify` PASS + อ่าน native TH ลื่น (ไม่มี hardcode, placeholder ตรงกัน)

---

## 🧪 กลยุทธ์ verify (Dev self-verify ก่อนส่ง QA)
- `npm run build` reproducible + **bundle < 150 kB gzip** (รายงานตัวเลข)
- `npm run i18n:verify` PASS
- `PYTHONPATH=. pytest tests/ -q` เขียว (baseline **164/6/9** + test hardening ใหม่ผ่าน)
- smoke ในเบราว์เซอร์: เปิด Hub/Overview/Settings/Models **0 console error** · drawer ถูกทิศ · dark+light · keyboard/focus-trap
- **ทดสอบ UI ต้องยิง P4 code**: server trial 8799 ของผู้ใช้เป็นโค้ดเก่า (ก่อน P4) → **ห้ามไปยุ่ง** · ให้ Dev **เปิด server ชั่วคราวเองอีกพอร์ต (เช่น 8801)** จาก worktree ชี้ `WS_LOG_FILE`/`WS_USAGE_HISTORY_FILE` ไปที่ tmp แล้วปิดหลังทดสอบ (ห้ามยิง HF จริง — Hub search จริงจะโดน network; ใช้เฉพาะเมื่อจำเป็นและรู้ตัว)
- commit แบบ conventional (แยก frontend / backend-hardening / i18n ได้)

---

## ✅ เกณฑ์จบ P5 (QA gates, §13 — "full regression · E2E ค้นหา→ดาวน์โหลด→โหลด→แชท · responsive/i18n sweep · honest-telemetry audit")

1. **Hub E2E**: ค้นหา→การ์ด GGUF→เลือกไฟล์→download→**SSE progress ค่าจริง**→เสร็จ→"โหลดเลย?"→โหลดได้; cancel ได้; downloads panel ตรงสถานะ; HF unreachable→banner ไม่ fake
2. **Overview Activity**: แสดง 5 รายการจริงจาก usage history; empty state ซื่อ
3. **Settings server**: ค่าจริง+source จาก /v1/config; PATCH safe subset มีผล; non-safe→409 snippet; log tail viewer เห็น log จริง
4. **Models Library**: dirs + loaded/on-disk + Hub shortcut
5. **i18n**: `npm run i18n:verify` PASS · TH+EN ครบ · native TH ลื่น
6. **Keep-green**: `/app` 0 diff · 0 console error · reproducible build · 4 breakpoints (1440/1200/900/412) · dark+light · keyboard ล้วน · focus-trap · drawer ถูกทิศ · bundle **< 150 kB gzip**
7. **Honest-telemetry audit ทุกหน้า**: ไม่มี speed/ETA/progress/count ปลอม · capability/restart note ตรงจริง
8. **Hardening**: #1 `.part` nofollow/excl + #2 test `content_length=None` ผ่าน · suite เขียว · mypy clean
9. **XSS**: ชื่อ/ข้อมูล server ใน Hub ถูก escape · markdown pipeline ไม่เปลี่ยน
10. **Regression**: endpoint เดิมไม่เปลี่ยน · pytest baseline เขียว

---

## 📌 พกต่อ / out-of-scope (ไม่ใช่แกน P5)
- **Out**: HTTP Range/resume (v2 = retry ใหม่) · model file delete (future) · agent tool-exec server-side · auth/token · **P6 promotion** (merge/route swap/ลบ dashboard_server — user-gated แยกเฟส)
- **Carry-over (optional stretch, ไม่ใช่ gate)**: registry static-import §4.2 · mobile btn <44px · scan timeout/cancel · EN faults/token vs `/tok` (แก้ label ได้ง่าย = polish)

---

## ▶️ สร้าง/รัน/ตรวจ
```bash
cd <worktree>/.Weight-Streaming/frontend
npm install
npm run build            # → static/console/ (reproducible, ดู bundle size)
npm run i18n:verify      # ต้อง PASS
# backend hardening + regression:
cd .. && PYTHONPATH=. python -m pytest tests/ -q     # baseline 164/6/9 + ใหม่
# UI test ยิง P4 code (ห้ามแตะ 8799/8765):
PYTHONPATH=. WS_LOG_FILE=/tmp/ws.log WS_USAGE_HISTORY_FILE=/tmp/usage.jsonl \
  python -m weight_stream.server --port 8801   # server ชั่วคราว → ปิดหลังทดสอบ
```

## ลำดับ
`Dev สร้าง (ตาม §การออกแบบ + self-verify) → commit → QA ตรวจอิสระ (E2E + honest-telemetry + responsive/i18n + security/XSS) → PM ตรวจ spec + รายงานผู้ใช้` วนจน gate ผ่าน → **P6** (PROMOTE — ต้องได้ user approve ก่อนเสมอ)
