# Draft — r/LocalLLaMA post (title + body)

> **Title (pick one):**
> - `[D] I ran a 104 GB LLM on 64 GB RAM + 12 GB VRAM — 1.9 tok/s, and I have the page-fault receipts`
> - `[D] The honest benchmark nobody publishes: 104 GB model on a consumer machine`
> - `[R] 104 GB DeepSeek-V4-Flash on 12 GB VRAM / 64 GB RAM: what the telemetry actually says`

---

## Body

**tl;dr** — Ran DeepSeek-V4-Flash-0731 (104 GB GGUF) on an i9-9900KF +
RTX 3060 12 GB + 64 GB DDR4 + NVMe. It works at **1.5–1.9 tok/s**. The
interesting part is *why*: 36k–77k page faults per token ≈ 150–300 MB of
disk reads **per token**. The bottleneck is the disk→RAM→CPU pipeline, and
you can see it in real OS telemetry, not vibes.

Full write-up + open-source harness (MIT) — out-of-core inference,
memory-mapped GGUF from NVMe, llama.cpp + MoE (DeepSeek / Qwen):
https://github.com/i-mrDed/weight-streaming

Screenshots of the console (live tok/s + page-fault telemetry) and a
short demo GIF are in the README, plus the full benchmark write-up.

**The numbers**

| config | cold | warm | faults/tok | disk MB/tok |
|---|---:|---:|---:|---:|
| all-CPU experts t8 | 1.48 | 1.76 | 68k | ~150–270 |
| tiered t8 | 1.46 | 1.89 | 76k | ~160–300 |
| t16 | 1.71 | 1.75 | 65k | ~145–260 |
| auto (n-cpu-moe 0) | 1.65 | 1.83 | 63k | ~150–250 |
| force everything to 12 GB VRAM | OOM | — | — | — |

Config tweaks move it ~15%. The wall is disk, not compute.

**Dead ends we actually measured (17 experiments logged):**

- Speculative decoding (llama.cpp draft-mtp) → **slower** on this box
  (−11–18%). The draft step still computes the full MoE forward pass.
- Expert census → "hot expert" tiering → expert activation is **flat**
  across layers; placement gains track bytes-on-GPU, not position.
- CPU lane (compute hot experts on CPU, like pulsar) → CPU only 39–51%
  busy because **DDR4 bandwidth is saturated**. Adding work to a
  bandwidth-bound CPU doesn't help.
- The ONE lever that works: **bytes-per-token** (IQ1_M vs IQ2_M on a
  10 GB MoE: 77 vs 56 tok/s). Lower bytes → more resident → fewer faults.

**Lesson:** on a bandwidth-bound pipeline, every optimization is a
bytes-per-token play. No software trick replaces RAM ≥ model size or
VRAM ≥ working set. Buy hardware with data, not hype.

**The actual contribution** is the honest measurement methodology:
page-fault-per-token and disk-MB-per-token telemetry on the llama-server
path, plus a clean-room gate that refuses to report numbers from
contaminated runs. The repo also documents the hardware plan (2026
prices) for the cheapest 100+ tok/s path.

Search-friendly summary for anyone landing from a search: **out-of-core
LLM inference** · **run models bigger than RAM** · **NVMe as extension
of memory** · **MoE expert streaming** · **honest telemetry (tok/s, page
faults/token, disk MB/token)** — if any of those is your question, the
repo has measured answers, not marketing.

---

## Visuals to attach when posting (files already on disk)

- `docs/screenshots/banner.png` — 1280×640 social banner (attach as the
  post image).
- `docs/screenshots/03-stats.png` — the live-telemetry page (tok/s gauge,
  faults/token, VRAM). This is the money shot.
- `docs/screenshots/demo-chat.gif` — 9 s console demo ending on the
  stats page (Reddit allows GIF uploads; keep it as a second attachment).
- All six screenshots + GIF are committed in the repo under
  `docs/screenshots/`, so the README stays visual even if Reddit hotlinks
  are stripped.

Happy to answer questions / discuss methodology. Anyone else measuring
faults-per-token on >RAM models? Curious if the 150–300 MB/token figure
matches other people's experience.

---

## Comments/notes for the author

- Post as text post with a link, not a link post (better engagement on
  r/LocalLLaMA).
- Pin the "n-cpu-moe 0 runs fine" surprise in a comment — people will
  ask why we didn't just offload more.
- Be ready for "why would you run this" — the honest answer is the
  methodology + the hardware decision data.
- Post timing: weekday morning US time for max visibility.
- The repo is currently **private** — flip it public (see
  `docs/GO_PUBLIC_CHECKLIST.md`) *before* posting, or the link 404s for
  readers. The checklist is a ~30-min run: release tag, visibility,
  social-preview image, Pages, then post.
- The repo is currently **private** — flip it public (see
  `docs/GO_PUBLIC_CHECKLIST.md`) *before* posting, or the link 404s for
  readers. The checklist is a ~30-min run: release tag, visibility,
  social-preview image, Pages, then post.
