```python
# Continue (config.yaml) / any OpenAI-compatible IDE plugin
# models:
#   - title: "Local weight-streaming"
#     provider: "openai"
#     model: "default"                 # a loaded model id
#     apiBase: "http://127.0.0.1:8765/v1"
#     apiKey: "local"                  # not checked

import requests
print(requests.get("http://127.0.0.1:8765/v1/models", timeout=5).json())
```
