# Glossary — locked terms (single source of truth, batches 1–2)

Use these Thai terms consistently. Batch-1 terms are locked; batch-2 extends
them. If a term is not listed, choose a concise natural Thai rendering and
stay consistent.

| English | Thai | note |
|---|---|---|
| model | โมเดล | |
| models | โมเดล | |
| load | โหลด | |
| unload | ปลดโหลด | |
| reload | โหลดใหม่ | |
| loaded | โหลดแล้ว | |
| scan | สแกน | |
| buffer | บัฟเฟอร์ | |
| chat | แชท | |
| conversation | บทสนทนา | |
| issue / report issue | ปัญหา / รายงานปัญหา | |
| theme | ธีม | |
| language | ภาษา | |
| settings | การตั้งค่า | |
| overview | ภาพรวม | |
| live stats | สถิติแบบสด | |
| hub | ฮับ | |
| API Docs | เอกสาร API | |
| appearance | รูปลักษณ์ | |
| particle background | พื้นหลังอนุภาค | |
| server | เซิร์ฟเวอร์ | |
| connected | เชื่อมต่อแล้ว | |
| checking | กำลังตรวจสอบ | |
| retry | ลองใหม่ | |
| cancel | ยกเลิก | |
| close | ปิด | |
| copy | คัดลอก | |
| copied | คัดลอกแล้ว | |
| search | ค้นหา | |
| confirm | ยืนยัน | |
| save | บันทึก | |
| display name | ชื่อที่แสดง | |
| auto (follow system) | อัตโนมัติ (ตามระบบ) | |
| under construction | อยู่ระหว่างพัฒนา | |
| **batch 2 — new terms** | | |
| generation / generate | การ generate / generate | loanword is standard in Thai LLM UI |
| tokens | โทเคน | |
| token | โทเคน | |
| context window | ขนาด context / คอนเท็กซ์ | "CTX" label keep as CTX |
| threads | เธรด | |
| hit rate | อัตราการฮิต | decided once — keep this everywhere |
| residency | เรซิเดนซี (สัดส่วนใน page cache) | first use may gloss; later uses short form |
| page cache | page cache | do not translate |
| paging demand | ความต้องการ paging | keep "paging" |
| fault / faults | ฟอลต์ | page-fault sense |
| prefetch | พรีเฟตช์ | |
| expert / MoE | expert / MoE | keep Latin |
| heatmap | ฮีตแมป | |
| gauge | เกจ | |
| session window | ช่วงเซสชัน | |
| system prompt | system prompt | keep Latin |
| temperature | temperature | keep Latin (ML term) |
| reasoning effort | ระดับการให้เหตุผล | |
| agent mode | โหมด agent | |
| parameter | พารามิเตอร์ | |
| preset | พรีเซ็ต | |
| export | ส่งออก | |
| rename | เปลี่ยนชื่อ | |
| delete | ลบ | |
| send | ส่ง | |
| stop | หยุด | |
| priority | ความสำคัญของโปรเซส | process priority sense |
| queue | คิว | |
| honest / n/a | according to context | keep `n/a` glyph as-is |
| today / yesterday / older | วันนี้ / เมื่อวาน / เก่ากว่า | grouping labels |
| thinking | กำลังคิด | <think> accordion |

## Do NOT translate (keep in Latin / as-is)
- Brand: `Weight Streaming`, `Console`
- Theme proper names: `Classic Dark`, `Aurora Dark`, `Aurora Light`
- Phase codes: `P2`, `P3`, `P4`, `P5` · ADR ids: `ADR-003`
- Version token: `v{{version}}`
- Key combos: `Ctrl+K`, `Enter`, `Shift+Enter`, `esc`, `↑↓`
- Endpoint / code / command text (`pip install -U llama-cpp-python`, `/v1/...`)
- Quant tags: `Q2_K`, `Q4_K_M`, `F16`, `F32`, `BF16` …
- Units/symbols: `MB`, `GB`, `tok/s`, `pp`, `%`, `↑`, `↓`, `→`, `▲`, `⚠️`, `💭`
- Formats/products: `GGUF`, `.gguf`, `.md`, `Markdown`, `localStorage`,
  `Windows`, `POSIX`, `llama.cpp`, `Jan Desktop`
- `n/a`, `OK`, `EN`, `TH`
- The glyphs inside strings (e.g. the ✓ in "Copied ✓") — keep them
