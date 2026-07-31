```bash
curl http://127.0.0.1:8765/v1/messages \
  -H "Content-Type: application/json" \
  -d '{
    "model": "default",
    "max_tokens": 256,
    "messages": [{"role": "user", "content": "Hello!"}]
  }'
```
