# 🗺️ Weight Streaming Console — Roadmap (phased build)

> แผนสร้าง **dashboard/console** ใหม่ (frontend redesign) ของเซิร์ฟเวอร์ local-LLM
> แยกจาก `docs/ROADMAP.md` ซึ่งเป็นแผนของ *ตัวไลบรารี Python/ผลิตภัณฑ์*
> **Source of truth รายเฟส/เกณฑ์จบ** = `docs/DASHBOARD_THEME_SPEC.md` §13 (ถ้าขัดกัน spec ชนะ)
> **สถานะอัปเดต**: 2026-07-31 · branch `feature/dashboard-theme` (git worktree) · ทดสอบที่พอร์ต **8799** · main **8765 ห้ามแตะ**จนกว่าจะ P6

---

## ภาพรวม: 7 เฟส (P0–P6)

ทุกเฟสเดินวงจร **Dev สร้าง → QA ตรวจอิสระ → PM ตรวจ spec → วนแก้จน gate ผ่าน → PM checkpoint รายงานผู้ใช้** แล้วจึงไปเฟสถัดไป

| เฟส | เนื้อหา | สถานะ (2026-07-31) |
|-----|---------|--------------------|
| **P0** | PM สำรวจ + ออก spec + ผู้ใช้อนุมัติ R1–R3 (Preact+Vite / backend แบ่งเฟส / worktree) | ✅ เสร็จ |
| **P1** | ฐาน: core/theme/i18n/router/shell/particles/components + **โลโก้ใหม่** + boot splash + i18n batch-1 (TH) | ✅ เสร็จ + QA PASS |
| **P2** | 4 หน้าจริง: **Overview / Chat / Live Stats / Models** (markdown XSS-safe, SSE streaming+Stop, honest hit-rate 0%+caveat, scan/load/unload) | ✅ เสร็จ + QA PASS + ผู้ใช้ตรวจรับ |
| **P3** | 3 หน้าจริง: **Issues** (9-state lifecycle + transition matrix + verify loop + maintainer panel) / **API Docs** (markdown-driven + code tabs + copy + honest notes) / **Settings** (runtime+persist · server read-only · apply-on-restart snippet · honest n/a) | ✅ เสร็จ + QA PASS + ผู้ใช้ตรวจรับ (รวมรอบ polish `bf512fd`: drawer→ซ้าย, toolbar, card, mobile left-sheet) |
| **P4** | **backend endpoint ใหม่** (spec §10): hub search/download+progress SSE, `/v1/usage/history`, `/v1/logs/tail`, `/v1/config` (+`PATCH` v1.1) + pytest — **backend ล้วน ห้ามแตะ frontend (หน้าที่ใช้ = P5)** | 🔄 **เริ่มแล้ว** — PM ปล่อยสเปค (`docs/P4_BRIEF.md` `b56e0d8`) → รอ Dev |
| **P5** | หน้า **Hub** (search-first, one-click download) + polish (light theme, palette, notifications, export) + **i18n batch สุดท้าย = full TH sweep** + native check | ⬜ ยังไม่เริ่ม |
| **P6** | PM สรุป + demo → **ผู้ใช้อนุมัติสุดท้าย** → merge กลับ main + route swap (`/`→console, ของเก่า→`/app-legacy` หนึ่ง release) + CHANGELOG | ⬜ ยังไม่เริ่ม |

> หมายเหตุสถานะ P4: สเปคอยู่ที่ **`docs/P4_BRIEF.md`** (ตรวจโค้ดจริงก่อนเขียน — usage-hook ที่ ModelManager, PATCH safe subset, logging rewire, HF raw HTTP, hub security) + NOTE ทีม · เป็นเฟสแรกที่แตะ server core; **frontend ที่ใช้ endpoint P4 ทั้งหมดเลื่อนไป P5** เพื่อแยกตรวจด้วย pytest/contract tests ล้วน

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
