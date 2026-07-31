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

---

# Batch 3 extensions (P5) — locked for this batch onward

| English | Thai | note |
|---|---|---|
| download | ดาวน์โหลด | verb/noun |
| downloads (count) | ยอดดาวน์โหลด | stat on a card |
| Hub | ฮับ | locked since batch 1 |
| repository / repo | repo | keep Latin on cards (short) |
| target folder / save to | บันทึกลงใน | |
| queued | อยู่ในคิว | status label, keep short |
| downloading | กำลังดาวน์โหลด | status label |
| done | เสร็จ | status label |
| failed | ล้มเหลว | status label |
| cancelled | ยกเลิกแล้ว | status label |
| resume | ทำต่อ (resume) | first use may gloss; "ไม่รองรับ resume" for the capability note |
| retry | ลองใหม่ | locked (batch 1) |
| ETA | เวลาที่เหลือโดยประมาณ | but keep `ETA {{eta}}` short: "เหลืออีก ~{{eta}}" is fine |
| speed | ความเร็ว | |
| curated / recommended by the team | รายการแนะนำโดยทีม | honest label — NOT "ยอดนิยม" (that implies ranking) |
| shelf / row | แถวรายการ | |
| unreachable | เชื่อมต่อไม่ได้ | |
| manual drop-in | วางไฟล์เอง | |
| runtime | runtime | keep Latin as the SOURCE BADGE (`src_runtime` value = "runtime") |
| env | env | keep Latin as the SOURCE BADGE |
| default | default | keep Latin as the SOURCE BADGE |
| source (of a value) | แหล่งที่มา | for explanatory sentences only |
| snippet | snippet | keep Latin |
| log tail | ท้าย log / log ท้ายสุด | keep "log" Latin |
| ring buffer | ring buffer | keep Latin |
| library | คลังโมเดล | Models library view |
| on disk | บนดิสก์ | |
| unauthenticated | ไม่มีการยืนยันตัวตน | |
| capability | ความสามารถ | |
| bytes | ไบต์ | |

## Do NOT translate (batch 3 additions)
- `Hugging Face`, `huggingface.co`, `localhost`, `MoE`, `RAM`
- `GET /v1/config`, `PATCH /v1/config`, `GET /v1/logs/tail`, `HTTP 403`, `HTTP 409`
- `WS_*` env names, `data/server.log`, `tok/s` (as a column header keep `tok/s`)
- the source-badge VALUES `env` / `default` / `runtime` (keys `src_env`,
  `src_default`, `src_runtime`) — keep the Latin word; their tooltips ARE Thai
- the dash glyph `–` used for "no measurement"
