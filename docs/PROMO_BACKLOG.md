# Promo Backlog (พักไว้ก่อน — กลับมาทำต่อทีหลัง)

> สถานะ ณ 2026-08-10: งานโปรโมทส่วนที่เหลือถูกพักไว้เพื่อลุยระบบต่อ
> รายการนี้คือ "ของที่เสนอไว้" ทั้งหมดที่ยังไม่ได้ทำ — กลับมาเมื่อไหร่ ไล่ตามนี้ได้เลย
> ขั้นตอนสลับ public ดูที่ [GO_PUBLIC_CHECKLIST](GO_PUBLIC_CHECKLIST.md)

## ✅ ทำเสร็จแล้ว (ไม่ต้องกลับมาทำ)

| งาน | หลักฐาน |
|---|---|
| README: banner/hero + screenshots 6 หน้า + demo GIF/video | `docs/screenshots/`, README |
| Hero โลโก้ใหญ่ + คำโปรย (ภาพแรก README) | `docs/screenshots/hero.png` + `scripts/hero_splash.html` |
| SEO: description + 15 topics + badges (CI/Release/MIT/Python matrix) | repo settings, README |
| LICENSE (MIT) | `LICENSE` |
| Release v0.15.0 (published + wheel) | https://github.com/i-mrDed/weight-streaming/releases/tag/v0.15.0 |
| Landing page สำหรับ Pages | `docs/index.md` (รอเปิด Pages ตอน public) |
| Write-up EXP-012 (EN+TH) + draft r/LocalLLaMA | `research/writeups/` |
| Go-public checklist | `docs/GO_PUBLIC_CHECKLIST.md` |
| CI Python matrix 3.11/3.12/3.13 | `.github/workflows/ci.yml` |

## 🔜 งานโปรโมทที่ค้าง (กลับมาทำเมื่อพร้อม)

| # | งาน | สถานะ | ต้องทำอะไร |
|---|---|---|---|
| P1 | **สลับ repo เป็น public** ตาม checklist | ⏸ รอการตัดสินใจ Track A/B | `gh repo edit --visibility public` + เปิด Pages + อัปโหลด social preview (`hero.png`) + ตรวจ CI/README/release |
| P2 | **โพสต์ r/LocalLLaMA** | draft พร้อม | โพสต์ `research/writeups/2026-08-10-reddit-r-localLLaMA.md` + แนบ hero.png/stats/demo-gif — **ต้องสลับ public ก่อน** |
| P3 | **โพสต์บทความ EN + TH** (blog/HF community) | draft พร้อม | `research/writeups/2026-08-10-exp012-104gb-on-64gb-ram.md` |
| P4 | **PyPI publish** | wheel พร้อม | `python -m build && twine upload dist/*` — ต้องใช้ credentials ของคุณ |
| P5 | **B6: เผยแพร่ benchmark harness** ให้ community วัดบน HW อื่น | ยังไม่ทำ | จัดระเบียบ `scripts/measure_*.py` → เอกสารวิธีใช้ + รับ input HW spec |
| P6 | **ตรวจ hero/boot-splash ด้วยตา** (preview) ก่อน public | ยังไม่ทำ | เปิด preview แล้วเล่ารายละเอียดภาพ |
| P7 | **Hero ฉบับภาษาไทย** + ตัดสินใจใช้ TH/EN | ยังไม่ทำ | แก้ `scripts/hero_splash.html` → capture ใหม่ |
| P8 | **GitHub Pages เปิด** (landing `docs/index.md`) | รอ public | Settings → Pages (2 คลิก) — ปัจจุบัน private บล็อก (422) |
| P9 | **Discussions/About pin** ใน repo | ยังไม่ทำ | เปิด Discussions + pin EXP-012 write-up |

## 💡 ไอเดียที่เคยเสนอ (ยังไม่ได้จอง)

- GIF demo ฉบับ Thai language UI
- วิดีโอ/WebM เพิ่ม (ตอนนี้มี mp4+webm ของ demo-chat แล้ว)
- CI badge เพิ่ม: PyPI downloads / release
- ขยาย CI ไป Linux + Python 3.14

## หมายเหตุ

- **ปมที่ต้องตัดสินใจก่อน P1**: Track A (honest platform — public) vs Track B
  (research เงียบ — private) → `docs/DECISION-2026-08-10-track-a-vs-b.md`
- งาน P1–P3 เกี่ยวข้องกัน: public → Pages+social preview → โพสต์ (ลิงก์ต้องไม่ 404)
