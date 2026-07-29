# 🎨 SPA Redesign Master Plan: Chat 2.0 & Stats Dashboard

> **โปรเจกต์:** `weight-streaming` (`D:\.opencode\.Weight-Streaming`)  
> **สถานะ:** 🟡 Implemented in part; reliability validation and streaming follow-up remain  
> **วันที่:** 2026-07-28  
> **เป้าหมาย:** ปรับปรุงโฉมหน้า UI/UX ทั้งหมดของระบบ SPA (Chat + Stats + Settings) ให้สวยงาม ปราณีต ระดับ ChatGPT / Claude / Jan Desktop พร้อมระบบ Agent Tools, Reasoning Effort, และ Native Chat Template

---

## สถานะจริง ณ 2026-07-28

| Work item | Status | Evidence / remaining work |
|-----------|--------|---------------------------|
| Collapsible SPA chat layout, history, settings drawer | ✅ | Implemented in `weight_stream/server/static/index.html` |
| Native template for chat | ✅ | Server uses `llama-cpp-python.create_chat_completion()`; manual formatter is fallback |
| Sampling controls | ✅ | Temperature, max tokens, and `top_p` are sent from SPA |
| Reasoning effort and tools | 🟡 | UI/schema fields exist; no server-side tool execution contract is implemented |
| Live metric dashboard | 🟡 | UI exists, but real stream telemetry is incomplete while server bypasses the wrapper |
| Responsive stream / low browser CPU | ⬜ | Implement item 4 in `docs/HANDOFF_STREAMING_RELIABILITY.md` |
| Wrapper-backed streaming and real telemetry | ⬜ | Implement item 5 in `docs/HANDOFF_STREAMING_RELIABILITY.md` |

Do not treat this plan as proof of completed functionality; use the handoff acceptance checks and a real GGUF + SPA run for release validation.

---

## 📋 1. สรุปปัญหาและสิ่งที่ต้องพัฒนา (Problems & Enhancements)

### 💬 หน้า Chat (Chat 2.0 Upgrade)
| # | ปัญหา / ความต้องการเดิม | แนวทางแก้ไขใน Chat 2.0 |
|---|------------------------|------------------------|
| 1 | UI ดูเป็น Plain HTML Form ยุคเก่า ไม่สวยงาม | เปลี่ยน Layout เป็น **Collapsible Sidebar + Fluid Chat Canvas (Max-width 800px)** พร้อมธีม Deep Space Dark Glassmorphism |
| 2 | โมเดลตอบเพี้ยน วนคำถาม (โดยเฉพาะ Q2_K) | ดึง **Native Jinja Chat Template** จาก GGUF Metadata อัตโนมัติ (รองรับ ChatML, Llama3, DeepSeek) |
| 3 | ไม่รองรับการสั่งงาน Agent / Tools | เพิ่มระบบ **Agent Tool Calling (Function Calling UI)** และ **Thinking / Reasoning Display (`<think>`)** |
| 4 | ตั้งค่าการตอบไม่ได้ครอบคลุม | เพิ่ม **Reasoning Effort Slider (Low/Med/High)**, Temperature, Top-P, Max Tokens, และ System Prompt Presets |
| 5 | ช่องพิมพ์ข้อความไม่สะดวก | ใช้ **Auto-expanding Textarea** (Shift+Enter = ขึ้นบรรทัดใหม่, Enter = ส่ง) + 1-Click Code Copy |

### 📊 หน้า Stats (Stats Dashboard Overhaul)
| # | ปัญหาเดิม | แนวทางแก้ไขใน Stats Dashboard |
|---|-----------|-------------------------------|
| 1 | การแสดงผลเป็นการ์ดตัวเลขธรรมดา ดูนิ่งๆ | เปลี่ยนเป็น **Interactive Analytics Dashboard** พร้อม Live Gauge Bars และ Progress Indicators |
| 2 | ค่ามักเป็น 0 เมื่อไม่ได้รัน Generation | ดึงข้อมูลระบบ Real-time Telemetry (`/v1/stats` + Windows Page Monitor `QueryWorkingSetEx`) |
| 3 | ไม่เห็นภาพการทำ Expert Streaming | เพิ่ม **Active Expert Heatmap Grid** แสดงจุดที่ Expert กำลังทำงานแบบ Live |

---

## 🏗️ 2. รายละเอียดสถาปัตยกรรม UI/UX ใหม่ (Architecture & Components)

### 2.1 โครงสร้างหน้าจอหลัก (Main Layout Structure)

