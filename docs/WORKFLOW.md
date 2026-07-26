# Project Workflow — Speculative Weight Streaming

> ⚠️ **กฎบังคับสำหรับทุก session** — ทั้ง AI agent และคน ต้องปฏิบัติตาม workflow นี้  
> **วัตถุประสงค์:** ให้มีความต่อเนื่อง — รู้สถานะ รู้ decision trail รู้ problems รู้ว่าต้องทำอะไรต่อ

---

## 📋 สารบัญ

1. [Every Session Checklist](#1-every-session-checklist)
2. [When to Create/Update Each File](#2-when-to-createupdate-each-file)
3. [Decision-Making Protocol](#3-decision-making-protocol)
4. [Experiment Protocol](#4-experiment-protocol)
5. [Problem Resolution Protocol](#5-problem-resolution-protocol)
6. [Versioning & Release](#6-versioning--release)
7. [Communication Standards](#7-communication-standards)
8. [Quick Reference Card](#8-quick-reference-card)

---

## 1. Every Session Checklist

### 🔵 ก่อนเริ่มทำงาน (Start of Session)

```
☐ 1. อ่าน SESSION_LOG.md — session ก่อนทำอะไรไป? ค้างตรงไหน?
☐ 2. อ่าน TASKS.md — รู้ backlog ปัจจุบัน
☐ 3. อ่าน docs/DECISIONS.md — รู้ context การตัดสินใจล่าสุด
☐ 4. อ่าน docs/WORKFLOW.md — ทบทวน workflow (file นี้)
☐ 5. ตรวจสอบ git status — branch, dirty files, มี commit ที่ยังไม่ push?
☐ 6. ดู CHANGELOG.md — version ล่าสุดคืออะไร
```

### 🟡 ระหว่างทำงาน (During Work)

```
เมื่อตัดสินใจอะไร → บันทึก ADR (docs/DECISIONS.md)
เมื่อเริ่มทดลอง → สร้าง experiment entry (research/experiments/EXP-NNN/)
เมื่อใช้คำศัพท์ใหม่ → เพิ่มใน GLOSSARY (docs/GLOSSARY.md)
เมื่อเริ่ม task → อัปเดต TASKS.md (Backlog → In Progress)
เมื่อเสร็จ task → อัปเดต TASKS.md (In Progress → Done)
```

### 🟢 เมื่อจบ session (End of Session)

```
☐ 1. เขียน SESSION_LOG.md entry ใหม่
    ├── session code (S000), วันที่, หัวข้อ
    ├── เป้าหมาย → ทำได้จริงไหม?
    ├── สิ่งที่ทำ (✅)
    ├── การตัดสินใจ (⚡)
    ├── ปัญหา + วิธีแก้ (🐛)
    └── ขั้นตอนถัดไป (⏭️)
    
☐ 2. อัปเดต TASKS.md — สถานะ task ล่าสุด
    
☐ 3. ตรวจสอบว่ามีอะไรต้องบันทึกเพิ่ม:
    ├── ADR ใหม่ที่ยังไม่ได้เขียน?
    ├── GLOSSARY คำใหม่ที่ยังไม่ได้เพิ่ม?
    ├── experiment result ที่ยังไม่ได้บันทึก?
    
☐ 4. อัปเดต CHANGELOG.md ถ้า version เปลี่ยน
    
☐ 5. Commit งาน
    ├── git add เฉพาะไฟล์โปรเจคนี้
    ├── commit message ระบุ: version, what, why
    └── (push รอคำสั่ง)
```

---

## 2. When to Create/Update Each File

| ไฟล์ | สร้างเมื่อ | อัปเดตเมื่อ | ใครทำ |
|------|-----------|-----------|-------|
| `SESSION_LOG.md` | Session แรก | **ทุก session** (จบ) | AI + คน |
| `docs/DECISIONS.md` | ตัดสินใจครั้งแรก | ทุกครั้งที่มี architectural decision | AI (ยืนยันกับคน) |
| `docs/GLOSSARY.md` | มีคำศัพท์แรก | ทุกครั้งที่มีคำศัพท์ใหม่ | AI |
| `TASKS.md` | Task แรก | **ทุก session** (เริ่ม/จบ task) | AI + คน |
| `research/experiments/` | การทดลองแรก | ทุกครั้งที่มี experiment | AI + คน |
| `docs/CONCEPT.md` | Initial concept | เมื่อแนวคิดเปลี่ยน | AI (ยืนยันกับคน) |
| `CHANGELOG.md` | Project เริ่ม | **ทุก version** | AI |
| `PROJECT.md` | Project เริ่ม | เมื่อ scope/architecture เปลี่ยน | AI (ยืนยันกับคน) |

> **กฎ:** ถ้า session ไหนไม่ได้อัปเดตไฟล์ที่ควรอัปเดต → session นั้น incomplete

---

## 3. Decision-Making Protocol

### ต้องบันทึก ADR เมื่อ:

```
☐ เลือก architecture / design approach
☐ เลือก technology / tool / framework
☐ เปลี่ยน direction ที่มีผลต่อ architecture
☐ Tradeoff ที่สำคัญ
☐ ลงทุน effort มากกว่าครึ่งวันกับทางเลือกใดทางเลือกหนึ่ง
```

### รูปแบบ ADR:

```markdown
## ADR-NNN: หัวข้อ

| รายการ | รายละเอียด |
|--------|-----------|
| **วันที่** | YYYY-MM-DD |
| **สถานะ** | ✅ Accepted / 🔄 Proposed / ❌ Superseded |
| **Context** | ปัญหาหรือสถานการณ์ |

### ตัวเลือกที่พิจารณา
- ...

### การตัดสินใจ
เลือก ... เพราะ ...

### เหตุผล
1. ...

### Consequences
- ✅ Positive: ...
- ⚠️ Negative: ...

### Revisit เมื่อ
- เงื่อนไขที่ทำให้ decision นี้ต้อง reconsider
```

### ขั้นตอน:

```
1. AI เสนอ decision พร้อม options
2. คนเลือก หรือ approve
3. AI บันทึก ADR
4. ถ้าตัดสินใจแล้ว later revisit → update สถานะ ADR
```

---

## 4. Experiment Protocol

### ต้องบันทึก experiment เมื่อ:

```
☐ เริ่มทดสอบสมมติฐาน
☐ วัด performance / latency / accuracy
☐ เปรียบเทียบ approaches
☐ ทดสอบ parameter sensitivity
```

### รูปแบบ experiment:

```markdown
## EXP-001: หัวข้อ

### Hypothesis
### Setup (model, hardware, parameters, metrics)
### Method
### Results (raw data)
### Analysis
### Conclusion + Action
```

### กฎสำคัญ:
- **Save raw data** — อย่าทิ้ง numbers
- **Record unexpected findings** — บ่อยครั้งที่ gold อยู่ตรงนี้
- **Don't cherry-pick** — failures มีค่าเท่ากับ successes
- **Reproducible** — setup ต้อง detail พอให้คนอื่นทำตามได้

---

## 5. Problem Resolution Protocol

### เมื่อเจอปัญหา:

```
1. 🔴 หยุด — อย่าแก้โดยไม่เข้าใจ
2. 📝 บันทึก:
   └── SESSION_LOG.md (🐛 section)
   ├── อาการ (Symptom)
   ├── สาเหตุ (Root Cause)
   ├── วิธีแก้ (Solution)
   └── วิธีป้องกัน (Prevention)
3. ถ้าเป็น recurring problem → สร้าง fix เป็น permanent
4. อัปเดต GLOSSARY ถ้ามี terminology ใหม่จาก bug
```

### รูปแบบ:

```markdown
### 🐛 ปัญหา: [หัวข้อ]
- **Symptom:** ...
- **Root Cause:** ...
- **Solution:** ...
- **Prevention:** ...
```

### ทำไมสำคัญ:
- Session ถัดไปไม่ต้องเสียเวลา debug ซ้ำ
- ป้องกัน same mistake
- สะสมเป็น knowledge base

---

## 6. Versioning & Release

ใช้ **Semantic Versioning** (`MAJOR.MINOR.PATCH`)

| Version bump | เมื่อ | ตัวอย่าง |
|-------------|------|---------|
| **MAJOR** | Architecture change, breaking changes | 1.0.0 → 2.0.0 |
| **MINOR** | Feature เพิ่ม, วิจัย phase ใหม่ | 0.1.0 → 0.2.0 |
| **PATCH** | Bug fix, docs update, tiny changes | 0.1.0 → 0.1.1 |

### ขั้นตอนการ release:

```
1. อัปเดต CHANGELOG.md — version + changes + files
2. อัปเดต version references ใน docs (ถ้ามี)
3. Commit
4. (รอคำสั่ง push)
```

### ข้อความ commit:

```
feat: [type] หัวข้อ vX.X.X

- สิ่งที่ 1
- สิ่งที่ 2
- รวม [N] ไฟล์, [+N/-N บรรทัด]
```

---

## 7. Communication Standards

### ภายในโปรเจคนี้:
- ภาษา: **ไทย** (หลัก)
- ใช้คำศัพท์ตาม GLOSSARY
- สรุปให้กระชับ ใช้ตาราง + bullet points
- บอกสถานะเสมอ: ✅ เสร็จ / 🔄 กำลังทำ / ⬜ ยังไม่เริ่ม / ❌ ติดปัญหา

### การ escalate:

```
⚠️ [สถานการณ์]
→ แจ้งปัญหา
→ เสนอทางเลือกที่มี
→ ถาม user ว่าจะเอายังไง
```

---

## 8. Quick Reference Card

### 🔵 เริ่ม session:

```
1. SESSION_LOG → session ล่าสุด
2. TASKS → backlog
3. DECISIONS → context
4. git status
```

### 🟢 จบ session:

```
1. SESSION_LOG entry ใหม่
2. TASKS อัปเดต
3. ADR/GLOSSARY/experiments เช็คค้าง
4. CHANGELOG (ถ้า version เปลี่ยน)
5. commit
```

### ⚡ เมื่อตัดสินใจ → ADR
### 🐛 เมื่อเจอปัญหา → SESSION_LOG (🐛)
### 🧪 เมื่อทดลอง → experiments/

---

> **Workflow นี้ live ตั้งแต่ 2026-07-27** — ถ้าพบ workflow ที่ดีกว่า → อัปเดตผ่าน ADR
