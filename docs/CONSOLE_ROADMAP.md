# 🗺️ Weight Streaming Console — Roadmap (phased build)

> แผนสร้าง **dashboard/console** ใหม่ (frontend redesign) ของเซิร์ฟเวอร์ local-LLM
> แยกจาก `docs/ROADMAP.md` ซึ่งเป็นแผนของ *ตัวไลบรารี Python/ผลิตภัณฑ์*
> **Source of truth รายเฟส/เกณฑ์จบ** = `docs/DASHBOARD_THEME_SPEC.md` §13 (ถ้าขัดกัน spec ชนะ)
> **สถานะอัปเดต**: 2026-08-03 · branch `feature/dashboard-theme` (git worktree) · ทดสอบที่พอร์ต **8799** · main **8765 ห้ามแตะ**จนกว่าจะ P6

---

## ภาพรวม: 7 เฟส (P0–P6)

ทุกเฟสเดินวงจร **Dev สร้าง → QA ตรวจอิสระ → PM ตรวจ spec → วนแก้จน gate ผ่าน → PM checkpoint รายงานผู้ใช้** แล้วจึงไปเฟสถัดไป

| เฟส | เนื้อหา | สถานะ (2026-08-03) |
|-----|---------|--------------------|
| **P0** | PM สำรวจ + ออก spec + ผู้ใช้อนุมัติ R1–R3 (Preact+Vite / backend แบ่งเฟส / worktree) | ✅ เสร็จ |
| **P1** | ฐาน: core/theme/i18n/router/shell/particles/components + **โลโก้ใหม่** + boot splash + i18n batch-1 (TH) | ✅ เสร็จ + QA PASS |
| **P2** | 4 หน้าจริง: **Overview / Chat / Live Stats / Models** (markdown XSS-safe, SSE streaming+Stop, honest hit-rate 0%+caveat, scan/load/unload) | ✅ เสร็จ + QA PASS + ผู้ใช้ตรวจรับ |
| **P3** | 3 หน้าจริง: **Issues** (9-state lifecycle + transition matrix + verify loop + maintainer panel) / **API Docs** (markdown-driven + code tabs + copy + honest notes) / **Settings** (runtime+persist · server read-only · apply-on-restart snippet · honest n/a) | ✅ เสร็จ + QA PASS + ผู้ใช้ตรวจรับ (รวมรอบ polish `bf512fd`: drawer→ซ้าย, toolbar, card, mobile left-sheet) |
| **P4** | **backend endpoint ใหม่** (spec §10): hub search/download+progress SSE, `/v1/usage/history`, `/v1/logs/tail`, `/v1/config` (+`PATCH` v1.1) + pytest — **backend ล้วน ห้ามแตะ frontend (หน้าที่ใช้ = P5)** | ✅ **เสร็จ + QA PASS** (`a58ae8b`) — endpoint §10 ครบ 9 ตัว + pytest +66 (รวม 164/6/9) + mypy clean (47 ไฟล์) · QA อิสระผ่าน (contract + security adversarial + offline hub) · `/app` 0 diff vs main |
| **P5** | หน้า **Hub** (search-first, one-click download) + polish (light theme, palette, notifications, export) + **i18n batch สุดท้าย = full TH sweep** + native check | 🔧 **Dev เสร็จ** (ถึง `79d944a` P5.3c) — ทุกหน้า implement ครบ (8 หน้าใน RouterView) + backend hub/usage/logs/config ครบ · **หลักฐาน QA (2026-08-03):** build reproducible (git clean) · bundle 131.93 kB gzip (< 150 kB) · i18n:verify PASS (661 keys) · pytest 177 passed / 13 skipped / 9 pre-existing GGUF-fixture errors · screenshots ใน `docs/artifacts/phase-5*` → **รอ QA ตรวจอิสระ + ผู้ใช้ตรวจรับ** |
| **P6** | **Promote Console ขึ้นproduction** — PM สรุป+demo → **ผู้ใช้อนุมัติสุดท้าย** → merge `feature→main` (`--no-ff`) + route swap (`/`→console, ของเก่า→`/app-legacy` หนึ่ง release) + CHANGELOG + **ลบ `dashboard_server.py` (มติผู้ใช้)** | ⬜ ยังไม่เริ่ม — **ผู้ใช้เลือกตัวเลือก A (ทำ P5 ให้จบดีก่อน) 2026-08-03** |

> หมายเหตุสถานะ P4: **Dev สร้างเสร็จแล้ว** (`a58ae8b`, 2026-07-31) ตาม **`docs/P4_BRIEF.md`** — endpoint §10 ครบ 9 ตัว (config GET/PATCH, usage/history, logs/tail, hub search/download/progress SSE/downloads/cancel) + module ใหม่ `server/{usage,logs,hub}.py` + pytest +66 (contract/manager/offline-hub/security) · suite **164 passed / 6 skipped / 9 pre-existing GGUF-fixture errors** · mypy clean (47 ไฟล์) · hub = stdlib urllib ล้วน (0 runtime dep ใหม่; httpx = test extra เท่านั้น) · แก้ dead `recent_errors` + dead `WS_LOG_LEVEL` · `/health`+`FastAPI(version)` = 0.13.0 แล้ว · `/app` 0 diff vs main, ไม่แตะ frontend · **QA ตรวจอิสระผ่านแล้ว** (contract tests + security adversarial + offline hub) ตามเกณฑ์ §13 — อัปเดตสถานะ 2026-08-03

