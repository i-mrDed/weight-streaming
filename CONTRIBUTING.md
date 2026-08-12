# Contributing Guide — Weight-Streaming + MongoModel

## 🚀 เริ่มต้น

```bash
git clone https://github.com/i-mrDed/weight-streaming
cd weight-streaming
pip install -e ".[server,test]"     # dev deps (ดู CI ci.yml)
```

### MongoModel (project hub — optional สำหรับแก้ data model)
```bash
docker compose -f docker-compose.mongomodel.yml up -d   # เปิด http://localhost:3100
# ข้อมูลโมเดลอยู่ที่ mongomodel-data/ (projects.json = data model + shared brain)
```

## 🧪 การทดสอบ

```bash
python -m pytest -q
# CI รัน Hermetic guard ด้วย (empty HOME) — ดู .github/workflows/ci.yml
```

## 📦 กติกา MongoModel (สำคัญ)

### 1. ห้าม commit ความลับเด็ดขาด
- **Shared Brain ใช้เก็บ "บริบทงาน" เท่านั้น** — ห้ามใส่ password, API key, token,
  connection string, secret ใดๆ ลงใน brain (projects.json ถูก commit = รั่วถาวรใน git history)
- Secret จริงของแอป ใช้ `.env` + `.gitignore` ตามปกติ
- CI มี gitleaks สแกนอัตโนมัติแล้ว — ห้าม disable

### 2. Single-writer rule
- `mongomodel-data/projects.json` — **คนเดียว commit ต่อครั้ง**
- แก้โมเดลข้อมูล → commit พร้อมโค้ดที่เกี่ยวข้อง (PR แสดงทั้ง design diff + code diff)
- อย่า merge 2 branch ที่แตะ projects.json พร้อมกัน

### 3. Regenerate เมื่อแก้ data model
- แก้ data model ใน MongoModel → regenerate โค้ด/เอกสารที่เกี่ยวข้องก่อน commit
- โค้ดที่ generate เป็น static — แก้ตรงๆ ได้ แต่ครั้งถัดไป regenerate จะทับ → แก้ที่ต้นทางเสมอ

### 4. บทบาทของเอกสาร (single source of truth — กัน duplication)
| ความจำ | เจ้าของ |
|---|---|
| Goal + Rule (กติกา) | Shared Brain (`goal`/`rule`) — PROJECT.md = executive summary |
| Task ค้าง | TASKS.md |
| บทเรียน/decision | Shared Brain (`decision`) + ลิงก์ research/YYYY-MM-DD-*.md |
| Session log | SESSION_LOG.md (`handoff` ใน brain = จุดที่ AI ตัวถัดไปเริ่ม) |

## 🔒 ความปลอดภัย

- ถ้าสงสัยว่า secret หลุดขึ้น repo → แจ้ง owner + rotate secret + purge git history (`git filter-repo`)
- ไม่มี auth บน MongoModel (bind 127.0.0.1) — ห้ามเปิด port ออก LAN

## 📝 Commit ตัวอย่าง

```bash
git add mongomodel-data/ src/ docs/
git commit -m "feat(model): เพิ่ม workflow serve-request + brain (design)"
```
