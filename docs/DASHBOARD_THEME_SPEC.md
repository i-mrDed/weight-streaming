# 📋 SPEC: Weight Streaming Console — Dashboard Theme & Frontend Redesign

> **สถานะ**: ✅ **อนุมัติแล้ว** (2026-07-30, รวมข้อเสริมโลโก้ + translation workflow) · ทีม "ระบุ สร้าง ตรวจสอบ" · run `run-1785386652753-35chx9`
> **Branch**: `feature/dashboard-theme` (แยกจาก main — รายละเอียด §12)
> **ผู้เกี่ยวข้อง**: PM (spec/อนุมัติขั้นกลาง) → Dev (สร้าง) → QA (ตรวจสอบ) → User (อนุมัติสุดท้ายก่อน merge)

---

## 1. ภาพรวมและเป้าหมาย

สร้าง **Dashboard บริหารจัดการ Local API Server แบบครบวงจร** สำหรับ Weight Streaming (ระบบรัน LLM ใหญ่กว่า RAM ผ่าน NVMe weight streaming) โดย:

1. **คงของเดิมที่ดีไว้** — ธีม/UXUI/Layout ปัจจุบัน ("Deep Space Glassmorphism") ถูกรักษาเป็นธีมคลาสสิกที่เลือกใช้ได้ ไม่ถูกลบหรือบังคับเปลี่ยน
2. **เพิ่มธีมใหม่ "Aurora"** — ภาษาดีไซน์ใหม่ที่เป็น signature พร้อมเอฟเฟกต์พื้นหลัง particle network (เส้นโยงใย) ตอบสนองเมาส์
3. **Theme Registry** — สลับ เก่า / ใหม่ / มืด / สว่าง / ธีมอนาคต ได้จาก Settings + Navbar โดยไม่ต้องแก้โค้ด
4. **ครบวงจร** — Chat, Live Stats, Models, Issues, Hub (ดาวน์โหลดโมเดล), API Docs, Settings + Overview/Home + Command Palette
5. **i18n จริงจัง** — ไทย/อังกฤษตั้งแต่วันแรก ขยายภาษาเพิ่มได้โดยเพิ่มไฟล์ locale
6. **Responsive + a11y** — desktop → tablet → mobile, keyboard navigation, contrast AA
7. **Honest Telemetry (ADR-003)** — กฎเหล็ก: ค่าสถิติต้องวัดจริง หรือแสดง `n/a` — ห้ามสร้างค่าปลอม/สุ่ม/ตกแต่ง โดยเด็ดขาด

### เป้าหมายคุณภาพ
Dashboard ต้องดูและรู้สึกเป็นผลิตภัณฑ์ระดับ Jan.ai / LM Studio — ไม่ใช่หน้า admin ธรรมดา: glass surfaces, gradient identity, micro-interactions, empty/idle states ที่ออกแบบมา ไม่ใช่ข้อความ error เฉยๆ

---

## 2. มติและข้อกำหนด

### 2.1 ที่ผู้ใช้ยืนยันแล้ว ✅
| # | มติ |
|---|------|
| D1 | ฟีเจอร์เสริม **4 อย่างเอาทั้งหมด**: Command Palette (Ctrl+K), Overview/Home Dashboard, Export Chat เป็น Markdown, Desktop Notification |
| D2 | **คง Theme/UXUI/Layout เดิม**ที่ใช้งานอยู่ — ปรับแต่งเพิ่มได้เล็กน้อยโดยไม่กระทบภาพรวม |
| D3 | ต้องมี **ตัวเลือกสลับธีม เก่า / ใหม่ / อื่นๆ (อนาคต)** ใน Settings |
| D4 | ทำงานบน **branch แยก** ก่อน sync ไป main เมื่อทดสอบผ่าน |
| D5 | PM เตรียมแผน/spec → **รอคำอนุมัติ** ก่อนส่ง Dev/QA |
| D6 | **โลโก้ระบบใหม่** — ออกแบบใหม่ให้ดูเป็น Product มืออาชีพ (แทน ⚡ emoji เดิม) → brief §5.4 |
| D7 | **Translation workflow** — เตรียมไฟล์/บริบทส่งต่อ **โมเดลเล็ก/agent แปลภาษา** ทำหน้าที่แปล + ทดสอบ + ตรวจสอบความถูกต้อง (ประหยัด token) แล้วส่งมอบกลับ → รายละเอียด §6.2 |

### 2.2 ค่าแนะนำของ PM — ✅ อนุมัติแล้วทั้งหมด (2026-07-30)
| # | ข้อเสนอ | เหตุผล | ทางเลือกอื่น |
|----|---------|--------|-------------|
| R1 | **Frontend: Preact + Vite** (commit prebuilt assets) | Dashboard 8+ หน้า + i18n + theme registry + particles + palette = ซับซ้อนเกิน vanilla ไฟล์เดียวอย่างมีนัยสำคัญ — ตรงเงื่อนไข "only if needed" ใน ADR; Preact ~3KB API เหมือน React; server ไม่ต้องลง Node เพราะ commit `dist/` ไว้ | Vanilla ES Modules (เคารพ ADR 100% แต่ใช้เวลามากกว่ามาก), Alpine+htmx (กลางๆ) |
| R2 | **Backend: full-stack แบ่งเฟส** — รวม endpoint ใหม่ (Hub search/download+progress, usage history, log tail, config read) ใน branch นี้ | หน้า Hub/Settings/Stats-history ทำไม่ได้จริงถ้าไม่มี backend — จะกลายเป็น placeholder ปลอมซึ่งขัดกฎ honest telemetry | Frontend-only + backend branch ถัดไป (Hub แสดงได้แค่ลิงก์) |
| R3 | **Branch: แยก git worktree** สำหรับ `feature/dashboard-theme` | main มีงานค้าง 6 ไฟล์ที่กำลังปรับแต่ง — worktree ทำให้ main untouched โดยสมบูรณ์ ทำงานสองฝั่งพร้อมกันได้ | commit WIP ก่อนแล้วแตก branch (history ตรงแต่ต้อง commit งานไม่เสร็จ) |

> ✅ **User อนุมัติ R1–R3 ตามที่เสนอทุกข้อ** — พร้อมชื่นชมการทักท้วงเรื่อง backend full-stack ("ดีมากที่คุณทักท้วงและเสนอเพิ่ม") · ข้อเสริมที่เพิ่มรอบนี้: **D6 โลโก้ใหม่** (§5.4) และ **D7 translation workflow ผ่านโมเดลเล็ก** (§6.2)

---

## 3. ขอบเขต: หน้าและฟีเจอร์

### 3.1 แผนผังหน้าทั้งหมด