```text
┌──────────────────────────────────────────────────────────────────────────────────┐
│  Weight-Streaming SPA 2.0                                                        │
├───────────────┬──────────────────────────────────────────────────────────────────┤
│ 📂 Sidebar    │ 💬 Main Canvas (Chat / Stats / Models Tabs)                      │
│ (Collapsible) │ ┌──────────────────────────────────────────────────────────────┐ │
│               │ │ 🤖 Model: [ Qwen2.5-Coder-7B (Q4_K_M) ▼ ]  ⚡ 18.5 tok/s      │ │
│ ➕ New Chat   │ └──────────────────────────────────────────────────────────────┘ │
│               │                                                                  │
│ 🔍 Search     │  🧠 Reasoning (<think>):                                         │
│               │  ┌────────────────────────────────────────────────────────────┐ │
│ 🕒 Today      │  │ Analyzing Python WebSocket requirements...                 │ │
│  • WebSockets │  └────────────────────────────────────────────────────────────┘ │
│  • Data Audit │                                                                  │
│               │  🤖 Assistant:                                                   │
│ 🗓️ Yesterday  │  Here is the Python WebSocket client code:                       │
│  • Weight-Sim │  ```python                                              [📋Copy]│
│               │  import websockets                                               │
│               │  ```                                                             │
│ 🛠️ Tools      │                                                                  │
│ [x] WebSearch │ ┌──────────────────────────────────────────────────────────────┐ │
│ [x] CodeExec  │ │ ✍️ Type a message or /command...                     [Send ➔]│ │
│               │ └──────────────────────────────────────────────────────────────┘ │
│ ⚙️ Settings   │ 🧠 Effort: Medium · 🌡️ Temp: 0.3 · 📏 Max: 512 · 🛠️ 2 Tools Active  │
└───────────────┴──────────────────────────────────────────────────────────────────┘
```

---

## 🛠️ 3. แผนการดำเนินงานและมอดูลที่จะปรับปรุง (Implementation Steps)

### Step 1: Native GGUF Chat Template & Reasoning Parser
- **ไฟล์:** `weight_stream/server/model_manager.py` & `weight_stream/server/openai_compat.py`
- **การเปลี่ยนแปลง:**
  - เพิ่มฟังก์ชันอ่าน `tokenizer.chat_template` จาก GGUF Metadata
  - แยกแท็ก `<think>...</think>` ใน Output Stream เพื่อส่งกลับไปยัง UI ในรูปแบบ Reasoning Chunk

### Step 2: Agent Tools & Response Effort System
- **ไฟล์:** `weight_stream/server/schemas.py` & `weight_stream/server/api_server.py`
- **การเปลี่ยนแปลง:**
  - เพิ่ม Schema รองรับ `tools` และ `reasoning_effort` (`low`, `medium`, `high`)
  - เพิ่ม Endpoint `/v1/tools` สำหรับเลือกเปิด/ปิดการใช้งาน Tools (เช่น Web Search, Code Execution, File Reader)

### Step 3: Redesign SPA HTML Layout (`index.html`)
- **ไฟล์:** `weight_stream/server/static/index.html`
- **การเปลี่ยนแปลง:**
  - สร้างโครงสร้าง Collapsible Sidebar ด้านข้างซ้าย
  - ย้าย Chat History มาอยู่ใน Sidebar จัดหมวดหมู่ตามเวลา (Today / Yesterday / Older)
  - เพิ่ม Drawer พาแนลตั้งค่าทางขวาสำหรับเลือก Presets, Reasoning Effort, และ Tools

### Step 4: Redesign Stats Dashboard
- **ไฟล์:** `weight_stream/server/static/index.html`
- **การเปลี่ยนแปลง:**
  - สร้าง Live Metric Cards: NVMe Bandwidth Gauge, WorkingSet RAM Residency Meter, Buffer Hit/Miss Rate Chart
  - สร้าง Active Expert Grid Heatmap 896 ช่อง (สำหรับ MoE Models) แสดงสถานะการ Firing แบบ Live

### Step 5: Styles & Visual Polish (Glassmorphism & Micro-animations)
- **ไฟล์:** `weight_stream/server/static/index.html` (CSS Section)
- **การเปลี่ยนแปลง:**
  - ธีม Deep Space Dark (`#0b0f19` background) ร่วมกับ Backdrop Filter Blur
  - Prism.js / Highlight.js Style Code Blocks พร้อม 1-Click Copy Button
  - Auto-expanding Textarea height (1 to 8 lines)

---

## 🧪 4. แผนการทดสอบและความถูกต้อง (Verification Plan)

1. **การทดสอบ UI & Responsive Layout:**
   - ทดสอบการย่อ/ขยาย Sidebar บนหน้าจอคอมพิวเตอร์และโน้ตบุ๊ก
   - ทดสอบการกดปุ่ม Copy Code บนบล็อกโค้ดตัวอย่าง
2. **การทดสอบ Prompt Template & Reasoning:**
   - ทดสอบส่งคำถามกับโมเดล Qwen / Llama 3 ตรวจสอบว่า Special Tokens ไม่รั่วไหล และแท็ก `<think>` ถูกแยกแสดงผลอย่างสวยงาม
3. **การทดสอบ Stats Dashboard:**
   - ทดสอบเปิดหน้า Stats ระหว่างที่โมเดลกำลังสร้างคำตอบ ตรวจสอบว่า Meter และ Gauge เคลื่อนไหวตามจริง

---

*สร้างโดย Antigravity AI — พร้อมเริ่มลงมือทำตามขั้นตอนทันทีหลังได้รับการยืนยัน*
