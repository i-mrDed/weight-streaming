# Go-Public Checklist (private → public)

> **Status:** repo is PRIVATE (since 2026-08-10). Everything below is prepared so the
> switch can happen in one sitting. Rough total: ~30 minutes of clicks + CI wait.
>
> The one strategic gate: **Track A vs Track B** — see
> [`docs/DECISION-2026-08-10-track-a-vs-b.md`](DECISION-2026-08-10-track-a-vs-b.md).
> Going public is only worth it if you accept the "honest platform" framing
> (Track A) as the product; a public repo actively contradicts "quiet research"
> (Track B). Both reviews that read the repo deeply (Sonnet, OpenCode) flagged
> this identity question first.

## 0. Decision gate (before anything)

- [x] **Decided 2026-08-13** — Track A as product + Track B as bounded research
      spike (see [`docs/DECISION-2026-08-10-track-a-vs-b.md`](DECISION-2026-08-10-track-a-vs-b.md)
      — updated with EXP-025..030 + paper + fact-check evidence).
- [x] Answer was "ready for public" — proceeding with the switch steps below.

## 1. Pre-flight verification (5 min)

Run from the repo root:

```bash
python -m pytest                 # expect ~471 passed (verified 2026-08-13: 471 passed / 7 skipped)
python -m mypy                   # expect: Success, 0 errors (verified 2026-08-13: 60 files, clean)
cd frontend && npm test          # expect 7 passed
# npm test needs a browser/screen on Windows — see the CI job for the headless invocation
git status --short               # expect clean except the Thai review folder (untracked, your call)
```

- [x] **CI is green on `main`** — verified 2026-08-13 on `ba3c37f`: CI 5/5 jobs
      success + Secret Scan success (7/7 check-runs).
- [x] **Path leak scan re-run 2026-08-13** — `C:/Users/<user>` cleaned from
      TASKS.md + ISSUES.md (3 จุด); scan now clean.
- [x] **Secrets scan** — no `ghp_`/`sk-`/`hf_`/password patterns (remaining hits
      are false positives: scan-instruction text + "disk-mmap").
