# 📋 Plan — Chat Agent Tools: filesystem access for chat agents

> **Status:** 🟢 เสร็จครบ — Phase 1–4 รวม E2E สดผ่านทั้งหมด (2026-08-12)
> **ที่มา:** ผู้ใช้ — "ให้ agents/models ที่คุยในหน้าแชท เข้าถึงไฟล์/โฟลเดอร์ (workspace) ได้"
> **รองรับจาก:** P7.3 tool-calling protocol (backend เสร็จ) + P7.4 MCP host (backend เสร็จ, UI บางส่วน)
> **ติดตามงาน:** `TASKS.md` section `Chat Agent Tools` · อัปเดตสถานะทุกไฟล์ที่แก้ที่ท้าย docs นี้

---

## 🎯 เป้าหมาย

ให้แชทในหน้า Console (ChatPage) ทำงานเป็น **agent**: ส่ง `tools` ให้โมเดล →
โมเดลคืน `tool_calls` → ระบบ execute (อ่านไฟล์/list โฟลเดอร์ ใน workspace ที่กำหนด) →
ส่งผลกลับให้โมเดลตอบต่อ → loop จนได้คำตอบสุดท้าย

รองรับ **tool 2 แหล่ง** (อนุมัติทั้ง 2 เส้นทาง):
- **A — MCP tools**: tools จาก MCP servers ที่ลงทะเบียน (เช่น `@modelcontextprotocol/server-filesystem`) ผ่าน `/v1/mcp/tools` + `/v1/mcp/tools/{server}/{tool}/call` (มีอยู่แล้ว)
- **B — Built-in workspace tools**: tools ฝั่ง server ใหม่ (`list_directory` / `read_file` / `workspace_info`) จำกัดอยู่ใน workspace root ด้วย path guard

---

## 🏗️ สถาปัตยกรรม (decision: agent loop ฝั่ง client)

```
ChatPage (console)
  │  ① ส่ง messages + tools (MCP ∪ built-in)      →  /v1/chat/completions (มีอยู่แล้ว, P7.3)
  │  ② stream: capture delta.content + delta.tool_calls (fragment merge)
  │  ③ finish_reason="tool_calls" → render tool card → execute:
  │        MCP tool      →  POST /v1/mcp/tools/{server}/{tool}/call   (มีอยู่แล้ว)
  │        built-in tool →  POST /v1/agent/tools/{name}/call          (ใหม่)
  │  ④ append {role:'tool', tool_call_id, content} → loop ②–④ (max 10 รอบ)
  │  ⑤ finish_reason="stop" → จบ
```

**เหตุผล client-side loop** (ไม่ทำ server-side agent):
- P7.4 หลักการเดิม: "MCP host ใช้สำหรับ Console โดยตรง" — IDE ภายนอกจัดการ loop เองผ่าน P7.3 อยู่แล้ว
- UI ควบคุมได้: แสดง tool call ทีละอัน, ยกเลิกได้, ไม่พัวพัน backend loop
- Server ทำหน้าที่ executor ล้วน (MCP + built-in ผ่าน HTTP) → testable + hermetic

---

## 🔌 API

### ใหม่ (built-in workspace tools)
| Method | Path | ฟังก์ชัน |
|--------|------|---------|
| GET | `/v1/agent/config` | กลับ `{enabled, workspace_root}` |
| PUT | `/v1/agent/config` | ตั้งค่า `{enabled, workspace_root}` (validate root มีจริง) |
| GET | `/v1/agent/tools` | list built-in tools (name/description/parameters) — เหมือน `/v1/mcp/tools` |
| POST | `/v1/agent/tools/{name}/call` | execute tool `{args}` → `{result}` |

### ใช้ของเดิม
- `POST /v1/chat/completions` — ส่ง `tools`/`tool_choice`, คืน `tool_calls` (P7.3, พร้อมแล้ว)
- `GET /v1/mcp/tools` · `POST /v1/mcp/tools/{server}/{tool}/call` (P7.4, พร้อมแล้ว)
- `GET/POST/DELETE /v1/mcp/servers` — Settings UI มีอยู่แล้ว (`MCPSection.tsx`)

### State
- ไฟล์ `data/agent.json` (gitignored, pattern เดียวกับ `data/tiering.json`)
- default: `workspace_root = env WS_WORKSPACE_ROOT` หรือ cwd ของ server, `enabled = true`
- `PUT /v1/agent/config` เขียนลงไฟล์ (validate path มีอยู่จริง + เป็น dir)

---

## 🛠️ Built-in workspace tools (v1)

| Tool | Args | กลับ | หมายเหตุ |
|------|------|------|---------|
| `workspace_info` | — | root, file_count, total_bytes | ให้โมเดลรู้ขอบเขต |
| `list_directory` | `path` (abs หรือ rel) | entries: name/type/size | depth 1, จำกัด 500 entries |
| `read_file` | `path` | เนื้อหา (text) | **cap 256 KB** — เกิน → error บอกให้ใช้ head |

