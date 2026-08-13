# 🖼️ QA / UI Evidence Artifacts

ที่เก็บ screenshot/หลักฐานจาก QA และการปรับ UI ของ Console **แบบจัดเป็นระเบียบ**.

> 📌 **กฎ (ห้ามละเมิด):** ห้ามบันทึก screenshot ลง root ของ repo (`*.png` หน้าบ้าน)
> ให้บันทึกที่ `docs/artifacts/<phase>/` ตามโฟลเดอร์เฟสโดยเฉพาะเท่านั้น.

## โครงสร้าง (group by phase)
```
docs/artifacts/
├── README.md        ← ไฟล์นี้ (กติกา)
├── .gitignore       ← ซ่อนรูปทั้งหมดจาก git status เสมอ
├── phase-2/         ← P2 (p2fix-*)
├── phase-3/         ← P3 (p3-*)
├── phase-5/         ← P5 (p5-*, p5-hub-*)
├── phase-5-2/       ← P5.2 (p52-*)  ← screenshots หน้าล่าสุด
└── polish/          ← polish รอบพวก pol-*
```

## วิธีการ (ต่อจากนี้)
1. **agent หน้า frontend / QA**: เมื่อจับ screenshot เป็นหลักฐาน → บันทึกที่
   `docs/internal/artifacts/<phase>/`
2. **การตั้งชื่อ**: ขึ้นต้นด้วย prefix เฟส (`phase-5-2` → `p52-...`), ตามด้วยบริบท เช่น
   `p52-hub-after-results.png`, `p52-models-library.png`.
3. **อย่า** dump ขึ้น root — ถ้าเห็นไฟล์ `*.png` หลุดขึ้น root ให้ย้ายกลับมาไว้ตรงนี้.

## ทำไม `.gitignore` อยู่ข้างใน
โฟลเดอร์นี้เป็น evidence ที่ไม่ต้อง commit; การมี `.gitignore` (`*` + un-ignore
`.gitignore`/`README.md`) ทำให้ `git status` สะอาดตลอด แต่ README (กติกา) ถูกเวอร์ชัน
เผื่อเรื่อง convention. อย่าลบคอนเทนต์ในนี้เพื่อความสะอาดของ status — แค่ย้ายช่วย.

_อัปเดต: 2026-08-02 ตามคำขอผู้ใช้ "จัดเก็บอย่างเป็นระเบียบ ไม่กลับมารก (แทนลบ)"._