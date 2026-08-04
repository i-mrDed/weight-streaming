"""Test tool-calling via LlamaServerBackend (P7.3)."""
import os
os.environ["WS_DATA_DIR"] = r"C:\Users\dedch\AppData\Local\Temp\wsdata-p72"
from weight_stream.backends.llama_server import LlamaServerBackend

backend = LlamaServerBackend(
    model_path=r"C:\Users\dedch\AppData\Roaming\Jan\data\llamacpp\models\Qwythos-9B-Claude-Mythos-5-1M-Q4_K_M\model.gguf",
    n_ctx=1024,
    port=8805,
)
backend.start()

# Define a simple tool
tools = [{
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "Get the current weather for a city",
        "parameters": {
            "type": "object",
            "properties": {
                "city": {"type": "string", "description": "City name"}
            },
            "required": ["city"]
        }
    }
}]

# Ask the model to call the tool
chunks = []
for chunk in backend.stream_chat(
    [{"role": "user", "content": "What's the weather in Bangkok? Use the get_weather tool."}],
    max_tokens=120,
    tools=tools,
    tool_choice="auto",
):
    chunks.append(chunk)
text = "".join(chunks)
print(f"content: [{text[:200]}]")
print(f"tool_calls: {backend.tool_calls}")
backend.close()