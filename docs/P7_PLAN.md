# 🗺️ P7 Plan — Jan-style Chat Controls + Assistant + MCP + Offline-First

> **Status:** 📋 วางแผน (ยังไม่เริ่ม) · **Date:** 2026-08-04
> **ที่มา:** Research Jan desktop (jan.ai/docs) + มติผู้ใช้ 2026-08-04
> **ลำดับ:** หลัง P6 (merge worktree → main) เสร็จ
> **หลักการ:** เอาแบบ Jan ที่ทำงานจริง + **ดีกว่า Jan ตรง offline-first**

---

## 🎯 เป้าหมาย P7

ยกระดับระบบแชท/API ให้เป็น **Local AI Server ครบวงจรแบบ Jan** แต่มีจุดแข็งเพิ่ม:
1. **Reasoning Mode จริง** (Auto/On/Off) — ควบคุม llama.cpp ได้จริง ไม่ใช่ display-only
2. **Assistant management** — สร้าง/จัดการ assistant (system prompt + model + params)
3. **MCP ทั้ง 2 ทาง** — จัดการ MCP เอง (host) + รองรับ tool-calling protocol (IDE ต่อเข้า)
4. **⚠️ Offline-first** — ใช้งานโมเดล local ได้จริงแม้ไม่มีเน็ต (จุดที่ Jan พัง!)

---

## 📌 ข้อกำหนดผู้ใช้ (2026-08-04)

| # | ข้อกำหนด | รายละเอียด |
|---|---------|-----------|
| 1 | **Chat controls แบบ Jan** | ทุกอย่างยกเว้นปุ่มสมอง เอาแบบ Jan (model params, per-model settings) |
| 2 | **Assistant management** | ระบบจัดการ Assistant (แบบ Jan: สร้าง/แก้ไข/เลือก assistant) |
| 3 | **MCP จัดการเอง** | ระบบจัดการ MCP servers ของเราเอง (host) |
| 4 | **Tool-calling protocol** | รองรับ tools/tool_calls/tool role ให้ IDE ต่อเข้า |
| 5 | **⚠️ Offline-first (สำคัญมาก)** | ใช้งานโมเดล local ได้จริงแม้ไม่มีเน็ต — Jan พังตอนเน็ตหลุด เราต้องไม่พัง |

---

## 🏗️ สถาปัตยกรรม P7 (อ้างอิง Jan)

### A. Reasoning Mode จริง (Auto/On/Off)

**วิธีที่ Jan ทำ (ต้องเลียนแบบ):**
- ปุ่มสมองโชว์ **เฉพาะโมเดลที่รองรับ extended thinking** (DeepSeek-R1, QwQ)
- Auto/On/Off ควบคุมผ่าน llama.cpp จริง (ไม่ใช่แค่ UI)
- per-model + ไม่ต้อง reload

**งานที่ต้องทำ:**
```
backend:
  - ตรวจว่าโมเดลรองรับ reasoning ไหม (จาก GGUF metadata / arch)
  - รับ reasoning_mode: auto|on|off → ส่งไป llama.cpp
  - ใช้เทคนิค: sampling config / grammar / system prompt injection
  - expose /v1/models/{id}/capabilities (reasoning, tools, vision)

frontend:
  - ปุ่มสมอง 3 สถานะ (Auto/On/Off) — โชว์เฉพาะโมเดลที่รองรับ
  - per-model จำไว้ (localStorage)
```

### B. Assistant Management (แบบ Jan)

**วิธีที่ Jan ทำ:**
- สร้าง assistant: system prompt + model + params (temperature, context, etc.)
- เลือก assistant ใน chat
- เก็บเป็นไฟล์ (Jan ใช้ ~/jan/assistants/)

**งานที่ต้องทำ:**
```
backend:
  - CRUD /v1/assistants (สร้าง/แก้ไข/ลบ/เลือก)
  - เก็บเป็น JSON ใน data/assistants/
  - assistant = { id, name, system_prompt, model_id, params }

frontend:
  - หน้า/panel จัดการ assistants
  - เลือก assistant ใน chat toolbar
  - ใช้ system prompt + params ของ assistant
```

### C. MCP — ทั้ง 2 ทาง

**ทางที่ 1: จัดการ MCP เอง (host) — แบบ Jan**
```
backend:
  - MCP client (เชื่อมต่อ MCP servers: stdio/SSE)
  - CRUD /v1/mcp/servers (เพิ่ม/ลบ/เปิด/ปิด)
  - เก็บ config ใน data/mcp/
  - tool execution: execute-on-server toggle (แบบ Jan)
  - permission: approve per-tool-call หรือ allow-all

frontend:
  - หน้า MCP servers (Settings)
  - tool call cards ใน chat (แสดง args + approve/deny)
```

