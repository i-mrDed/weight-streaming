"""Integration test for the API server."""
import sys, time, json, os
sys.path.insert(0, '.')
sys.stdout.reconfigure(encoding='utf-8')

import requests
import threading

MODEL = "research/models/Qwen1.5-MoE-A2.7B_Q2_k.gguf"
SERVER_URL = "http://127.0.0.1:8383"

def test_health():
    r = requests.get(f"{SERVER_URL}/health", timeout=5)
    assert r.status_code == 200
    print(f"  PASS Health: {r.json()}")
    return True

def test_load_model():
    r = requests.post(f"{SERVER_URL}/v1/models/load", json={
        "model_id": "test", "model_path": MODEL,
        "buffer_mb": 64, "n_ctx": 64,
    }, timeout=90)
    assert r.status_code == 200, f"Load failed: {r.status_code} {r.text}"
    assert r.json()["status"] == "loaded"
    print(f"  PASS Load model")
    return True

def test_list_models():
    r = requests.get(f"{SERVER_URL}/v1/models", timeout=10)
    assert r.status_code == 200
    models = r.json()
    assert len(models) >= 1
    print(f"  PASS List: {len(models)} model(s)")
    return True

def test_generate():
    r = requests.post(f"{SERVER_URL}/v1/generate", json={
        "model": "test", "prompt": "The capital of France is",
        "max_tokens": 10, "temperature": 0.7, "stream": False,
    }, timeout=120)
    if r.status_code != 200:
        print(f"  FAIL Generate: {r.status_code} {r.text[:200]}")
        return False
    data = r.json()
    assert len(data["output"]) > 0
    print(f"  PASS Generate: {data['tokens_per_second']:.1f} tok/s, {data['tokens_generated']} tokens")
    return True

def test_generate_stream():
    r = requests.post(f"{SERVER_URL}/v1/generate", json={
        "model": "test", "prompt": "Hello",
        "max_tokens": 5, "temperature": 0.7, "stream": True,
    }, timeout=60, stream=True)
    assert r.status_code == 200
    events = []
    for line in r.iter_lines():
        if line and line.startswith(b"data: "):
            events.append(json.loads(line[6:]))
    assert len(events) > 0
    assert events[-1]["done"] == True
    print(f"  PASS Stream: {len(events)} events")
    return True

def test_stats():
    r = requests.get(f"{SERVER_URL}/v1/stats", timeout=10)
    assert r.status_code == 200
    data = r.json()
    assert "models" in data
    print(f"  PASS Stats: {data['server']['models_loaded']} models loaded")
    return True

def test_unload():
    r = requests.post(f"{SERVER_URL}/v1/models/unload", json={
        "model_id": "test",
    }, timeout=10)
    assert r.status_code == 200
    assert r.json()["status"] == "unloaded"
    print(f"  PASS Unload")
    return True

if __name__ == "__main__":
    import uvicorn
    from weight_stream.server.api_server import create_app
    from weight_stream.server.config import ServerConfig
    
    config = ServerConfig(host="127.0.0.1", port=8383)
    app, mgr = create_app(config)
    
    def run_server():
        uvicorn.run(app, host=config.host, port=config.port, log_level="warning")
    
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    time.sleep(3)
    
    print("Testing API Server...\n")
    
    all_pass = True
    for name, fn in [
        ("Health", test_health),
        ("Load model", test_load_model),
        ("List models", test_list_models),
        ("Generate", test_generate),
        ("Stream", test_generate_stream),
        ("Stats", test_stats),
        ("Unload", test_unload),
    ]:
        try:
            if not fn():
                all_pass = False
        except Exception as e:
            print(f"  FAIL {name}: {e}")
            all_pass = False
    
    print(f"\n==> {'ALL PASS' if all_pass else 'SOME FAILED'}")
    sys.exit(0 if all_pass else 1)