```
WS Console
├── 🏠 Overview (Home)          [ใหม่]
├── 💬 Chat                     [สร้างใหม่บนของเดิม]
├── 📊 Live Stats               [ทำให้ live จริง + กราฟ]
├── 🧠 Models                   [ยกระดับ]
├── 🐛 Issues                   [restore ของเดิมที่หายไป + ต่อยอด]
├── 🌐 Hub                      [ใหม่ 100% + backend ใหม่]
├── 📖 API Docs                 [ใหม่ in-app]
└── ⚙️ Settings                 [ใหม่]

Overlays: Command Palette (Ctrl+K) · Toasts · Report Issue (global) · Dialogs
```

### 3.2 ส่วนผสมระหว่างของเก่า/ใหม่
- **โค้ด SPA เดิม** (`static/index.html`): **ไม่แก้** ระหว่างพัฒนา — Console ใหม่ serve คู่กันที่ route `/console` (dev) จนกว่าจะอนุมัติ swap
- **ค่าสี/สไตล์เดิม**: extract เป็น token set ชื่อ `classic` (dark) — ความละเอียดระดับ pixel เดิมต้องคงอยู่เมื่อเลือกธีมนี้
- **พฤติกรรมเดิมที่ดี** (think accordion, rAF streaming, per-model settings): port เป็นสเปก ไม่ใช่ copy โค้ด

---

## 4. Theme System

### 4.1 สถาปัตยกรรม 3 ชั้นของ token

```
ชั้นที่ 1  Primitive tokens   --ws-indigo-500: #6366f1    (ค่าสี/ขนาดดิบ — ห้ามใช้ใน component โดยตรง)
ชั้นที่ 2  Semantic tokens    --ws-surface-card, --ws-text-primary, --ws-accent-brand, --ws-status-error
ชั้นที่ 3  Component tokens   --ws-chat-bubble-user-bg, --ws-stat-bar-gradient   (เฉพาะจุด)
```

- ทุก component อ้างอิงชั้น 2/3 เท่านั้น → สลับธีม = สลับค่าชั้น 1-2
- ธีมปัจจุบันมีปัญหา raw `rgba()` กระจายเกิน token — การ extract ธีม `classic` จะ map ค่าเหล่านั้นเข้า token ให้ครบ (งาน Dev P1)

### 4.2 Theme Registry
```ts
interface ThemeDefinition {
  id: string              // 'aurora-dark' | 'classic-dark' | 'aurora-light' | ...
  name: string            // แสดงผล (แปลผ่าน i18n key)
  mode: 'dark' | 'light'
  base?: string           // ธีมแม่ที่สืบทอด token (optional)
  css: string             // path ของไฟล์ token css
  preview: { accent: string; surface: string }  // สำหรับการ์ดเลือกธีม
  particles?: 'constellation' | 'none'          // เอฟเฟกต์พื้นหลัง
  builtin?: boolean
}
```
- Registry = ไฟล์ manifest หนึ่งไฟล์ + ธีมละหนึ่ง CSS token file → **เพิ่มธีมอนาคต = เพิ่ม 2 ไฟล์ ไม่ต้องแตะ core**
- DOM: `<html data-theme="aurora-dark" data-mode="dark">`
- Persistence: `localStorage['ws-theme']`; ค่าเริ่มต้น = `classic-dark` (รักษาประสบการณ์เดิม) + ตรวจ `prefers-color-scheme` สำหรับ first-run เท่านั้น
- สลับได้ 2 จุด: Settings → Appearance (การ์ดพร้อม preview) และ menu ด่วนใน navbar

### 4.3 โหมดสี
- ทุกธีมมีคู่ dark/light (Aurora มาพร้อมกันทั้งคู่; Classic dark ก่อน — light ของ classic = โบนัสถ้าทัน)
- Auto mode: ตาม OS (`prefers-color-scheme`) — เป็นตัวเลือกที่ 3 ใน switcher

---

## 5. Visual Language

### 5.1 ธีม `classic` (คงเดิม)
- ค่าเดิมทั้งหมด: `#0b0f19` canvas, glass `rgba(17,24,39,.75)`, indigo `#6366f1`→cyan `#06b6d4`, radius 6/10/16, Inter + JetBrains Mono, emoji icons
- อนุญาตปรับได้เฉพาะ: focus ring ที่ขาด, contrast จุดที่ต่ำกว่า AA, hover states ที่ไม่สม่ำเสมอ — โดยภาพรวมต้องจำได้ว่าเป็นของเดิม

### 5.2 ธีม `aurora` (ใหม่ — signature)

**แนวคิด**: "แสงออโรร่าเหนือสถานีอวกาศ" — ต่อยอดเอกลักษณ์ indigo→cyan ของโปรเจกต์เป็นสเปกตรัมเต็ม (violet→indigo→cyan→teal) บน canvas ลึก มี constellation particles เป็นสิ่งมีชีวิตพื้นหลัง

| องค์ประกอบ | สเปก |
|-----------|------|
| **พื้นหลัง** | Canvas particle network: nodes ลอยช้า (drift ~12px/s), เชื่อมเส้นเมื่อระยะ < 140px, เส้นโยงไปหา cursor ในรัศมี 180px พร้อมแรงดึงดูดเบาๆ, node ใกล้ cursor สว่างขึ้น; ความหนาแน่นตามพื้นที่จอ (desktop ~60 nodes, mobile ~24); สีอนุภาคตาม accent ของธีม; **ปิดอัตโนมัติ**เมื่อ `prefers-reduced-motion`, tab hidden, หรือ battery saver; สลับปิดได้ใน Settings |
| **Surfaces** | Glass 3 ระดับความลึก (base/raised/overlay) + hairline border 1px แบบ gradient (มุมบนสว่าง) + inner glow บางๆ; hover = border brighten + translateY(-2px) + shadow bloom |
| **Gradient identity** | Brand gradient 4-stop (violet→cyan) ใช้กับ: primary button, active nav, stat bars, logo, selection; มี animated variant (gradient shift 6s) เฉพาะจุด hero/narrow — ไม่ใช้พร่ำเพรื่อ |
| **Typography** | Inter (UI) + **Noto Sans Thai** (ไทย) + JetBrains Mono (code/เลขสถิติ); fluid scale ด้วย clamp(); เลขสถิติใช้ tabular-nums |
| **Iconography** | ระบบคู่: **Lucide SVG** สำหรับ UI เชิงโครงสร้าง (nav, actions, status) + **emoji** สำหรับ accent/บุคลิก (avatar 🤖, หัวข้อหมวด) — emoji คือเสน่ห์ของโปรเจกต์เดิม ไม่ทิ้ง |
| **Motion** | token: `--ws-dur-fast 120ms / base 200ms / slow 320ms`, easing `cubic-bezier(.2,.9,.3,1)` (overshoot เล็กน้อยเฉพาะ card เข้า); numeric tick animation เมื่อค่าสถิติเปลี่ยน; streaming text = rAF batch เหมือนเดิม |
| **Radius / spacing** | scale 4/8/12/16/24; spacing base 4px grid; ความหนาแน่นระดับ dashboard (ไม่ใช่ marketing) |

