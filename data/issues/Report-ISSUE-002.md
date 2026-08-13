# Report-ISSUE-002: ทดสอบการใช้งานหลังอัพเดท Llama แล้ว

- **Status:** in_progress
- **Severity:** critical
- **Created:** 2026-07-27T14:16:42Z by local-user
- **Updated:** 2026-07-27T15:18:45Z

## Description
- สามารถโหลด Qwen3.6 จาก Browse / path ได้
- กดโหลดโมเดล Qwen3.6 ได้แล้ว
- จุดที่ยังเป็นปัญหาคือ หน้าแชทครับ โมเดลยังตอบเป็นภาษาไทยไม่ได้ , ยิ่งตอนโหลดหลายโมเดลเข้ามาด้วยแล้ว ตอนแชทไม่รู้เลยว่ากำลังแชทอยู่กับโมเดลไหน และก็ไม่สามารถเลือกการตั้งค่าต่างๆของโมเดลได้เช่น Models, Tools, Effort ฯลฯ
- ตอนแชทยาวลงไปเรื่อยๆ มันจะหลุดหน้าจอและหล่นลงไปข้างล่างเรื่อยๆเลยครับ ควรต้องปรับใหม่อย่างยิ่ง
** สรุปแล้ว หน้า Chat นี้ ควรต้องออกแบบระบบใหม่, UXUI ใหม่ ต้องวางและเขียนแผนฯออกมาโดยละเอียดก่อนลงมือทำ

## Context
```json
{
  "app_version": "0.12.0",
  "llama_cpp_version": "0.3.34",
  "python_version": "3.14.2",
  "os": "Windows-11-10.0.22631-SP0",
  "cwd": "<repo-root>",
  "model_path": "<repo-root>/research/models/Qwen1.5-MoE-A2.7B_Q2_k.gguf",
  "model_architecture": "qwen2moe",
  "last_error": null,
  "last_endpoint": "/health",
  "env": {
    "WS_AUTO_MODEL_PATH": "research/models/Qwen1.5-MoE-A2.7B_Q2_k.gguf",
    "WS_AUTO_MODEL_ID": "default",
    "WS_BUFFER_MB": "64",
    "WS_N_CTX": "512"
  }
}
```

## Timeline
- `2026-07-27T14:16:42Z` **created** by local-user
- `2026-07-27T15:18:05Z` **status:in_progress** by maintainer — เริ่มวางแผน Chat UX redesign