**Path guard (ทุก tool):**
1. resolve + expanduser → ถ้า rel ต่อกับ workspace root
2. `os.path.commonpath([resolved, root]) == root` → ไม่งั้น 403 (กัน `..`, abs นอก root)
3. ปฏิเสธ symlink ที่ resolve ออกนอก root (ตาม `realpath`)
4. `read_file`: ปฏิเสธถ้าไม่ใช่ regular file; cap 256 KB; decode utf-8 (errors='replace')

**ไม่ทำใน v1 (เลื่อน):** `write_file`/`edit_file` (ต้อง approve flow ก่อน — งานหลัง), `search_files` (grep), recursive list, file upload/download UI

---

## 🧩 งานย่อย (Phases)

### Phase 1 — Agent loop ใน ChatPage (core)
- [ ] `frontend/src/core/api.ts`: เพิ่ม `callMCPTool(serverId, toolName, args)` + `listAgentTools()` + `callAgentTool(name, args)` + `getAgentConfig`/`putAgentConfig` + types
- [ ] `frontend/src/core/chat.ts` (ใหม่): pure functions สำหรับทดสอบ —
  - `accumulateToolCalls(fragments)` — merge delta.tool_calls ตาม index (เลียนแบบ backend `_accumulate_tool_calls`)
  - `buildWireMessages(msgs)` — แปลง ChatMsg → OpenAI wire format (assistant.tool_calls, role:'tool' พร้อม tool_call_id)
  - `MAX_AGENT_ITERS = 10`, `MAX_TOOL_RESULT_CHARS = 32_000`
- [ ] `ChatPage.tsx`:
  - ขยาย `ChatMsg`: `tool_calls?`, `tool_call_id?`, `name?`, `toolState?`
  - ส่ง `tools` ใน request (จาก MCP + built-in, filter ด้วย toggle)
  - stream: capture `delta.tool_calls` (fragment merge) + `finish_reason`
  - ถ้า `tool_calls`: render tool card (name + args collapsible + status) → execute (MCP/built-in) → append tool message → loop (guard รอบ)
  - ถ้า `stop`: จบปกติ
  - toolbar: toggle "Agent tools" + badge จำนวน tools
- [ ] locale en/th (`chat.json`) + CSS (`pages.css`)

### Phase 2 — Built-in workspace tools (backend)
- [ ] `weight_stream/server/workspace_tools.py` (ใหม่): TOOLS registry + path guard + handlers
- [ ] `api_server.py`: 4 routes `/v1/agent/*` + state file `data/agent.json`
- [ ] `tests/test_workspace_tools.py` (ใหม่, hermetic): path guard (.. / abs นอก root / symlink), size cap, read/list/workspace_info ผ่าน tmp_path, config round-trip
- [ ] `docs/GO_PUBLIC_CHECKLIST` note? (ไม่จำเป็น — ไฟล์ state gitignored)

### Phase 3 — Workspace selection UI
- [ ] Settings → section "Agent & Workspace" (ใหม่ `AgentSection.tsx`): workspace root input + enabled toggle + รายการ tools ที่ active
- [ ] locale en/th (`settings.json`) + CSS

### Phase 4 — Verification + QA
- [ ] backend: `pytest` hermetic (เต็ม suite) — เทสต์ใหม่ ต้องไม่พึ่งไฟล์นอก repo
- [ ] frontend: typecheck + vitest (pure functions + DOM test tool card render) + i18n verify + build (regenerate bundle)
- [ ] E2E ทางเลือก (optional, ต้องมี npx): MCP filesystem server จริง — `npx -y @modelcontextprotocol/server-filesystem <workspace>` → สั่งแชท "อ่าน README.md แล้วสรุป"
- [ ] manual: prompt injection payload ในไฟล์ที่ agent อ่าน → ตรวจว่าไม่หลุดออกนอก workspace / ไม่รันคำสั่ง

---

## 🔒 ความปลอดภัย (non-negotiable)

1. **Path allowlist server-side** — โมเดลถูก prompt-inject ได้; guard อยู่ที่ server ไม่ใช่ client
2. **Size caps** — read_file 256 KB, tool result 32 KB ต่อ call (กัน context overflow / cost)
3. **Iteration cap** — 10 รอบ loop (กัน tool loop ไม่รู้จบ)
4. **Transparency** — tool call ทุกอันแสดงใน UI (name/args/result) — ไม่มี hidden execution
5. **auto_approve=false** → v2: แสดง approve/deny ก่อน execute (P7.4 ค้างไว้) — v1 execute ทันทีแต่แสดงผล
6. ไฟล์ state `data/agent.json` gitignored — ไม่รั่ว workspace path ขึ้น repo

