```javascript
const res = await fetch("http://127.0.0.1:8765/v1/messages", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    model: "default",
    max_tokens: 256,
    messages: [{ role: "user", content: "Hello!" }],
  }),
});
console.log(await res.json());
```