- [ ] **Decide the fate of `บันทึกรีวิวโปรเจค/`** (4 platform reviews + analysis):
      either commit it (it's good public content) or keep it out — **เป็น decision ของคุณ**.

## 2. Release v0.15.0 (before or right after the switch)

Everything is version-bumped and the wheel is fixed (console now ships in
`package-data`); the GitHub **release does not exist yet**.

- [ ] `git tag v0.15.0 && git push origin v0.15.0`
- [ ] Create the GitHub release from the tag with notes from
      [`CHANGELOG.md`](../CHANGELOG.md) 0.15.0 section (security W1–W5, auth,
      frontend tests, mypy-clean, console-in-wheel).
- [ ] **PyPI publish (optional)** — `python -m build && twine upload dist/*`
      needs your PyPI credentials (this machine has none configured).
      Verify the wheel contains `weight_stream/server/static/console/index.html`.

## 3. Flip visibility (1 min) — ✅ DONE 2026-08-13

```bash
gh repo edit i-mrDed/weight-streaming --visibility public --accept-visibility-change-consequences
# (the --accept-* flag is required by gh ≥2.41)
```

- [x] **Flipped 2026-08-13** — `https://github.com/i-mrDed/weight-streaming`
      is now PUBLIC (`visibility=PUBLIC`).
- [x] Description + topics already set — verified: 15 topics
      (`llm`, `local-llm`, `moe`, `gguf`, `llama-cpp`, `out-of-core`,
      `nvme`, `memory-mapping`, `deepseek`, `qwen`, `benchmarking`…).
- [x] LICENSE file present (MIT) — added 2026-08-10.
- [x] **v0.15.0 release** — tag moved to current `main` (2026-08-13) with
      updated notes (security + auto-tiering + bench harness + 30 EXP);
      public at `releases/tag/v0.15.0`.

## 4. GitHub Settings (manual — no CLI) — 5 min

> **Updated 2026-08-13:** Pages is now ENABLED via API
> (`https://i-mrded.github.io/weight-streaming/`, building from `main` `/docs`,
> `docs/index.md` present). Social preview image still needs the manual
> Settings → Social preview upload (browser step).

These two cannot be set via `gh`; do them in the browser:

- [ ] **Social preview image**: Settings → Social preview → Upload
      `docs/screenshots/hero.png` (1280×640, app-logo hero with tagline —
      already generated). This is the card shown when the repo is shared on
      X/LinkedIn/Discord.
- [ ] **GitHub Pages** (optional but recommended for discoverability): Settings →
      Pages → build from `main` `/docs`. Consider adding a `docs/index.md`
      landing that links to README, screenshots, EXP write-ups, and the
      HARDWARE plan. (Repo must be public for Pages to be public.)
      > **Verified 2026-08-10:** the Pages API returns 422 "Your current plan
      > does not support GitHub Pages for this repository" while the repo is
      > PRIVATE (GitHub Free only serves Pages for public repos). The landing
      > page (`docs/index.md`) is committed and ready; enable Pages in this
      > step, right after the visibility flip — 2 clicks.
- [ ] Repo metadata: consider enabling Discussions (community questions land
      somewhere visible) and pinning the EXP-012 write-up link in the About box.

## 5. Publish the content assets (30 min)

All drafts already exist in [`research/writeups/`](../research/writeups/):

- [ ] **r/LocalLLaMA post** — `2026-08-10-reddit-r-localLLaMA.md` (3 title
      options, body with the honest-telemetry hook: "104 GB model on 64 GB RAM,
      measured, page-faults per token"). Post it with the banner + stats
      screenshot attached.
- [ ] **Blog / HF article** — `2026-08-10-exp012-104gb-on-64gb-ram.md`
      (full write-up, EN + TH summary) — publish to your blog or HF community
      article, cross-link the repo.
- [ ] **README self-checks**: banner + GIF + 6 screenshots already embedded;
      verify they render after the switch (they are committed files, they will).

## 5b. ป้องกันการเกิดซ้ำ (added 2026-08-13 — post-public hardening)

- [x] **CI guard `devpath-leak-check`** (ใน `.github/workflows/secret-scan.yml`) —
      block push/PR ที่มี dev-machine path: `C:/Users/<real-username>`, `.opencode/`,
      `.worktrees/` (ยกเว้น `runneradmin` = CI runner ของ GitHub เอง).
- [x] **กติกา path สำหรับทุก contribution ใหม่:** ใช้ relative / `~/` / `<user>`
      placeholder เสมอ — ห้าม commit drive letter + username จริง.
- [x] **docs วางแผนภายใน (`docs/internal/`)** — BRIEF/verification/artifacts
      ย้ายออกจากหน้าหลัก (ยังอยู่ใน repo, git history คงอยู่).
- [x] **README note เรื่อง history** — บอกว่าพาธเก่าใน commits เก่าเป็น
      artifact ของ dev machine ไม่ใช่ secret.

## 6. Post-public verification (10 min)

- [ ] CI runs green on public (free unlimited minutes — GitHub Free public).
- [ ] README renders: banner, GIF, screenshot table, badges.
- [ ] Release v0.15.0 is public and downloadable (source zip + wheel asset if
      uploaded).
- [ ] Repo appears in GitHub search for the topics (usually within hours).
- [ ] Watch for the first weeks: respond to issues/PRs, keep the honest-telemetry
      rule in every reply (it is the differentiator).

## 7. If you ever go private again

- [ ] `gh repo edit i-mrDed/weight-streaming --visibility private`
- [ ] Note: Pages + social preview keep their settings; releases stay public on
      the page but the repo disappears from search.
- [ ] Everything in this checklist is reversible except **published posts** —
      think twice before posting, not after.
