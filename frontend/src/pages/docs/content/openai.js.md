```javascript
// Streaming over fetch + SSE
const res = await fetch("http://127.0.0.1:8765/v1/chat/completions", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    model: "default",
    messages: [{ role: "user", content: "Explain mmap in one paragraph." }],
    stream: true,
    reasoning_effort: "medium", // accepted, NOT executed yet
  }),
});

const reader = res.body.getReader();
const dec = new TextDecoder();
let buf = "";
while (true) {
  const { done, value } = await reader.read();
  if (done) break;
  buf += dec.decode(value, { stream: true });
  let i;
  while ((i = buf.indexOf("\n")) !== -1) {
    const line = buf.slice(0, i).trim();
    buf = buf.slice(i + 1);
    if (!line.startsWith("data:")) continue;
    const payload = line.slice(5).trim();
    if (!payload || payload === "[DONE]") continue;
    const delta = JSON.parse(payload).choices?.[0]?.delta?.content ?? "";
    process.stdout.write(delta);
  }
}
```
