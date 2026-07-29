# Report-ISSUE-002: Chat UX Redesign — Detailed Plan

> **Issue:** Report-ISSUE-002 (critical)  
> **Status:** in_progress  
> **Date:** 2026-07-27  
> **Approval:** approved — implementation in progress

---

## 1. Problems Identified (from ISSUE-002)

| # | Problem | Impact |
|---|---------|--------|
| 1 | ไม่รู้ว่ากำลังแชทกับโมเดลไหน | สับสนเมื่อโหลดหลายโมเดล |
| 2 | เลือกการตั้งค่าโมเดลไม่ได้ (temperature, max_tokens, tools, effort) | ไม่สามารถปรับแต่งได้ |
| 3 | แชทยาวแล้วหลุดหน้าจอ / เลื่อนลงไม่หยุด | UX แย่ ใช้งานจริงไม่ได้ |
| 4 | โมเดลตอบภาษาไทยไม่ได้ | ข้อจำกัดของโมเดล Q2_K (แต่ควรปรับ system prompt ให้ดีขึ้น) |
| 5 | ไม่มีการจัดการหลายโมเดลในหน้าแชท | สลับโมเดลไม่ได้โดยตรง |

---

## 2. Design Goals

```
เป้าหมาย: หน้า Chat ที่ใช้งานได้จริงเหมือน ChatGPT / Claude / Jan Desktop
```

1. **รู้ชัดว่าแชทกับโมเดลไหน** — แสดงชื่อโมเดล + architecture + quantization ตลอดเวลา
2. **สลับโมเดลได้โดยตรง** — dropdown ในหน้าแชทเลย ไม่ต้องไปที่ Models tab
3. **ปรับการตั้งค่าได้** — temperature, max_tokens, system prompt, top_p
4. **แชทยาวไม่หลุด** — scroll ที่ควบคุมได้, auto-scroll เฉพาะตอนอยู่ล่างสุด
5. **ประวัติแยกตามโมเดล** — แต่ละโมเดลมี conversation ของตัวเอง
6. **รองรับภาษาไทย** — system prompt ที่ดีขึ้น + UI ภาษาไทยได้

---

## 3. New Chat Layout

```
┌──────────────────────────────────────────────────────────────────┐
│  Header (existing)                                               │
├──────────────────────────────────────────────────────────────────┤
│  Chat Tab                                                        │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │  Chat Toolbar (NEW)                                        │ │
│  │  ┌──────────────────┐  ┌──────────┐  ┌──────────────────┐ │ │
│  │  │ Model: Qwen3.6 ▼│  │ ⚙ Settings│  │ 🗑 Clear Chat    │ │ │
│  │  └──────────────────┘  └──────────┘  └──────────────────┘ │ │
│  └────────────────────────────────────────────────────────────┘ │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │  Chat Messages (scrollable, controlled)                   │ │
│  │                                                            │ │
│  │  ┌─ User ─────────────────────────────────┐               │ │
│  │  │ สวัสดีครับ                               │               │ │
│  │  └─────────────────────────────────────────┘               │ │
│  │  ┌─ Assistant ─────────────────────────────┐               │ │
│  │  │ สวัสดีครับ ยินดีต้อนรับ!                  │               │ │
│  │  └─────────────────────────────────────────┘               │ │
│  │                                                            │ │
│  └────────────────────────────────────────────────────────────┘ │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │  Input Bar                                                 │ │
│  │  ┌──────────────────────────────────────────────┐ [Send]  │ │
│  │  │ Type a message...                              │         │ │
│  │  └──────────────────────────────────────────────┘          │ │
│  │  256 tokens · temp 0.3 · Qwen3.6-35B-A3B                  │ │
│  └────────────────────────────────────────────────────────────┘ │
├──────────────────────────────────────────────────────────────────┤
│  Footer (existing)                                               │
└──────────────────────────────────────────────────────────────────┘
```

### Settings Panel (popup/accordion)

```
┌─ ⚙ Settings ──────────────────────────┐
│                                        │
│  System Prompt                         │
│  ┌──────────────────────────────────┐  │
│  │ You are a helpful assistant...   │  │
│  └──────────────────────────────────┘  │
│                                        │
│  Temperature    [────●──] 0.3          │
│  Max Tokens     [────●──] 256          │
│  Top P          [───────●] 0.9         │
│                                        │
│  [Save]  [Reset to defaults]           │
└────────────────────────────────────────┘
```

---

## 4. Component Breakdown

### 4.1 Chat Toolbar (NEW)

| Element | Type | Behavior |
|---------|------|----------|
| Model selector | Dropdown | Lists all loaded models from `GET /v1/models`. Switching changes `currentModel` and loads that model's conversation history. |
| Settings button | Button → popup | Opens settings panel (temperature, max_tokens, system_prompt, top_p) |
| Clear Chat | Button | Clears current model's conversation history (with confirm) |

### 4.2 Model Selector

