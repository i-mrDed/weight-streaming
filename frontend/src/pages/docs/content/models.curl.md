```bash
# Scan a folder for GGUF files (recursive; can be slow on big stores)
curl "http://127.0.0.1:8765/v1/models/scan?dir=./models"

# Load a model by id
curl -X POST http://127.0.0.1:8765/v1/models/load \
  -H "Content-Type: application/json" \
  -d '{"model_id": "default", "model_path": "./models/qwen.gguf", "buffer_mb": 64, "n_ctx": 2048}'

# List / unload
curl http://127.0.0.1:8765/v1/models
curl -X POST http://127.0.0.1:8765/v1/models/unload \
  -H "Content-Type: application/json" -d '{"model_id": "default"}'
```
