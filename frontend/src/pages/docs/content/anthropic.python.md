```python
import requests

r = requests.post(
    "http://127.0.0.1:8765/v1/messages",
    json={
        "model": "default",
        "max_tokens": 256,
        "messages": [{"role": "user", "content": "Hello!"}],
    },
    timeout=120,
)
print(r.json())
```
