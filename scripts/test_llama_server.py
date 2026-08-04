"""Test LlamaServerBackend with reasoning_format=none (content includes thinking)."""
import time
from weight_stream.backends.llama_server import LlamaServerBackend

backend = LlamaServerBackend(
    model_path=r"C:\Users\dedch\AppData\Roaming\Jan\data\llamacpp\models\Qwythos-9B-Claude-Mythos-5-1M-Q4_K_M\model.gguf",
    n_ctx=1024,
    port=8805,
)
backend.start()

start = time.time()
chunks = []
for chunk in backend.stream_chat(
    [{"role": "user", "content": "What is the capital of France? Answer in one word."}],
    max_tokens=80,
    reasoning_mode="auto",
):
    chunks.append(chunk)
elapsed = time.time() - start
text = "".join(chunks)
gen = backend.get_stats().get("generation", {})
print(f"elapsed: {elapsed:.2f}s | tok/s: {gen.get('tokens_per_sec', 0):.1f}")
print(f"tokens: {gen.get('token_count', 0)}")
print(f"reply: [{text[:200]}]")
backend.close()