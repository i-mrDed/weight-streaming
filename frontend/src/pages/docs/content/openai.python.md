```python
# Streaming with the OpenAI SDK
from openai import OpenAI

client = OpenAI(base_url="http://127.0.0.1:8765/v1", api_key="not-used")

stream = client.chat.completions.create(
    model="default",
    messages=[{"role": "user", "content": "Explain mmap in one paragraph."}],
    temperature=0.7,
    top_p=1.0,
    max_tokens=256,
    reasoning_effort="medium",  # accepted, NOT executed yet
    stream=True,
)
for chunk in stream:
    delta = chunk.choices[0].delta.content or ""
    print(delta, end="", flush=True)
```