### 5.3 Light mode
- ไม่ใช่ dark-invert — ออกแบบแยก: canvas `#f6f7fb`, glass ทึบขึ้น (blur น้อยลง), gradient brand คงอยู่แต่ลด glow, เงาเป็น soft diffuse; particle network = เส้นสีเทาอ่อน/indigo 10% opacity

### 5.4 โลโก้ & Brand Identity ใหม่ (มติ D6)

แทนที่ ⚡ emoji เดิมด้วย identity ระดับผลิตภัณฑ์จริง — ใช้กับ navbar (28px), favicon (16px), app icon (512px), boot splash, และ docs

**ข้อกำหนด**
- ทำงานได้ทุกขนาด 16px → 512px โดยยังอ่านออก
- Self-contained SVG — mark เป็น geometry สั่งทำ **ไม่พึ่ง font ภายนอก**
- มีเวอร์ชัน monochrome + full-color · ใช้ได้บนพื้น dark และ light
- ❌ ห้าม: bolt/brain/robot โฉ่งฉ่างทั่วไป, rainbow, neon เดียวบนดำ, gradient หัวข้อสไตล์ template

**Concept หลัก — "Streamline W"**
- โมโนแกรม **W** สร้างจาก streamline โค้ง 3 เส้นไหลขนาน (ซ้ายบน→ขวาล่าง) = ภาพของ weight ที่ stream ผ่าน NVMe → page cache → compute
- เส้นกลางสว่างสุด = hot shard ใน LRU buffer · เส้นท้ายสลายเป็นจุด particle ห่างขึ้น = shard ที่กำลังถูก page เข้ามา
- Gradient ตามทิศทางการไหล violet→indigo→cyan→teal (spectrum เดียวกับธีม aurora)
- ที่ 16px ลดจุด particle เหลือน้อยสุด — silhouette ต้องยังอ่านเป็น W
- **Wordmark "WEIGHT STREAMING"**: letterforms geometry สั่งทำ (หรือ Inter 650 tracking +0.08em เป็น fallback) — ระยะห่างคำกว้างแบบผลิตภัณฑ์ infrastructure ไม่ใช่แอป consumer

**Concept สำรอง — "Strata"**: ชั้นเลเยอร์ 4 ชั้นวางเหลื่อม (memory hierarchy) พร้อมลำแสงพุ่งผ่านชั้นบนสุด — ใช้เมื่อ Streamline W อ่านยากที่ขนาดเล็กเกินแก้

**Deliverables**
| ไฟล์ | ใช้ที่ |
|------|--------|
| `logo.svg` (mark+wordmark) · `mark.svg` · `wordmark.svg` · mono variants | navbar, docs, README |
| `favicon.ico` (16/32) + `favicon.svg` | browser tab |
| `icon-180.png` (apple-touch) · `icon-512.png` | app icon / splash |
| **Boot splash** | หน้าแรกขณะเชื่อมต่อ server: โลโก้ animate เบาๆ (stream lines วาดเข้า) + status line จริง (checking… → connected ✓ แสดง host:port / failed + retry) — แบรนด์โมเมนต์ที่ไม่ใช่ spinner ว่าง และ **ไม่ fake สถานะ** |

**กฎการใช้**: clear space = ความสูง 1 stream รอบ mark · min size 16px · ธีม aurora = glow อ่อนๆ ได้ · ธีม classic = flat · particle background ต้องไม่ชนกับ logo (รัศมี clear รอบ logo)

---

## 6. ระบบ i18n

| ข้อกำหนด | รายละเอียด |
|----------|-----------|
| ภาษาเปิดตัว | `th` (default สำหรับ `navigator.language` ไทย) + `en` (fallback สุดท้าย) |
| โครงสร้าง | `locales/<lang>/<namespace>.json` — namespace: `common, nav, chat, stats, models, issues, hub, docs, settings, errors` |
| กลไก | key-based + interpolation (`{{count}}`) + plural rules (Intl.PluralRules) + relative time (Intl.RelativeTimeFormat — "วันนี้/เมื่อวาน/เก่ากว่า" ของ history grouping) |
| การขยายภาษา | เพิ่มโฟลเดอร์ `locales/<lang>/` = เพิ่มภาษาได้ทันที UI picker แสดงภาษาที่มีไฟล์ครบ |
| Persistence | `localStorage['ws-locale']`; menu เลือกภาษาใน navbar + Settings |
| กฎ | **ห้าม hardcode ข้อความ UI ใน component**; ชื่อผู้ใช้ ("คุณทอม" เดิม) → ตั้งได้ใน Settings → `ws-display-name` ค่าเริ่มต้น "You/คุณ" |
| เนื้อหา vs UI | API docs/examples (code snippet) คงภาษาอังกฤษตามธรรมชาติ; เฉพาะคำอธิบายแปล |

### Translation Workflow — ส่งต่อโมเดลเล็ก (มติ D7)

**หลักการ**: งานสถาปัตยกรรม/implementation ใช้โมเดลหลัก · งานแปล = งานกลไกปริมาณมาก → ส่ง **agent โมเดลเล็ก** พร้อมชุดงานที่ปิดขอบเขตแน่น (ประหยัด token ตามที่ user กำหนด)

```
Dev (โมเดลหลัก)                    Translator agent (โมเดลเล็ก)
   │ เขียน EN strings + keys
   │ ประกอบ Translation Kit ──────────▶ รับเฉพาะ kit (ไม่เห็น codebase)
   │                                    แปล TH → ส่งคืน th/*.json
   │ ◀──────────────────────────────────
   │ verify อัตโนมัติ + QA native check
   │ (ไม่ผ่าน → ส่ง kit กลับ — roundtrip ถูก)
   └─ commit
```

1. **Dev เขียน EN ก่อน** — strings ทั้งหมดใน `locales/en/*.json` (dev lingua franca) · keys ต้องนิ่ง (stable) — เปลี่ยนแล้วต้องอัปเดต kit
2. **Translation Kit** ต่อ batch (batch 1 = P1 shell/components · batch สุดท้าย = full sweep ที่ P5) วางที่ `translation-kit/batch-N/`:
   - `en/*.json` ต้นฉบับ
   - `CONTEXT.md` — แต่ละ namespace ใช้ที่หน้าจอไหน, ข้อจำกัดความยาว, ความหมายของ `{{placeholder}}`, tone guide (ไทยสุภาพกระชับ ระดับผลิตภัณฑ์ไม่ใช่แชท), รายการ **ห้ามแปล** (ชื่อ endpoint, code, brand, token Technik ที่ทับศัพท์)
   - `GLOSSARY.md` — ล็อกคำเดียวต่อศัพท์: model=โมเดล · load=โหลด · unload=ปลดโหลด · buffer=บัฟเฟอร์ · scan=สแกน · issue=ปัญหา (รายงานปัญหา) · theme=ธีม · hit rate=อัตราการฮิต (หรือทับศัพท์ — ตัดสินใจครั้งเดียวใน glossary แล้วใช้ยาว)
   - Agent kit รับโจทย์: "แปลเท่านั้น ห้ามเพิ่ม/ลด key, รักษา `{{var}}`, สงสัยให้ติด note ใน `QUESTIONS.md` ห้ามเดา"
