```python
import requests

with requests.post(
    "http://127.0.0.1:8765/v1/generate",
    json={"model": "default", "prompt": "Count to 5:", "max_tokens": 16, "stream": True},
    stream=True,
    timeout=120,
) as r:
    for line in r.iter_lines(decode_unicode=True):
        if line:
            print(line)  # SSE token / in-stream error
```
