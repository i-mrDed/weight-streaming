import json, subprocess, threading, time, urllib.request

BASE = "http://127.0.0.1:8765"
PROMPT = "อธิบายสำนวน 'น้ำขึ้นให้รีบตัก' พร้อมตัวอย่างการใช้งาน"


def gen():
    req = urllib.request.Request(BASE + "/v1/chat/completions",
        data=json.dumps({"model": "qwen-cpulane",
                         "messages": [{"role": "user", "content": PROMPT}],
                         "max_tokens": 300, "stream": True,
                         "temperature": 0.0}).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    t0 = time.time()
    n = 0
    with urllib.request.urlopen(req, timeout=900) as r:
        for line in r:
            line = line.decode("utf-8", "replace").strip()
            if line.startswith("data: ") and line != "data: [DONE]":
                n += 1
    return n, time.time() - t0


def cpu_pct():
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "(Get-Counter '\\Processor(_Total)\\% Processor Time' -SampleInterval 1 -MaxSamples 1).CounterSamples[0].CookedValue"],
            capture_output=True, text=True, timeout=8).stdout.strip()
        return round(float(out), 1)
    except Exception:
        return None


def gpu_pct():
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=utilization.gpu,memory.used",
             "--format=csv,noheader"],
            capture_output=True, text=True, timeout=8).stdout.strip()
        return out
    except Exception:
        return None


def sample_loop(stop, samples):
    while not stop.is_set():
        samples.append((cpu_pct(), gpu_pct()))
        time.sleep(1.0)


def measure_once():
    stop = threading.Event()
    samples = []
    t = threading.Thread(target=sample_loop, args=(stop, samples), daemon=True)
    t.start()
    n, el = gen()
    stop.set()
    t.join(timeout=5)
    return n, el, samples


def main():
    gen()  # warmup
    time.sleep(1)
    for i in range(3):
        n, el, samples = measure_once()
        tps = n / el
        cpus = [s[0] for s in samples if s[0] is not None]
        gpus = [s[1] for s in samples if s[1]]
        cpu_avg = round(sum(cpus) / len(cpus), 1) if cpus else None
        print(f"rep{i+1}: {n} tok / {el:.2f}s = {tps:.1f} tps | "
              f"CPU% avg={cpu_avg} (n={len(cpus)}) | GPU samples={gpus}", flush=True)


if __name__ == "__main__":
    main()
