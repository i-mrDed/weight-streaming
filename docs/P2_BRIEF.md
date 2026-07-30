# 📦 P2 BRIEF — Weight Streaming Console: 4 หน้าจริง (Overview / Chat / Live Stats / Models)

> **สถานะ**: ปล่อยงานโดย PM แล้ว (2026-07-30) · ผู้ใช้ตรวจรับ P1 แล้วจริง · run ต้นทาง `run-1785386652753-35chx9`
> **Source of truth**: `docs/DASHBOARD_THEME_SPEC.md` — โดยเฉพาะ **§9.1–9.4** (สเปกรายหน้า) และ **§13** (workflow/เกณฑ์จบ) · ไฟล์นี้ = brief ย่อยสำหรับ Dev/QA (ถ้าขัดแย้งกัน spec ชนะ)
> **Branch / worktree**: `feature/dashboard-theme` ที่ `D:\.opencode\.worktrees\dashboard-theme\.Weight-Streaming` (สร้างต่อบน P1 ที่ commit แล้ว)

---

## เป้าหมาย
สร้าง **4 หน้าจริง** บนฐาน P1 ที่ผ่านการตรวจแล้ว (theme/i18n/responsive/shell/components) แทน placeholder "กำลังพัฒนา":

| หน้า | Spec | สรุปงาน |
|------|------|---------|
| 🏠 **Overview** | §9.1 | hero status (`/health`+`/v1/stats.server`) · แถวโมเดลที่โหลด (`/v1/models`) · health widgets (`/v1/stats`+`/v1/issues?status=open`) · quick actions · **Activity = empty ซื่อๆ** ("จะเริ่มเก็บข้อมูลหลัง generate ถัดไป" — ต้องการใช้ `/v1/usage/history` ซึ่งเป็น **P4**) |
| 💬 **Chat** | §9.2 | conversation sidebar (localStorage, grouping วันนี้/เมื่อวาน/เก่ากว่า) · model selector · **agent-mode + reasoning-effort + tooltip ตามจริง** (server ยังไม่ execute) · **markdown+code+copy ต้อง XSS-safe** · <think> accordion · SSE streaming + Stop คงข้อความ · desktop notification · parameter drawer · presets · Export .md |
| 📊 **Live Stats** | §9.3 | poll `/v1/stats` @2s (visibility-aware/backoff) · 5 gauge cards + delta + tooltip ซื่อ · **hit-rate = 0% จริง + caveat** (ADR-003) · กราฟ 2 เส้นจาก **client ring buffer** กำกับ "session window" · paging detail (+n/a non-Windows) · MoE heatmap **degrade สำหรับ dense** · idle state |
| 🧠 **Models** | §9.4 | loaded cards + Unload(confirm)/Reload(force)/stats/use-in-chat · scan (`/v1/browse-dir` + การ์ดผล + คำเตือน `may_need_upgrade`) · load form (path/browse + id/BUF/CTX/threads + คำเตือน quant F16/Q2_K) · Library view = **P4+ (เลื่อน)** · ไม่ลบไฟล์ (out of v1) |

---

## 🔒 กฎเหล็ก (ห้ามละเมิด)
1. **ใช้ endpoint เดิมเท่านั้น** — ไม่มี backend ใหม่ใน P2 (Hub / usage-history / logs / config = **P4**) · จุดไหนยังไม่มีข้อมูล → **empty / n/a ซื่อๆ ห้ามแต่งค่าเด็ดขาด**
2. **Honest telemetry (ADR-003) ครอบคลุมถึง capability** — agent/effort tooltip บอกตรงๆ ว่า server ยังไม่ execute, กราฟกำกับ "session window", ไม่มี ETA/ค่าปลอม
3. **Markdown ต้อง XSS-safe** — sanitizer ระดับ DOMPurify + highlighter ปลอดภัย · ห้าม `innerHTML` raw output จากโมเดล · QA จะยิง payload ทดสอบ (script / img onerror / svg onload)
4. **P1 ต้องเขียวยกชุด (regression)**: build reproducible (git clean) · `/app` 0 diff กับ main · ไม่มี CDN · ไม่มี fake-metric literals · `npm run i18n:verify` PASS · classic `#0b0f19`+radii 6/10 · aurora particles + reduced-motion ปิด · 4 breakpoints · TH · palette keyboard · drawer/dialog focus-trap · 0 console errors · **pytest baseline 98 passed / 6 skipped / 9 pre-existing fixture errors**

## 🌐 i18n batch 2 (มติ D7 — ส่งโมเดลเล็กแปล)
- namespace ใหม่: `chat`, `stats`, `models` (+ overview keys) · เขียน **EN ก่อน, keys นิ่ง**
- ประกอบ `frontend/translation-kit/batch-2/` = `en/*.json` + `CONTEXT.md` + `GLOSSARY.md` → ส่ง **agent โมเดลเล็ก** (kit ปิดขอบเขต ไม่เห็น codebase) → verify อัตโนมัติ + QA native TH check
- ห้าม hardcode ข้อความ UI ใน component · GLOSSARY = single source of truth ข้าม batch

## 📦 deps ใหม่ที่อนุญาต (§11) — งบ ~150KB gzip (P1 = 26KB)
`marked` + `dompurify` + `highlight.js` (core build เลือกภาษา) สำหรับ chat · `uPlot` หรือ canvas เองสำหรับกราฟ · โตขึ้นมากให้ flag · self-host เท่านั้น **ห้าม CDN runtime**

## ▶️ สร้าง/รัน/ตรวจ
```bash
cd <worktree>/.Weight-Streaming/frontend && npm install && npm run build \
  && cd .. && PYTHONPATH=. python -m weight_stream.server --port 8799
# เปิด http://127.0.0.1:8799/console/
```
- พอร์ต **8799 ว่าง** (server เดโม P1 ของ PM หยุดแล้ว)
- **main ของผู้ใช้รันที่ 8765 — ห้ามแตะ** (คนละ branch/งาน)
- i18n: `npm run i18n:verify` · typecheck: `npm run typecheck` · regression: `pytest tests/ -q`

## ✅ เกณฑ์จบ P2 (QA gates, §13)
markdown+copy XSS-safe · streaming + Stop คงข้อความบางส่วน · stats poll + idle states · hit-rate caveat (0% จริง) · heatmap degrade dense · load/unload/reload/scan ไหลลื่น · + P1 keep-green ทั้งชุด · 0 console errors · i18n batch-2 verify PASS + native TH spot-check · **honest-telemetry audit** (ไม่มี activity/history/ETA/capability ปลอมทุกหน้า)

## 📌 พกต่อ (ไม่ใช่ scope P2 — อย่าให้บวม)
1. registry static-import ต่างจาก spec §4.2 css-path (ยอมรับได้)
2. `/health` hardcode `0.11.0` vs package `0.13.0` (แก้ฝั่ง server ด้วย `__version__` ในเฟสหลัง)

## ลำดับ
`Dev สร้าง → self-verify ตาม gates → commit (conventional) → QA ตรวจอิสระ → PM ตรวจ spec + รายงานผู้ใช้` วนจน gate ผ่าน แล้วค่อย P3 (Issues + API Docs + Settings)
