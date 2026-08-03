# ✅ P5 QA Report — Weight Streaming Console (2026-08-03)

> **QA โดย:** OpenCode Agent (อิสระ) + ผู้ใช้ตรวจ web UI ร่วม
> **Server:** trial พอร์ต 8804 (จาก HEAD `6d46278`) — ปิดแล้วหลัง QA
> **เกณฑ์:** `docs/P5_BRIEF.md` §13 (10 gates) + `docs/DASHBOARD_THEME_SPEC.md`
> **Model ทดสอบ:** qwen2.5-0.5b-instruct-q2_k.gguf (415MB, download จาก Hub จริง)

---

## 📋 ผล QA ตาม 10 gates

| # | Gate | ผล | หลักฐาน |
|---|------|-----|---------|
| 1 | **Hub E2E** (search→download→SSE→load) | ✅ **ผ่าน** | `/v1/hub/search?q=qwen` คืนผล HF จริง (unsloth/Qwen3-Coder-30B) · POST `/v1/hub/download` → 202 task `dl-1` → SSE progress 68.2% → 81.1% → **100% done** (speed 7.57 MB/s, ETA จริง) · `.part` ถูก atomic rename · GGUF valid (magic GGUF, ver 3, 291 tensors) · load model → 200 "loaded" · chat → ตอบ "Hi!" (2 tokens) |
| 2 | **Overview Activity** | ✅ **ผ่าน** | `/v1/usage/history` มี 1 รายการจริง: qa-qwen, 2 tok, 9.86 tok/s, paging: faults 48,468 / faults_per_token 24,234 / disk_demand 0.0 MB (warm) |
| 3 | **Settings server** | ✅ **ผ่าน** | `/v1/config` → 200 ทุก key + `source: default/env/cli` badge |
| 4 | **Models Library** | ✅ **ผ่าน** | `/v1/models` แสดง model ที่ load (qa-qwen) · `/v1/stats` models_loaded=1 |
| 5 | **i18n:verify** | ✅ **ผ่าน** | PASS 661 keys TH+EN · 20 strings > 45% (warning — review UI fit) |
| 6 | **Keep-green** | ✅ **ผ่าน** | `npm run build` reproducible (git clean หลัง build) · bundle **131.93 kB gzip** (< 150 kB) · 4 breakpoints/dark+light/keyboard/focus-trap (โค้ด) |
| 7 | **Honest-telemetry** | ✅ **ผ่าน** | ทุกค่าจริง: speed_bps 16.5→8.6→7.57 MB/s (network ผันผวนจริง), percent 68.2→81.1→100, faults จริง, empty states ซื่อ (`history:[]`, `downloads:[]`) — ไม่มีค่าปลอม |
| 8 | **Hardening** | ✅ **ผ่าน** | commit `3db85d3` (.part O_EXCL/no-follow) + test `content_length=None` · `.part` atomic rename ทำงานจริง |
| 9 | **XSS** | ✅ **ผ่าน** | `renderMarkdown()`: marked → DOMPurify (html profile, `FORBID_TAGS: style/form/input/iframe/embed/object/img`, `FORBID_ATTR: style`) · code = text content เท่านั้น · link เฉพาะ http(s) + noopener · Hub/Issues ใช้ JSX escape · **Report-ISSUE-002 (XSS probe) มีในระบบ** — payload `<script>/<img onerror>/<svg onload>/<iframe>` ถูก escape (ดูผ่าน API/UI) |
| 10 | **Regression** | ✅ **ผ่าน** | pytest **177 passed / 13 skipped / 9 pre-existing GGUF-fixture errors** · `/app` 200 (legacy ยังทำงาน) · `/` → 302 `/app/` (ยังไม่ swap) · `/console/` 200 |

---

## 🧪 สรุปผล

**P5 ผ่าน QA ครบทั้ง 10 gates** ✅ — พร้อม P6 (promote) ต่อจากผู้ใช้ตรวจรับ web UI

### ข้อสังเกต / findings (บันทึกไว้)
1. **`/health` version ยัง hardcode 0.11.0** (carry-over จาก roadmap) — Settings/About ชดเชยด้วย `/v1/debug/context` แล้ว แต่ navbar dot/splash ยังตาม `/health` → แก้ server ด้วย `__version__` เฟสหลัง
2. **20 strings ไทยยาวกว่า EN >45%** — warning จาก i18n:verify (ไม่ fail) — ควร review UI fit
3. **Report-ISSUE-002 มี 2 ไฟล์ต่างกัน** — `.json` (XSS probe, title ใหม่) vs `.md` (issue เก่า "ทดสอบการใช้งานหลังอัพเดท Llama") — ระบบ issues อ่านจาก `.json` (ถูกต้อง) แต่ `.md` เก่าค้างอยู่ → ล้างได้ (non-blocking)
4. **Server trial 8805 ค้างจาก QA รอบก่อน (PID 36264)** — ปิดแล้ว 2026-08-03 ตามผู้ใช้อนุมัติ (P5 commit ครบก่อนปิด)
5. **Download ทับไฟล์เดิมที่มีอยู่** — `qwen2.5-0.5b-instruct-q2_k.gguf` (415MB เดิม) ถูก overwrite ด้วยไฟล์ใหม่จาก HF (ขนาดเท่ากัน) — ไม่มี warning เรื่องไฟล์มีอยู่แล้ว → ควรพิจารณาเพิ่ม confirm/overwrite flow (future)

---

## 📁 หลักฐานที่เกี่ยวข้อง
- Test results: pytest 177/13/9 (รัน 2026-08-03)
- Build: reproducible, bundle 131.93 kB gzip
- i18n: PASS 661 keys
- Screenshots: `docs/artifacts/phase-5/`, `phase-5-2/`, `polish/`
- API evidence: บันทึกในไฟล์นี้

---

*QA โดย OpenCode Agent · 3 สิงหาคม 2026 · งานถัดไป: ผู้ใช้ตรวจรับ web UI → P6 promote*
