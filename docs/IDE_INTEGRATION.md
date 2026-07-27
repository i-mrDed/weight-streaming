# เชื่อมต่อ Weight Streaming กับ IDE & Tools

> **前提:** API Server กำลังรันอยู่ที่ `http://localhost:8765`

---

## 1. VS Code + Continue.dev

ไฟล์ `~/.continue/config.json`:

```json
{
  "models": [
    {
      "title": "WeightStream Local",
      "provider": "openai",
      "model": "default",
      "apiBase": "http://localhost:8765/v1",
      "apiKey": "not-needed"
    }
  ],
  "tabAutocompleteModel": {
    "title": "WeightStream Local",
    "provider": "openai",
    "model": "default",
    "apiBase": "http://localhost:8765/v1"
  }
}
```

หรือตั้งค่าผ่าน UI: VS Code → Continue tab → settings gear → Models → Add Model → OpenAI → ใส่ `http://localhost:8765/v1` ใน API Base

---

## 2. Cursor IDE

Settings → Models → Add Model → ใส่:

```
Model Name: weightstream-local
API Base URL: http://localhost:8765/v1
API Key: not-needed
```

หรือ `/cursor-settings` → OpenAI API Key: `not-needed` → Override Base URL: `http://localhost:8765/v1`

---

## 3. Cline (VS Code Extension)

เปิด Cline settings → API Provider: **OpenAI Compatible** → 

```
Base URL: http://localhost:8765/v1
API Key:  not-needed
Model ID: default
```

---

## 4. Terminal AI Tools

### Aider
```bash
export OPENAI_API_BASE=http://localhost:8765/v1
export OPENAI_API_KEY=not-needed
aider --model openai/default
```

### Claude Code CLI (via OpenAI compat)
```bash
export OPENAI_BASE_URL=http://localhost:8765/v1
export OPENAI_API_KEY=not-needed
```

### Fabric
```bash
export OPENAI_BASE_URL=http://localhost:8765/v1
export OPENAI_API_KEY=not-needed
fabric --model default --pattern summarize
```

---

## 5. LangChain / LlamaIndex (Python)

```python
# LangChain
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(
    model="default",
    openai_api_base="http://localhost:8765/v1",
    openai_api_key="not-needed",
)
response = llm.invoke("What is the capital of France?")
print(response.content)
```

```python
# LlamaIndex
from llama_index.llms.openai import OpenAI

llm = OpenAI(
    model="default",
    api_base="http://localhost:8765/v1",
    api_key="not-needed",
)
```

---

## 6. OpenAI Python SDK

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8765/v1",
    api_key="not-needed",
)

# Chat
response = client.chat.completions.create(
    model="default",
    messages=[{"role": "user", "content": "Tell me a joke"}],
)
print(response.choices[0].message.content)

# Streaming
stream = client.chat.completions.create(
    model="default",
    messages=[{"role": "user", "content": "Write a haiku"}],
    stream=True,
)
for chunk in stream:
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="", flush=True)
```

---

## 7. curl (REST API ตรง)

```bash
# Generate
curl -X POST http://localhost:8765/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "default",
    "messages": [{"role": "user", "content": "What is 2+2?"}],
    "max_tokens": 50,
    "temperature": 0.7
  }'

# Streaming
curl -X POST http://localhost:8765/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "default",
    "messages": [{"role": "user", "content": "Hello"}],
    "stream": true
  }'
```

---

## 8. Node.js / TypeScript

```typescript
import OpenAI from "openai";

const client = new OpenAI({
  baseURL: "http://localhost:8765/v1",
  apiKey: "not-needed",
});

const response = await client.chat.completions.create({
  model: "default",
  messages: [{ role: "user", content: "Hello from TypeScript!" }],
});
console.log(response.choices[0].message.content);
```

---

## 9. HTTP Request (any language)

ทุก endpoint ใช้ standard HTTP POST/GET:

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/v1/chat/completions` | POST | Chat (OpenAI compatible) |
| `/v1/generate` | POST | Raw text generation |
| `/v1/generate?stream=true` | POST | SSE streaming |
| `/v1/stats` | GET | Performance stats |
| `/v1/models` | GET | List loaded models |
| `/v1/models/load` | POST | Load model |
| `/v1/models/unload` | POST | Unload model |

---

## Environment Variables (cross-tool)

ตั้งค่า env ครั้งเดียวใช้ได้ทุก tool:

| Windows (PowerShell) | Linux/macOS |
|---------------------|-------------|
| `$env:OPENAI_BASE_URL="http://localhost:8765/v1"` | `export OPENAI_BASE_URL=http://localhost:8765/v1` |
| `$env:OPENAI_API_KEY="not-needed"` | `export OPENAI_API_KEY=not-needed` |

แล้วใช้ได้กับ Cursor, Cline, Continue.dev, OpenAI SDK, LangChain และทุกอย่างที่รองรับ OpenAI API format