**ทางที่ 2: Tool-calling protocol (IDE ต่อเข้า)**
```
backend:
  - รับ tools: [...] ใน /v1/chat/completions
  - ส่งให้ llama.cpp → คืน tool_calls
  - รับ role: tool messages
  - (ไม่ต้องรู้จัก MCP — IDE จัดการเอง)

frontend:
  - (ไม่ต้องทำ — เป็น API สำหรับ IDE)
```

### D. ⚠️ Offline-First (จุดที่เราต้องดีกว่า Jan)

**ปัญหาของ Jan (จากผู้ใช้):** เน็ตหลุด → ใช้โมเดล local แทบไม่ได้

**สาเหตุที่ Jan พัง (วิเคราะห์):**
- Jan พึ่ง cloud services สำหรับบางอย่าง (model list, telemetry, auth)
- UI อาจพยายาม fetch อะไรที่ต้องใช้เน็ต → hang/error

**หลักการ Offline-First ของเรา:**
```
1. ทุกอย่างที่จำเป็นต้องใช้ local ก่อน:
   - model list: จาก local scan (ไม่พึ่ง HF)
   - assistant: local JSON
   - MCP: local config (stdio servers ทำงาน offline ได้)
   - telemetry: local เท่านั้น

2. สิ่งที่ต้องใช้เน็ต = optional + graceful:
   - Hub search/download (HF) → offline = แสดง banner "offline" ไม่พัง
   - Cloud providers → ไม่มี = ซ่อน
   - MCP remote (SSE) → offline = แสดงสถานะ disconnected

3. Design rule: "local-first, cloud-optional"
   - ทุกหน้า/ฟีเจอร์ต้องทำงานได้ 100% โดยไม่มีเน็ต
   - สิ่งที่ต้องเน็ต = แสดงสถานะชัดเจน ไม่ hang ไม่ error
```

---

## 📋 ขอบเขต P7 (แบ่งเป็น sub-phases)

| Sub-phase | เนื้อหา | ขึ้นกับ |
|-----------|---------|--------|
| **P7.1** | Model capabilities API + Reasoning Mode จริง (Auto/On/Off) | backend llama.cpp |
| **P7.2** | Assistant management (CRUD + UI) | P7.1 |
| **P7.3** | Tool-calling protocol (tools/tool_calls/tool role) | P7.1 |
| **P7.4** | MCP host (จัดการ MCP servers + execute + permission) | P7.3 |
| **P7.5** | Offline-first audit + hardening (ทุกหน้า/ฟีเจอร์) | ทั้งหมด |

---

## 🧪 เกณฑ์จบ P7 (draft)

1. **Reasoning Mode:** ปุ่มสมอง Auto/On/Off ทำงานจริง (โมเดลที่รองรับ) — วัดผลต่างได้
2. **Assistant:** สร้าง/แก้ไข/ลบ/เลือก assistant ได้ — system prompt + params มีผลจริง
3. **Tool-calling:** IDE ต่อเข้า → ส่ง tools → ได้ tool_calls → ส่งผลกลับ → โมเดลตอบต่อ
4. **MCP:** เพิ่ม MCP server → โมเดลเรียก tool → execute (server หรือ client) → ผลกลับ
5. **Offline-first:** ตัดเน็ต (หรือ mock) → ทุกหน้า/ฟีเจอร์ local ยังทำงาน 100% ไม่ hang/error
6. **Honest telemetry:** ทุกค่าจริง ไม่ fake (ตาม ADR-003)
7. **Regression:** pytest เขียว + bundle < 150 kB + i18n PASS

---

## 🔗 อ้างอิง

- Jan docs: https://jan.ai/docs/desktop/model-parameters (Reasoning Mode)
- Jan docs: https://jan.ai/docs/desktop/mcp (MCP host)
- Jan docs: https://jan.ai/docs/desktop/api-server (Execute Tools on Server)
- Jan docs: https://jan.ai/docs/desktop/agents (agents แยกจาก app)
- โปรเจค: docs/ROADMAP.md (แผนหลัก) + docs/CONSOLE_ROADMAP.md (console)

---

*วางแผนโดย OpenCode Agent · 4 สิงหาคม 2026 · เริ่มหลัง P6 merge*