> หมายเหตุสถานะ P5: **Dev เสร็จ** (HEAD `79d944a` P5.3c, 2026-08-02) — งาน P5.1 (Hub enrichment + shard-aware grouping จาก feedback ผู้ใช้), P5.2 (settings submenu + hub latest feed), P5.3 (a11y contrast + settings-server card) + i18n full TH sweep (batch-3, 661 keys) · **หลักฐาน QA ที่รันใหม่ 2026-08-03:** `npm run build` reproducible (git clean หลัง build) · bundle **131.93 kB gzip** (< 150 kB) · `npm run i18n:verify` **PASS** · `pytest` **177 passed / 13 skipped / 9 pre-existing GGUF-fixture errors** (9 ตัว = fixture ต้องการไฟล์ GGUF ที่ git-ignored — ไม่ใช่ regression) · screenshots: `docs/artifacts/phase-5/`, `phase-5-2/`, `polish/` · **งานที่เหลือก่อน P6:** QA ตรวจอิสระ (E2E Hub download + honest-telemetry audit + responsive/i18n sweep) + ผู้ใช้ตรวจรับ

## 🧭 มติผู้ใช้ (2026-07-31) — รูปแบบการย้ายระบบ (migration model)
1. **ทดลองใช้ก่อน โปรโมททีหลัง (trial-first / promote-later)**:
   - **`main` = เวอร์ชัน "Classic"** (production ปัจจุบัน, SPA `/app` เดิม) — คงไว้เป็นตัวหลักที่ปลอดภัย ตลอดช่วงทดลอง
   - **`feature/dashboard-theme` = เวอร์ชัน "Console"** — ผู้ใช้จะรันเซิร์ฟเวอร์จาก worktree บน**พอร์ตแยก** (เช่น 8799) เพื่อลองใช้งานจริงไประยะหนึ่ง (main 8765 ไม่ถูกแตะ)
   - เมื่อพอใจ → **โปรโมท = P6**: merge `feature→main` (`--no-ff`) + route swap (`/`→console, `/app`→`/app-legacy` หนึ่ง release) + CHANGELOG · **ผู้ใช้อนุมัติเอง ไม่มีอะไร flip อัตโนมัติ**
   - **สถานะ divergence (ตรวจ 2026-07-31)**: branch **รวม main ครบแล้ว** (main 0 commit ที่ branch ไม่มี · merge-base = HEAD main `9eb95b5`) → promote ตอนนี้ = ไร้ conflict · ถ้าผู้ใช้ commit เพิ่มใส่ main ระหว่างทดลอง ต้อง **sync main→branch** ก่อนโปรโมท (ทำโดย PM/ผู้ใช้ + รัน pytest ใหม่ทั้งชุด)
2. **ลบ `dashboard_server.py`** (CLI dashboard พอร์ต 8766 — เสิร์ฟค่าปลอม ขัด honest-telemetry) **ตอน merge P6** — ไม่ใช่ใน P4 · ต้องลบ call sites ด้วย: `cli/main.py:94-96,172-173,503-506` + `cli/__init__.py:21,55-57`

---

## กฎข้ามเฟส (ถือทุกเฟส — ห้ามละเมิด)
1. **Honest telemetry (ADR-003)**: ค่าจริงหรือ `n/a` เท่านั้น — ห้ามแต่ง stat/history/ETA; ครอบคลุม capability claim (agent-mode/reasoning-effort มี tooltip ซื่อว่า server ยังไม่ execute)
2. **Backend แบ่งตามเฟส**: P2/P3 ใช้ **endpoint เดิมเท่านั้น**; endpoint ใหม่ยกไป P4. ขาดข้อมูล → empty/n-a ซื่อ
3. **Chat/Issues markdown = XSS-safe** (marked → DOMPurify → highlight.js; sanitize หลังประกอบ; ห้าม `<img>`)
4. **Preact signals gotcha**: signal ที่ bump แต่ไม่ read ใน render จะไม่ re-render; อย่าส่ง ref เดิมของ array ที่ mutate เป็น prop — subscribe ชัดเจน (`void tick.value`) + ส่ง copy (`items().slice()`)
5. **i18n**: ไม่ hardcode ข้อความ; namespace ใหม่ผ่าน sealed translation-kit → small-model agent → `npm run i18n:verify` + native TH check; ต้องมี th mirror placeholder ให้ verify/build เขียวก่อนแปล
6. **Drawer/overlay ทิศทาง** (บทเรียนจาก bug 2 ครั้ง): ฝั่งที่ drawer เลื่อนเข้า = ฝั่งของ trigger (ซ้าย→ซ้าย, ขวา→ขวา); Dialog/Modal กลางจอ + dropdown + tooltip ไม่เข้าเกณฑ์นี้
7. **Keep-green regression baseline**: reproducible build (git clean) · `/app` 0 diff vs main · ไม่มี CDN · `i18n:verify` PASS · classic `#0b0f19`+radii 6/10 · aurora particles+reduced-motion off · 4 breakpoints (1440/1200/900/412) · TH · palette keyboard · drawer/dialog focus-trap · 0 console errors · **pytest 98 passed / 6 skipped / 9 pre-existing GGUF-fixture errors** (= baseline, 9 ตัวไม่ใช่ของใหม่)