3. **Verify อัตโนมัติ** (script ใน P1): key sets ตรงกัน 100% · `{{var}}` ครบทุกตัว · JSON valid · ความยาวไม่เกิน EN +45% (ไทยมักยาว — เกิน = flag ให้ดูจุดนั้น ไม่ใช่ fail ทั้ง batch)
4. **QA native check**: เปิด UI โหมด `th` (dev override `?locale=th`) spot-check หน้าสำคัญ (nav/chat/stats/errors/dialogs) — ผ่าน = merge · ไม่ผ่าน = ส่ง kit รอบใหม่เฉพาะ namespace ที่มีปัญหา
5. **หนึ่ง batch ต่อครั้ง** — ไม่ส่งทั้งก้อน; glossary คือ single source of truth ข้าม batch

---

## 7. Responsive & Accessibility

### 7.1 Breakpoints
| ชื่อ | ช่วง | Layout |
|------|------|--------|
| Desktop | ≥1280px | sidebar ถาวร 260px + content fluid |
| Laptop | 1024–1279 | sidebar collapse เป็น rail 64px (icons) |
| Tablet | 768–1023 | sidebar ซ่อน (เปิดเป็น drawer), grid 2 คอลัมน์ |
| Mobile | <768 | **bottom navigation bar**, card 1 คอลัมน์, chat เต็มจอ, drawer เป็น bottom sheet |

- Chat บน mobile: composer ติดล่าง safe-area, parameter drawer เป็น sheet, palette เต็มจอ
- Touch targets ≥44px บน mobile; ไม่มี `overflow:hidden` ตายตัวแบบเดิม

### 7.2 Accessibility (AA)
- Contrast ≥ 4.5:1 (text) / 3:1 (UI) ทุกธีม — รวม classic ที่ต้องแก้บางจุด
- Focus ring เห็นชัดทุกธีม (`:focus-visible` outline + offset)
- aria: dialog `role=dialog` + focus trap + Esc ปิด, toast `aria-live=polite`, badge มี text equivalent (ไม่สื่อด้วยสี/emoji ลำพัง)
- Streaming chat: ประกาศ "กำลังตอบ…/ตอบเสร็จ" ผ่าน status region (ไม่ประกาศราย token)
- Particle canvas `aria-hidden` + ปิดตาม `prefers-reduced-motion`
- Keyboard: สลับ tab ได้, palette นำทางทุกหน้า, Enter/Esc ใน dialog ถูกต้อง

---

## 8. Shell, Navigation & Global Components

### 8.1 App Shell
```
┌────────────────────────────────────────────────────────┐
│ Navbar 56px: ☰ | Logo | ⌘K search | status dot | 🌐 TH▾ | 🎨▾ | 👤 │
├───────────┬────────────────────────────────────────────┤
│ Sidebar   │  Page area (router outlet)                  │
│ 260px     │                                             │
│ - Overview│                                             │
│ - Chat    │                                             │
│ - Stats   │                                             │
│ - Models  │                                             │
│ - Issues  │  (badge count ที่ Issues เมื่อมี open)       │
│ - Hub     │                                             │
│ - API Docs│                                             │
│ - Settings│                                             │
│ ─────────│                                             │
│ active    │                                             │
│ model chip│                                             │
└───────────┴────────────────────────────────────────────┘
+ ParticleCanvas (fixed, z-index ต่ำสุด, ทั่วโลก)
+ Toast viewport (ล่างขวา) + Dialog layer + CommandPalette
```

- **Status dot** = `/health` poll 10s (เขียว/เหลือง=degraded/แดง=down + tooltip เวอร์ชัน)
- **Active model chip**: ชื่อโมเดลที่ load อยู่ + คลิกเปิด Models; หลายโมเดล = "+N"
- Hash router (`#/chat`, `#/issues/Report-ISSUE-002` deep-link) + localStorage หน้าล่าสุด

### 8.2 Command Palette (Ctrl+K / Cmd+K)
- fuzzy search: หน้า, คำสั่ง (load/unload/scan/reload), โมเดล, issues (ตาม id/title), settings keys, สลับธีม/ภาษา
- recent + grouped results, keyboard ล้วน, `/` focus search จากที่ใดก็ได้
- backend: ไม่ต้อง — ข้อมูลจาก client state + cache ของ `/v1/models` และ `/v1/issues`

### 8.3 Dialog / Popup Catalog (ตาม workflow จริง)
| Dialog | Trigger | เนื้อหา |
|--------|---------|---------|
| Confirm Destructive | unload/reload(force)/ล้าง history/ลบ conversation | รายละเอียดผล + checkbox "จำคำตอบสำหรับเซสชันนี้" (เฉพาะ unload) |
| Load Model Progress | load model | spinner + ขั้นตอน (mapping…/ready) + ปุ่มยกเลิก; error → inline + suggest รายงานปัญหา |
| Model Detail | คลิกการ์ดโมเดล | metadata + stats ย่อ + actions |
| Issue Detail (drawer) | คลิก issue | §9.5 |
| New Report | global button / error dialog / Issues page | §9.5 — **prefill จาก debug context อัตโนมัติ** |
| Error (global) | API fail ทั่วไป | ข้อความ + code + "คัดลอก debug context" + shortcut เปิด New Report (prefill!) |
| Theme Switcher mini | navbar 🎨 | รายการธีม + mode toggle ด่วน |
| Keyboard Shortcuts (?) | palette / settings | ตารางคีย์ลัด |
| About / Version | settings | เวอร์ชัน, ลิงก์ docs, licenses |
| First-run Onboarding | เข้า Console ครั้งแรก (dismiss ได้) | 3 ขั้น: ยินดีต้อนรับ → สแกน/โหลดโมเดล → เริ่มแชท |

### 8.4 Toasts
- ชนิด: success / info / warning / error + progress variant (ใช้กับ Hub download)
- stack สูงสุด 4, auto-dismiss 4s (error = ค้างจนกดปิด), action button ได้ (เช่น "ดู" หลัง export)

### 8.5 Global "Report Issue"
- ปุ่มใน error dialog + Issues page + Settings → เปิด New Report modal ที่ **prefill debug context** จาก `/v1/debug/context` แล้ว (user เติมคำอธิบายอย่างเดียว) — เปลี่ยนทุก error เป็น feedback loop

