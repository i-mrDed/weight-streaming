# Installing on a New Machine

> เป้าหมาย: จาก `git clone` ถึงรัน server ได้ **โดยไม่ต้องติดตั้ง Jan** และไม่ต้อง
> ไล่หาของทีละชิ้น — ใช้สคริปต์ setup ในตัวจัดการให้อัตโนมัติ

## 1. สิ่งที่ต้องมี (prerequisites)

| รายการ | เวอร์ชัน | วิธีตรวจ |
|---|---|---|
| Python | >= 3.11 | `python --version` |
| git | ใดๆ | `git --version` |
| (ทางเลือก) GPU driver | CUDA (NVIDIA) / Vulkan | `nvidia-smi` / `vulkaninfo` |

## 2. Clone + ติดตั้ง dependencies

```bash
git clone https://github.com/i-mrDed/weight-streaming.git
cd weight-streaming

# Python package (server extras + test)
pip install -e ".[server,test]"
```

## 3. เตรียม inference engine (llama-server / llama.cpp)

ระบบค้นหา binary ตามลำดับ (โค้ดจริง: `weight_stream/backends/llama_server.py`):

```
1. $WS_LLAMA_SERVER          ← ตั้งเอง (แนะนำ)
2. %APPDATA%/Jan/...          ← ถ้ามี Jan อยู่แล้ว (ใช้ของมันได้)
3. PATH (shutil.which)        ← มีใน PATH ก็พอ
```

**วิธีที่เร็วที่สุด — ใช้สคริปต์ในตัว:**

```bash
# ตรวจว่ามี binary อยู่แล้วไหม (ไม่เขียนอะไร)
python scripts/setup_llama_server.py --check

# ไม่มี → ดาวน์โหลด release ล่าสุดจาก llama.cpp ที่ตรงกับ GPU + เขียน .env
python scripts/setup_llama_server.py --write-env

# ระบุ backend เอง (ข้าม auto-detect) ได้:
python scripts/setup_llama_server.py --write-env --backend cuda   # NVIDIA
python scripts/setup_llama_server.py --write-env --backend vulkan # AMD/Intel
python scripts/setup_llama_server.py --write-env --backend metal  # macOS
```

สคริปต์จะ:
1. หา binary ที่มีอยู่ (env → Jan → PATH) — เจอแล้วจบ
2. ไม่เจอ → ดาวน์โหลด `llama-<tag>-bin-<os>-<backend>-<arch>.zip` จาก
   GitHub releases ของ llama.cpp (เลือก CUDA toolkit เวอร์ชันใหม่สุดให้อัตโนมัติ)
3. แตกไฟล์ลง `.llama/` → เขียน `WS_LLAMA_SERVER=` ลง `.env`

### ทำ manual (ถ้าไม่อยากใช้สคริปต์)

1. โหลด release จาก https://github.com/ggml-org/llama.cpp/releases
   (เลือกไฟล์ `llama-*-bin-win-cuda-13.x-x64.zip` หรือเทียบเท่า platform คุณ)
2. แตกไฟล์ จำ path ของ `llama-server` (หรือ `llama-server.exe`)
3. ตั้งค่า:
   ```bash
   # Windows PowerShell
   $env:WS_LLAMA_SERVER = "C:\path\to\llama-server.exe"
   # หรือเขียน .env
   WS_LLAMA_SERVER=C:\path\to\llama-server.exe
   ```

## 4. รัน

```bash
weight-streaming server        # API server + console → http://localhost:8765/console/
```

หรือ front door อื่น:
```bash
weight-streaming run model.gguf -p "Hello"
weight-streaming benchmark model.gguf --max-tokens 256
weight-streaming tui --server http://127.0.0.1:8765
```

## 5. ตรวจว่าใช้ engine ถูกตัว

```bash
# server log ควรเห็น "Starting llama-server: port=8805 model=..." 
# ชี้ไปที่ binary ที่ตั้งไว้
```

## Troubleshooting

| อาการ | สาเหตุ/วิธีแก้ |
|---|---|
| `ModelError: No llama-server found` | ยังไม่มี binary — รัน `python scripts/setup_llama_server.py --write-env` |
| ช้ามาก (2–4 tok/s) | ใช้ CPU build — ต้อง build ที่ตรง GPU (cuda/vulkan/metal) |
| โหลดโมเดลใหม่ (qwen35 ฯลฯ) ไม่ได้ | llama.cpp เวอร์ชันเก่า — อัปเดต release (`--download` หรือ `--backend cuda`) |
| เปิด `--port` ชนกัน | ตั้ง `WS_PORT` / `WS_LLAMA_BACKEND_PORT` ต่าง |

> ⚠️ ไฟล์ `.llama/` (binary ที่ดาวน์โหลด) ถูก git-ignore — ไม่ต้องกังวลเรื่อง commit
> ⚠️ `WS_LLAMA_SERVER` ใช้กับ Linux/macOS ได้เหมือนกัน (ไม่มี `.exe` suffix)