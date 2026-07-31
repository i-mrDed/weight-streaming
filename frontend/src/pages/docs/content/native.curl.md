```bash
# Non-streaming
curl http://127.0.0.1:8765/v1/generate \
  -H "Content-Type: application/json" \
  -d '{"model": "default", "prompt": "The capital of France is", "max_tokens": 8}'

# Streaming (SSE tokens; errors arrive in-stream)
curl -N http://127.0.0.1:8765/v1/generate \
  -H "Content-Type: application/json" \
  -d '{"model": "default", "prompt": "Count to 5:", "max_tokens": 16, "stream": true}'
```