---

## 9. สเปกรายหน้า

### 9.1 🏠 Overview (Home) — ใหม่
**Purpose**: สถานะระบบในแวบเดียว + ทางลัด

| โซน | เนื้อหา | Source |
|-----|---------|--------|
| Hero status strip | server up/downtime since load, host:port, priority badge, เวอร์ชัน | `/health` + `/v1/stats.server` |
| Models row | การ์ดโมเดลที่ load อยู่ (arch/quant/residency bar) + quick unload + "โหลดเพิ่ม" | `/v1/models` |
| Activity | การ generate ล่าสุด 5 รายการ (โมเดล/tokens/tok-s/เวลา) — *ต้องมี backend usage history (P4); ก่อน P4 แสดง "เริ่มเก็บข้อมูลหลัง generate ถัดไป" ซื่อๆ* | `/v1/usage/history` |
| Health widgets | Paging demand ล่าสุด, page-cache residency, open issues count (badge → ลิงก์ Issues) | `/v1/stats` + `/v1/issues?status=open` |
| Quick actions | สแกนโมเดล / โหลดโมเดล / เปิดแชท / รายงานปัญหา | — |

- Empty state (ยังไม่มีโมเดล): hero card ชวนสแกน/ไป Hub พร้อม illustration เบาๆ
- Poll visibility-aware 5s เฉพาะแท็บ active

### 9.2 💬 Chat — สร้างใหม่
**Layout**: 3 คอลัมน์โดยพฤตินัย — conversation sidebar (ซ้าย, collapse ได้) · chat canvas (กลาง ≤860px) · parameter drawer (ขวา, เปิด/ปิด)

- **Conversation sidebar**: รายการสนทนาจริง (ของเดิมมีหลอกๆ) — grouping **วันนี้ / เมื่อวาน / เก่ากว่า** ด้วย Intl.RelativeTimeFormat; ต่อ conversation = แยก localStorage key; rename / delete (confirm) / export .md (D1); แสดง model tag ต่อ conversation
- **Model selector**: dropdown ใน toolbar ของ canvas — แสดง loaded models + quant badge + "🌐 หาเพิ่มที่ Hub" ลิงก์; ถ้าไม่มีโมเดล → empty state พาไป Models/Hub
- **Agent mode selector**: dropdown โหมด (Default / Agent) — *Agent mode = UI + system-prompt wiring; server-side tool-execution ยังไม่มี (สถานะเดิม 🟡) — แสดง tooltip "tool execution กำลังพัฒนา" ซื่อๆ ไม่หลอก*
- **Reasoning/Effort selector**: segmented ต่ำ/กลาง/สูง ใน toolbar (ของเดิมซ่อนใน drawer) — *สถานะ server: ส่งได้แต่ยังไม่ execute ฝั่ง server (ตามเอกสาร SPA_CHAT_2_0) → tooltip ตามจริง*
- **Message rendering**: **markdown + code blocks พร้อม syntax highlight + ปุ่ม copy** (ของเดิม textContent ล้วน) — ใช้ sanitizer (DOMPurify-class) + highlighter เบา; XSS-safe = spec requirement ไม่ใช่ tradeoff
- **`<think>` accordion**: port พฤติกรรมเดิม (hold-back partial tag, auto-collapse) — สไตล์ตามธีม
- **Streaming**: SSE `/v1/chat/completions` + rAF batching + sticky-bottom 80px threshold + Stop คงข้อความบางส่วน (พฤติกรรมเดิมที่ดี) + **Desktop Notification เมื่อ generate ยาว (>20 วิ) เสร็จและ tab ไม่ focus** (D1, ขอสิทธิ์ครั้งแรกแบบไม่รบกวน)
- **Composer**: auto-expand textarea, Enter=ส่ง/Shift+Enter=ขึ้นบรรทัด, ปุ่ม stop กลายเป็น send เมื่อ idle, ลากวาง? (อนาคต), character/token estimate เบาๆ
- **System prompt presets**: chips 4 ตัวเดิม (Coding/Writing/Analyst/Concise) + custom preset บันทึกได้
- **Parameter drawer**: temperature / top-p / max_tokens sliders + preset chips + system prompt textarea + per-conversation toggle ("ใช้ค่าเฉพาะบทสนทนานี้")
- **Token footer ต่อข้อความ**: tok/s + tokens (จาก stats payload สุดท้าย) — แสดงเท่าที่มี จริงๆ
- **Export chat**: .md ทั้ง conversation (D1) — frontmatter (model, date, params) + messages

### 9.3 📊 Live Stats — ทำให้ live จริง
**ปัญหาเดิม**: fetch ครั้งเดียวตอนเข้า tab → แก้เป็น poll 2s (เฉพาะ tab active, หยุดเมื่อ hidden, backoff เมื่อ server down)

| โซน | รายละเอียด |
|-----|-----------|
| Model selector strip | เลือกโมเดล (หรือ "ทั้งหมด") — กรองทั้งหน้า |
| Gauge cards (5) | Buffer Hit Rate* · RAM Residency · Generation Speed · Prefetch Accuracy · Paging Demand — ค่าใหญ่ + delta ↑↓ เทียบ poll ก่อนหน้า + honest tooltip |
| **\*หมายเหตุ Hit Rate** | `buffer.hit_rate` = 0 เสมอในการรันจริง (llama.cpp อ่าน mmap ของมันเอง — ADR-003) → การ์ดแสดงค่าจริง (0%) + คำอธิบายสั้น "tracker ไม่เห็นการอ่านของ llama.cpp — ใช้ Paging Demand เป็นสัญญาณหลัก" + ไม่ตกแต่งให้ดูดี |
| Time-series charts | **2 กราฟ**: tok/s และ faults-per-token / disk MB-per-token — *client-side ring buffer เก็บตั้งแต่เปิดหน้า* พร้อม label ชัด "ตั้งแต่เปิดหน้านี้ (session window)" — **ห้ามเคลมว่าเป็น history ถาวร** จนกว่า P4 usage history พร้อม |
| Paging Demand detail | hard/soft faults, disk demand MB/token, source badge (Windows: residency estimate / POSIX: major faults) — แสดง `n/a` + note เมื่อ platform ไม่รองรับ (page_cache = `{}` บน non-Windows) |
| MoE Expert Heatmap | คงของเดิม (16×16, firing glow) + **degrade สำหรับ dense model**: แสดง n_experts=0 → การ์ดเปลี่ยนเป็น "โมเดลนี้ไม่ใช่ MoE — ไม่มี expert routing" ไม่ใช่ heatmap ว่างเฉยๆ |
| Server block | models_loaded/max, priority badge, host:port |
| Idle state | ก่อน generate ครั้งแรก: การ์ด generation/paging = "ยังไม่มีการ generate — สถิติจะปรากฏหลังรันครั้งแรก" พร้อมปุ่มลัดไป Chat |