```javascript
// Fetch loaded models
const models = await apiJSON('/v1/models');
// Dropdown: model.id + model.arch + model.n_experts
// On change: switchModel(modelId)
```

When switching models:
- Save current conversation to `localStorage['ws-chat-{oldModelId}']`
- Load conversation from `localStorage['ws-chat-{newModelId}']`
- Update toolbar display
- Update input bar footer text

### 4.3 Settings Panel

Settings stored per-model in localStorage:
```json
{
  "ws-settings-default": {
    "system_prompt": "You are a helpful assistant...",
    "temperature": 0.3,
    "max_tokens": 256,
    "top_p": 0.9
  }
}
```

### 4.4 Chat Messages — Scroll Fix

**Root cause of scroll problem:**
- Current: `chatMessages.scrollTop = chatMessages.scrollHeight` on every token
- Problem: forces scroll even when user scrolled up to read
- Fix: Only auto-scroll if user is already near bottom

```javascript
function isNearBottom() {
  const el = chatMessages;
  return el.scrollHeight - el.scrollTop - el.clientHeight < 100;
}

// In streaming:
if (isNearBottom()) {
  chatMessages.scrollTop = chatMessages.scrollHeight;
}
```

Also:
- Add scroll container with `overflow-y: auto; flex: 1; min-height: 0;`
- Messages container should NOT grow infinitely — use `flex-shrink: 0` on messages

### 4.5 Conversation History Per Model

```javascript
function getModelKey(modelId) {
  return 'ws-chat-' + modelId;
}

function saveChatForModel(modelId) {
  localStorage.setItem(getModelKey(modelId), JSON.stringify(conversationHistory));
}

function loadChatForModel(modelId) {
  try {
    return JSON.parse(localStorage.getItem(getModelKey(modelId)) || '[]');
  } catch { return []; }
}
```

### 4.6 Thai Language Support

- System prompt default: ตอบภาษาเดียวกับที่ user ใช้ (มีแล้ว)
- UI labels: ใช้ภาษาอังกฤษ (universal) แต่รองรับ input/output ภาษาไทย
- Font: ตรวจสอบว่า font รองรับ Thai (Segoe UI รองรับ)
- ถ้าโมเดลไม่รองรับไทย → แสดง hint ใน settings: "This model may not support Thai well (Q2_K quantization)"

---

## 5. Implementation Steps

| Step | What | Files | Effort |
|------|------|-------|--------|
| 1 | Chat toolbar HTML + CSS | `static/index.html` | 30 min |
| 2 | Model selector dropdown + switch logic | `static/index.html` JS | 30 min |
| 3 | Settings popup (temp, tokens, system prompt) | `static/index.html` | 45 min |
| 4 | Scroll fix (isNearBottom + controlled scroll) | `static/index.html` JS | 15 min |
| 5 | Per-model conversation history (localStorage) | `static/index.html` JS | 30 min |
| 6 | Input bar footer (model info + settings summary) | `static/index.html` | 15 min |
| 7 | Clear chat with confirm | `static/index.html` | 10 min |
| 8 | Test all flows + commit | — | 30 min |

**Total: ~3.5 hours**

---

## 6. What NOT to Change (scope control)

- Models tab (scan/browse/load) — ไม่แตะ
- Stats tab — ไม่แตะ
- Issues tab — ไม่แตะ
- API server endpoints — ไม่แตะ
- Backend (WeightStreamModel) — ไม่แตะ
- Chat completion logic (Q&A format) — ใช้ที่มี ไม่เปลี่ยน

---

## 7. Success Criteria

```
☐ เห็นชื่อโมเดลในหน้าแชทตลอดเวลา
☐ สลับโมเดลได้จาก dropdown ในหน้าแชท
☐ แต่ละโมเดลมีประวัติแชทแยกกัน
☐ ปรับ temperature / max_tokens / system prompt ได้
☐ แชทยาวแล้วไม่หลุดหน้าจอ (scroll ควบคุมได้)
☐ ปุ่ม Clear Chat ล้างประวัติได้
☐ รีโหลดแล้วประวัติแชทแต่ละโมเดลยังอยู่
```

---

## 8. Open Decisions

| # | Decision | Recommendation |
|---|----------|----------------|
| 1 | Settings popup หรือ sidebar? | Popup (เล็ก ไม่กินพื้นที่แชท) |
| 2 | Model selector ใน toolbar หรือ sidebar? | Toolbar (เข้าถึงง่าย) |
| 3 | แยกประวัติตาม model_id หรือเดียวกัน? | แยก (แต่ละโมเดลเป็นคนละบทสนทนา) |
| 4 | Settings เก็บ per-model หรือ global? | Per-model (แต่ละโมเดลอาจต้องการ temp ต่างกัน) |
| 5 | แสดง token count ตามเวลาเลยไหม? | แสดงหลัง generate เสร็จ (ไม่รบกวนระหว่าง stream) |

---

**Next step:** รอคุณ approve แผนนี้ แล้วเริ่ม implement ตาม 8 steps