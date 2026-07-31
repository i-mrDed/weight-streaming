```bash
curl http://127.0.0.1:8765/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "default",
    "messages": [{"role": "user", "content": "Explain mmap in one paragraph."}],
    "temperature": 0.7,
    "top_p": 1.0,
    "max_tokens": 256,
    "reasoning_effort": "medium",
    "stream": true
  }'
```