### 9.4 🧠 Models — ยกระดับ
| โซน | รายละเอียด |
|-----|-----------|
| Loaded models (บน) | ตาราง/การ์ด: id, arch badge, quant badge, size, buffer/context/threads, last_used (relative), status dot; actions: Unload (confirm), Reload(force), "ดูสถิติ" → Stats filtered, "ใช้ในแชท" |
| Scan panel | folder input + Scan + native Browse (`/v1/browse-dir`); ผลลัพธ์: การ์ดโมเดล (name/size/quant/arch/`may_need_upgrade` warning → แนะ `pip install -U llama-cpp-python`); filter/search ในผลสแกน; sort by size/name |
| Load form | model picker จากผลสแกน or path input + native Browse File (`/v1/browse`) + Model ID / BUF(MB) / CTX / threads (default = half cores) + quant advisory: F16/F32/BF16 = warning banner (ข้อมูลจริงจาก ISSUE-011/018), Q2_K = "อาจ echo/garble — แนะนำ Q4_K_M ขึ้นไป" ตาม MODEL_GUIDE |
| Library view (P4+) | โฟลเดอร์ models ที่ตั้งค่า + สถานะ "loaded/on-disk" + **Hub shortcut** สำหรับโมเดลที่ยังไม่มี; *การลบไฟล์ = ไม่อยู่ใน v1 (ความเสี่ยงสูงบน server ไม่มี auth) — บันทึกเป็น future* |
| Default search dirs | แสดงรายการ dirs ที่ scan ให้อัตโนมัติ (รวม Jan models dir) + เพิ่ม `WS_MODELS_DIR` ได้จาก Settings (snippet) |

### 9.5 🐛 Issues — restore + ต่อยอด
> Backend สมบูรณ์อยู่แล้ว (9-state lifecycle, transition matrix, timeline, export, debug context) — งานคือ **คืน UI ที่หายไปจาก v0.13.0 rewrite + ยกกระดับ**

| โซน | รายละเอียด |
|-----|-----------|
| Toolbar | search + filter chips (status: open/triaged/in_progress/fixed/verify_pending/verified/closed/wontfix · severity: low/med/high/critical) + sort + **Export md/json** + "+ รายงานปัญหา" |
| Summary chips | นับตาม severity (สี + emoji + text ครบ — a11y) |
| รายการ | การ์ด: id · title · status badge สี (emoji map เดิม: 🟠 verify_pending ฯลฯ) · severity · created relative · timeline count; คลิก = เปิด drawer |
| Detail drawer | description, steps, expected/actual, **debug context block** (os/python/llama-cpp/model arch — redacted), **timeline** (เหตุการณ์เรียงเวลา), actions ตาม state ที่ user ทำได้ |
| Verify flow (user) | เมื่อ `verify_pending`: ปุ่ม "✅ ยืนยันว่าหายแล้ว" → auto-close / "❌ ยังเป็นอยู่" → reopen in_progress + ช่อง note |
| Maintainer mode | toggle (localStorage) → panel: เปลี่ยน status (เฉพาะ transition ที่ matrix อนุญาต — UI disable ที่ผิดกฎ), severity, root_cause, fix_summary, commit, verify_steps, test_notes — **บังคับ root_cause+fix_summary+verify_steps เมื่อ mark fixed** (ตรงกับ service.py) |
| New Report modal | title (5–200) · description (10–10000) · steps[] · expected · actual · severity select · created_by (= display name) · **auto-attach debug context** (`POST /v1/issues` merge ให้อัตโนมัติ) |
| Empty state | "ยังไม่มีรายงาน — ระบบทำงานราบรื่น 🎉" + คำอธิบายว่า context อะไรจะถูกแนบ (privacy transparency) |

### 9.6 🌐 Hub — ใหม่ 100% (ต้องทำ backend P4 ก่อน/ขนาน)
**Reference UX**: หน้า Hub ของ Jan.ai — search-first, การ์ดโมเดล, one-click download

| โซน | รายละเอียด |
|-----|-----------|
| Search bar | ช่องค้นหา (debounce 400ms) → `GET /v1/hub/search?q=&sort=downloads|likes|recent&limit=` — proxy ไป HuggingFace API กรอง **GGUF เท่านั้น**; แสดง repo/author/downloads/likes/updated |
| ผลลัพธ์ | การ์ดโมเดล: ชื่อ · author · badges (quant ที่มีใน repo — parse filenames, ขนาดไฟล์ต่อ quant) · ปุ่ม "ดูไฟล์" → แผงเลือกไฟล์ GGUF ใน repo (ชื่อ/size/quant guess) → **Download** |
| Download | `POST /v1/hub/download {repo_id, filename, target_dir?}` → server task; UI = toast progress + แถบความคืบหน้า (bytes, %, speed, ETA) ผ่าน SSE `GET /v1/hub/progress/{task_id}`; เสร็จ → "โหลดเลย?" (เรียก models/load ต่อ) |
| Downloads panel | คิว/ประวัติการดาวน์โหลด (status: queued/downloading/done/failed · resume? v1 = retry ใหม่ · ยกเลิกได้) |
| Curated shelves | แถวแนะนำ: "ยอดนิยมสำหรับ 16GB RAM", "MoE ที่รองรับ", "ภาษาไทยดี" — curated list ฝั่ง client (JSON ใน frontend) ลิงก์ไป search; ซื่อ: label "รายการแนะนำโดยทีม" |
| Target dir | ค่าเริ่มต้น = models dir; เปลี่ยนได้ต่อรายการ (browse-dir) |
| Offline/error state | HF unreachable → banner + ลิงก์ "เปิด huggingface.co เอง" + อธิบาย manual drop-in — ไม่ fake รายการ |

### 9.7 📖 API Docs — in-app
**Purpose**: คู่มือเชื่อมต่อทุกแบบที่ server รองรับ (ดึงเนื้อหาจาก `website/pages/api-docs.html` + `docs/IDE_INTEGRATION.md` มาปรับ)

| หมวด | เนื้อหา |
|------|---------|
| Quick start | curl `/v1/chat/completions` + copy button |
| OpenAI-compatible | endpoint, params ที่รองรับ/ignored (`reasoning_effort`, `tools` รับแต่ไม่ execute — บอกตรงๆ), stream format, ตัวอย่าง Python (`openai` SDK base_url) |
| Anthropic-compatible | `/v1/messages` + ข้อควรทราบ: stream path ใช้ plain prompt (quirk ที่ค้นพบ) — เอกสารตามจริง |
| Native + WebSocket | `/v1/generate` SSE grammar (errors in-stream), WS `/v1/stream` protocol + cancel-by-disconnect |
| IDE integration | Cursor / Continue / Claude Code snippets |
| Models API | scan/load/unload + browse dialogs |
| Issues API | CRUD + lifecycle diagram |
| Server info | เวอร์ชัน live, host:port, "เปิด Swagger เต็ม" → `/docs` |