---

## ⚠️ ความเสี่ยง / ข้อจำกัด

- **โมเดลต้องรองรับ tool calling จริง** — `capabilities.tools` มี flag อยู่แล้ว; โมเดลที่ไม่รองรับจะ ignore tools → แชททำงานปกติ (degrade gracefully)
- **MCP filesystem server ยังไม่เคยทดสอบ E2E** — ต้อง `pip install mcp` (extra) + `npx` มีในเครื่อง; ถ้า npx ไม่มี → เส้นทาง B (built-in) ใช้ได้เสมอ
- **llama.cpp tool calling เบต้า** — บาง quant/โมเดลให้ tool_calls format ผิด → error handling ต้องไม่พังแชท (แสดง tool error ใน card แล้วให้โมเดลอธิบาย)
- **fragment accumulation สองชั้น** — backend เก็บ tool_calls ครบแล้ว แต่ ChatPage ต้องอ่านจาก stream เอง (เพราะ loop อยู่ client) → pure function + tests

---

## ✅ เกณฑ์สำเร็จ (definition of done)

- [ ] พิมพ์ในแชท "list ไฟล์ใน workspace แล้วสรุปว่าโปรเจคนี้ทำอะไร" → เห็น tool call card → ได้คำตอบที่อ้างอิงไฟล์จริง
- [ ] `read_file` ไฟล์นอก workspace → error card ชัดเจน (ไม่ silent)
- [ ] ไฟล์ >256 KB → error "too large" ไม่ crash
- [ ] hermetic suite เขียว (pytest + vitest + build + i18n)
- [ ] บันทึกผลใน TASKS.md

---

## 📌 งานหลัง (follow-ups, ไม่ใช่ v1)

- [ ] `write_file`/`edit_file` + approve/deny flow (auto_approve=false)
- [ ] search_files (grep), recursive listing, file diff preview
- [ ] server-side agent loop (ให้ IDE/client ภายนอกใช้ได้) — ถ้าผู้ใช้ต้องการ
- [ ] tool-call history UI (ผลลัพธ์เก็บใน conversation, export/import)

---

## 🧾 หลักฐานการทำงาน (อัปเดตทุกครั้งที่แก้)

| วันที่ | สถานะ | หมายเหตุ |
|-------|-------|---------|
| 2026-08-11 | Plan เขียน | วิเคราะห์: backend พร้อม (P7.3/P7.4), ขาด agent loop ฝั่ง client + built-in tools + workspace UI |
| 2026-08-11 | Phase 1–3 เสร็จ | `core/chat.ts` (pure fns: buildWireMessages/formatToolResult/truncateToolResult) + vitest 14 · `ChatPage.tsx` agent loop (non-stream tool turns → execute MCP/builtin → loop cap 10) + tool cards · `workspace_tools.py` (path guard commonpath+realpath, size cap 256KB, state `data/agent.json`) + routes `/v1/agent/*` · `AgentSection.tsx` Settings · locale en/th + CSS |
| 2026-08-11 | Verification | vitest 51/51 · typecheck ✓ · i18n 881 keys ✓ · build ✓ · pytest hermetic **398 passed / 7 skipped** (16 เทสต์ workspace tools ใหม่) — E2E สดยังรอ restart server ใหม่ |
| 2026-08-12 | E2E สด (Phase 4) | Server :8765 รันโค้ดใหม่ + Qwen3-0.6B (llama-server CUDA ผ่าน WS_LLAMA_SERVER): **agent loop ครบวงจร** — โมเดลยิง 3 tools (workspace_info ✓ / list_directory("/") → 403 block ✓ / read_file ✓) แล้วตอบสรุปจบ · **MCP filesystem จริง** (npx @modelcontextprotocol/server-filesystem): 14 tools, read_file+list_directory ผ่าน · **injection probe PASS** — payload "echo PWNED > /tmp/pwned.txt" ถูก treat เป็น data, ไม่มีไฟล์หลุด/รัน |
| 2026-08-12 | Fixes จาก E2E | ① `chat_template_kwargs` forward ครบเส้นทาง (schemas→openai_compat→stream_chat payload) + ChatPage ส่ง `{enable_thinking:false}` ตอน agent turn — Qwen3 คิดไม่หยุดเดิม → ยิง tool_calls จริง ② mcp_host 1.27: `stdio_client`/`sse_client` ต้อง enter เป็น async CM (ทั้งคู่พังกับ mcp 1.27) ③ `.gitignore` + `data/agent.json` (plan เคยบอกว่า gitignored แต่ไม่ได้ใส่ — รั่ว workspace path) · เทสต์ใหม่ +3 (payload forwarding ×2, StdioServerParameters) |