---

## Definition of Done รวม (ทุกเฟส)
pytest เขียว · ไม่มี console error · honest-telemetry audit ผ่าน · TH+EN ครบ · dark+light + 4 breakpoints · keyboard ล้วนใช้งานได้ · bundle ใต้งบ ~150 kB gzip

---

## Carry-over (non-blocking — ไม่เปิดเฟสที่ผ่านแล้วใหม่)
- `registry.ts` static-import token CSS vs spec §4.2 css-path drop-in (ยอมรับ/bundled)
- `/health` hardcode `0.11.0` vs package `0.13.0` → Settings/About ชดเชยโดยดึงจาก `/v1/debug/context` แล้ว แต่ navbar dot/splash ยังตาม `/health` (แก้ server ด้วย `__version__` เฟสหลัง)
- EN copy `faults/token` (overview) vs `faults/tok` (stats) — cosmetic
- recursive scan โฟลเดอร์โมเดลใหญ่มาก (เช่น `D:/models` 11.5GB GGUF) ค้าง/serialize `/v1/models/scan` → ควรมีตั๋ว scan timeout/cancel (pre-existing)
- mobile shell buttons 34–37px (<44px) — ยอมรับตอน P1 sign-off
- bundle โตเป็น ~112.5 kB gzip หลัง P3 (ยังใต้งบ) — ติดตามใน P5

---

## ไฟล์ที่เกี่ยวข้อง
- Spec (source of truth): `docs/DASHBOARD_THEME_SPEC.md`
- P2 brief: `docs/P2_BRIEF.md` · หลักฐาน P2: `docs/verification-p2/` + `docs/verification-p2-qa/`
- Project memory (cross-run): note `dashboard-console-phases`
- แผนผลิตภัณฑ์/ไลบรารี (คนละอัน): `docs/ROADMAP.md`

---

## 📝 บันทึกการทำงาน (Session Log)

> **กรอบ:** บันทึกการทำงานทุกครั้งที่ดำเนินการ — หลักฐาน/วัดผล/ย้อนกลับได้/ตรวจสอบได้

### 2026-08-03 — ปิดงาน worktree (ตัวเลือก A: ทำ P5 ให้จบก่อน P6)
- **ผู้ใช้ตัดสินใจ:** ตัวเลือก A (ทำ P5 ให้จบดีทั้งหมดก่อน) + เก็บธีม classic ไว้เป็นตัวเลือก (มีใน registry แล้ว) + merge แทน replace
- **งานที่ทำ:**
  - Deep Research สถานะจริง: P4 QA ผ่าน, P5 Dev ทำถึง P5.3c, P6 ยังไม่เริ่ม
  - ตรวจสอบ ii8n: `npm run i18n:verify` PASS (661 keys, 20 strings > 45% = warning)
  - ตรวจสอบ build: `npm run build` reproducible (git status สะอาดหลัง build) · bundle **131.93 kB gzip** (< 150 kB)
  - ตรวจสอบ test: `pytest` **177 passed / 13 skipped / 9 pre-existing GGUF-fixture errors** (9 ตัว = fixture ต้องการไฟล์ GGUF ที่ git-ignored)
  - อัปเดตเอกสาร roadmap นี้ให้ทันสถานะจริง (P4 QA ผ่าน, P5 Dev เสร็จ + หลักฐาน)
- **หลักฐาน (evidence):** ไฟล์นี้ + `docs/artifacts/phase-5*` + ผล test/build/i18n ที่รันจริง
- **งานที่เหลือ (ก่อน P6):**
  1. ✅ อัปเดตเอกสาร roadmap (ทำแล้ว)
  2. ⬜ QA ตรวจอิสระ P5 (E2E Hub download + honest-telemetry audit + responsive/i18n sweep)
  3. ⬜ ผู้ใช้ตรวจรับ P5
  4. ⬜ P6: sync main → backup tag → merge --no-ff → route swap → ลบ dashboard_server.py → CHANGELOG
- **ย้อนกลับได้:** branch `feature/dashboard-theme` ยังไม่ merge — ตรวจสอบได้ทุกขั้นตอน