- code tabs (curl/Python/JS) + copy ทุก block; anchor navigation; search-in-page; เนื้อหา markdown-driven (แก้ไขได้โดยไม่แตะ component)

### 9.8 ⚙️ Settings — ใหม่
> ⚠️ Server ปัจจุบัน config ผ่าน env/CLI เท่านั้น ไม่มี runtime write API → Settings ออกแบบ **ซื่อตามความจริง**: อะไรแก้ runtime ได้ = แก้เลย; อะไรต้อง restart = แสดงค่าปัจจุบัน + สร้าง snippet ให้นำไปใช้

| หมวด | รายการ | พฤติกรรม |
|------|--------|----------|
| **Appearance** | ธีม (การ์ด preview จาก registry), mode (dark/light/auto), particle FX on/off + ความหนาแน่น, density (comfortable/compact) | runtime ทันที + persist |
| **Language** | เลือกภาษา (แสดงที่มี locale), display name | runtime + persist |
| **Chat defaults** | temperature/top-p/max_tokens/system preset ค่าเริ่มต้น, notification on/off + ทดสอบ | persist (localStorage) |
| **Server (read)** | host/port, buffer_mb, n_ctx, n_threads, max_models, idle_timeout, lower_priority, models dirs, issues dir — แสดง **ค่าจริงจาก `/v1/config` (P4) + แหล่งที่มา (env/default/cli)** | read-only |
| **Server (apply-on-restart)** | ฟอร์มแก้ค่า → สร้าง `WS_*` env snippet / CLI command ให้ copy + คำอธิบาย "ตั้งค่าก่อนเริ่ม server ครั้งถัดไป" | snippet generator (ซื่อ — ไม่หลอกว่าแก้ live) เมื่อ P4 มี `PATCH /v1/config` สำหรับ subset ปลอดภัย → ค่อยเปิด runtime edit จุดนั้น |
| **Data** | ล้าง chat history (confirm), export/import การตั้งค่า, localStorage usage | — |
| **Diagnostics** | เปิด debug context (`/v1/debug/context`), ดาวน์โหลด log tail (P4), รายงานปัญหา (prefill) | — |
| **About** | เวอร์ชัน, ลิงก์ docs/GitHub, license, เกียรติคุณ | — |

---

## 10. Backend endpoints ใหม่ (Phase 4 — Dev backend)

> ทั้งหมด additive — ไม่แก้ route เดิม, ไม่กระทบ main flow; ฟีเจอร์ frontend ที่ต้องพึ่ง = หมายเหตุใน §9 แล้ว

| Endpoint | วัตถุประสงค์ | หมายเหตุ |
|----------|-------------|----------|
| `GET /v1/hub/search` | proxy HF search กรอง GGUF + parse quant/size จาก filenames | timeout + cache 5 นาที; ไม่ต้อง auth (localhost) |
| `POST /v1/hub/download` | เริ่ม download task (repo_id, filename, target_dir) | stream ด้วย HTTP Range, atomic (tmp→rename), size guard |
| `GET /v1/hub/downloads` | รายการ tasks + status/progress | |
| `GET /v1/hub/progress/{id}` | SSE ความคืบหน้า (bytes/%/speed/eta/status) | |
| `POST /v1/hub/download/{id}/cancel` | ยกเลิก | |
| `GET /v1/usage/history` | ประวัติ generation (ring buffer JSONL 500 รายการ: ts/model/tokens/tok_s/paging สรุป) | hook เข้า wrapper stream ที่มีอยู่; `?limit=&since=` |
| `GET /v1/logs/tail?lines=` | server log tail | **ต้องเดินสาย logging ใหม่**: ring buffer `recent_errors` ที่ dead อยู่ + file handler `data/server.log` |
| `GET /v1/config` | ค่า effective + source (default/env/cli) ต่อ key | อ่านจาก ServerConfig dataclass |
| `PATCH /v1/config` *(v1.1)* | แก้ subset ปลอดภัย runtime (เช่น idle_timeout, max_models) | เฉพาะ key ที่ ModelManager รองรับโดยไม่อาย; ที่เหลือ = 409 + snippet |

**Dependency ใหม่**: `huggingface_hub` (หรือ raw HTTP ไป HF API — ตัดสินใจตอน Dev; แนะนำ raw HTTP เพื่อคง dep footprint ต่ำ) — บันทึกเป็น ADR ย่อย

**ของเก่าที่ควรเคลียร์ (เสนอ, ไม่บังคับใน v1)**: `dashboard_server.py` (fake metrics — ขัด honest telemetry) → ลบเมื่อ merge; dead env vars (`WS_LOG_LEVEL` ฯลฯ) → เดินสายหรือลบ

---

## 11. สถาปัตยกรรม Frontend (ตาม R1: Preact + Vite)

```
frontend/                        (ใหม่, project root)
├── src/
│   ├── main.tsx, App.tsx
│   ├── core/        router(hash) · api-client · sse · poll-manager · store(สัญญาณเล็ก)
│   ├── theme/       registry.ts · tokens/ (classic-dark.css, aurora-dark.css, aurora-light.css…)
│   ├── i18n/        index.ts · useT hook · ../locales/{th,en}/*.json
│   ├── components/  Button Card Dialog Drawer Toast Badge Gauge Chart ParticleCanvas Palette EmptyState …
│   └── pages/       Overview Chat Stats Models Issues Hub Docs Settings
├── locales/         th/ en/ (แยกไฟล์เพื่อให้ทีมแปล/ขยายง่าย)
├── vite.config.ts   build → ../weight_stream/server/static/console/
└── package.json
```

- **State**: Preact signals (เบา, ไม่ต้อง redux-class)
- **Charts**: uPlot หรือ canvas เอง (เบากว่า Chart.js มาก) — กราฟ 2-3 เส้นพอ
- **Markdown**: marked + DOMPurify + highlight.js (core build เลือกภาษา)
- **Icons**: lucide-preact + emoji
- **Serve**: FastAPI mount `/console` (StaticFiles) คู่ `/app` เดิม; หลังอนุมัติ swap: `/` → `/console`, ของเก่า → `/app-legacy` หนึ่ง release
- **CI/build**: `npm run build` แล้ว **commit `static/console/`** — server runtime ไม่ต้องมี Node (รักษาจิตวิญญาณ "pip install แล้วรันได้")
- **ถ้า R1 = vanilla**: โครงสร้างเทียบเท่าเป็น ES modules ล้วน (`static/console/{core,components,pages}/*.js`) + import maps, ไม่มี build — spec ส่วนอื่นคงเดิม

### API client & polling
- `apiJSON` ใหม่: error taxonomy (network / http / stream), base = `location.origin` (แก้ http hardcoded เดิม), timeout + retry idempotent
- **Poll manager**: visibility-aware (หยุดเมื่อ tab hidden), interval ต่อ endpoint, jitter + exponential backoff เมื่อล้ม, single-flight
- Stats history buffer ฝั่ง client (ring 300 จุด) สำหรับกราฟ — label "session window" เสมอ

---

## 12. แผน Branch & Migration (ตาม R3: worktree)

1. **สร้าง worktree**: `~/worktrees/dashboard-theme/` บน branch `feature/dashboard-theme` จาก `main` HEAD — main + งานค้าง 6 ไฟล์ **untouched**
2. Dev/QA ทำงานใน worktree ทั้งหมด; commit ย่อยต่อ phase (conventional commits)
3. ระหว่าง dev: Console ใหม่ที่ `/console` — `/app` เดิมไม่ถูกแตะ (ทดสอบเทียบได้ตลอด)
4. QA ผ่านทุก phase + user approval → **merge → main** แล้วจึง swap route + เคลียร์ legacy
5. main มีงานปรับแต่งค้างชนกัน? — merge ตอนท้ายทำโดย user/PM ด้วย `--no-ff`; คาดว่าชนต่ำ (งาน main อยู่ฝั่ง server core, งานนี้อยู่ frontend + endpoint ใหม่ additive)

### ความเสี่ยง & ข้อผ่อนปรน
| ความเสี่ยง | ผล | การจัดการ |
|-----------|-----|-----------|
| HF download ช้า/ล่ม (โมเดล GB) | UX ค้าง | progress จริง + cancel + retry; ไม่ fake ETA คงที่ |
| ไม่มี auth + CORS `*` | Hub download = เขียนไฟล์จาก internet สู่เครื่อง | จำกัด target_dir ใน models dirs เท่านั้น + localhost premise + เตือนใน Settings; auth = out-of-scope v1 (บันทึก) |
| Preact build ต้อง commit dist | repo ใหญ่ขึ้น | dist ~150KB gzip — ยอมรับได้; .gitignore source maps |
| Classic theme extract ไม่ตรง pixel เดิม | ผู้ใช้เดิมรู้สึกเปลี่ยน | QA มี screenshot diff กับ `docs/verification/` เดิม เป็น gate |
| i18n ไม่ครบ key | UI ผสมภาษา | lint script ตรวจ missing keys เป็น QA gate |
| Stats "live" หนักเครื่อง | CPU จาก polling | 2s + หยุดเมื่อ hidden + backoff; particle ปิดตาม reduced-motion/battery |
| Agent mode/effort ไม่มี server contract | UI หลอกผู้ใช้ | tooltip ตามจริงทุกจุด (honest-telemetry กินความถึง capability ด้วย) |

---

## 13. Workflow & เกณฑ์จบราย Phase

```
P0 ✅ PM: สำรวจ (3 agents) → spec นี้ → [รอ user อนุมัติ + ยืนยัน R1-R3]
─────────────────────────────────────────────────────────────────
P1 Dev: core/theme/i18n/router/shell/particles/components
       + **โลโก้ใหม่** (§5.4: SVG set + favicon + boot splash)
       + i18n batch 1: EN strings → translation kit → **small-model agent แปล TH** (§6.2) → verify
   QA: ธีม classic = pixel เดิม (screenshot gate) · aurora dark/light สลับได้ ·
       TH/EN ครบ · responsive 4 breakpoints · reduced-motion ปิด particle · a11y scan
       · โลโก้ชัดที่ 16px/512px ทั้ง dark/light · splash แสดงสถานะจริง
P2 Dev: Overview + Chat + Live Stats + Models
   QA: markdown+copy ปลอดภัย · streaming/stop · stats poll+idle states ·
       hit-rate caveat แสดง · heatmap degrade dense · load/unload/scan flows
P3 Dev: Issues (restore เต็ม) + API Docs + Settings
   QA: lifecycle ครบ 9 state + transition matrix บังคับ · verify loop ·
       maintainer panel · docs copy blocks · settings snippet generator
P4 Dev: backend endpoints ใหม่ (§10) + tests (pytest)
   QA: API contract tests · download progress จริง · history ring buffer ·
       ไม่กระทบ endpoint เดิม (regression suite 93 tests ต้องเขียว)
P5 Dev: Hub page + polish (light theme tune, palette, notifications, export)
       + i18n batch สุดท้าย: **full TH sweep ผ่าน small-model agent** + native check
   QA: full regression · E2E ค้นหา→ดาวน์โหลด→โหลด→แชท · responsive/i18n sweep ·
       honest-telemetry audit (ไม่มีค่าปลอม/เคลมเกินจริงทุกหน้า)
─────────────────────────────────────────────────────────────────
P6 PM: สรุปผล + demo → [user อนุมัติสุดท้าย] → merge + route swap + CHANGELOG
```

- ทุก phase: Dev → QA → PM ตรวจ spec → loop แก้จน gate ผ่าน → phase ถัดไป
- PM checkpoint รายงาน user ทุก phase จบ (ไม่หายเงียบ)
- **Definition of Done รวม**: pytest เขียว · ไม่มี console error · honest-telemetry audit ผ่าน · TH+EN ครบ · dark+light + 4 breakpoints · keyboard ล้วนใช้งานได้

---

## 14. อนาคต (ไม่อยู่ใน v1 — ออกแบบรองรับไว้แล้ว)
- ธีมชุมชน: registry + manifest รองรับ drop-in อยู่แล้ว
- Agent tool execution ฝั่ง server (ปลดล็อก Agent mode เต็ม) — UI พร้อมรอ
- Auth/token เมื่อต้องการ bind LAN — เพิ่ม middleware ไม่กระทบ frontend
- Model delete / auto-load startup (`WS_AUTO_MODEL_*` dead code → เดินสายจริง)
- ภาษาที่ 3+ — เพิ่มโฟลเดอร์ locale
- PWA/offline — asset structure พร้อม

---

## 15. รายการรอตัดสินใจ (Approval Checklist)
- [x] อนุมัติ spec ภาพรวม ✅ (2026-07-30)
- [x] R1: **Preact + Vite** ✅
- [x] R2: **Backend full-stack แบ่งเฟส** ✅ (user ชื่นชมการทักท้วงเรื่องนี้)
- [x] R3: **Git worktree** ✅
- [x] ชื่อ Console + ชื่อธีม ("Weight Streaming Console" / "Aurora") — ถือว่าอนุมัติตามเสนอ
- [x] อนุมัติเริ่ม P1 ✅ + ข้อเสริม **D6 โลโก้ใหม่** · **D7 translation workflow โมเดลเล็ก**
