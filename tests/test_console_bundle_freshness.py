"""The committed console bundle must be in sync with the frontend source.

Regression guard for the 2026-08-13 stale-bundle incident: auto-compact
and the n_ctx/max_tokens defaults landed in frontend source, but the
committed bundle (weight_stream/server/static/console) predated them —
so anyone cloning the repo and running the server got a console without
those features. CI's bundle-freshness guard catches it by rebuilding;
this test is the cheap local check that the *committed* bundle is the
one the server actually serves and carries the features we ship.

Kept intentionally tiny and dependency-free: reads the served index.html,
resolves the JS bundle it references, and asserts a few sentinel strings.
"""
import re
from pathlib import Path

import pytest

STATIC = Path(__file__).resolve().parents[1] / "weight_stream" / "server" / "static" / "console"
INDEX_HTML = STATIC / "index.html"

# Sentinel strings that must be present in the bundle the server serves.
# If a feature lands in frontend source but the bundle isn't rebuilt,
# one of these goes missing and this test fails.
REQUIRED_BUNDLE_SNIPPETS = [
    # auto-compact (context-management, research/12): the toast i18n key
    "chat.summary.auto",
    # default max_tokens 4096 (fix 2026-08-13, PR #10 follow-up)
    "max_tokens:4096",
]

# A hash is embedded in the asset filename (index-<hash>.js). This must
# look like the real thing so we don't accidentally match a stale name.
_BUNDLE_RE = re.compile(r'src="(/console/assets/index-[A-Za-z0-9_-]+\.js)"')


def _referenced_bundle() -> Path:
    if not INDEX_HTML.exists():
        pytest.fail(f"served console index.html not found: {INDEX_HTML}")
    html = INDEX_HTML.read_text(encoding="utf-8", errors="replace")
    m = _BUNDLE_RE.search(html)
    if not m:
        pytest.fail(
            f"no JS bundle reference found in {INDEX_HTML}; "
            "frontend build output looks wrong"
        )
    # "/console/assets/index-x.js" -> <static>/assets/index-x.js
    rel = m.group(1).removeprefix("/console/")
    return STATIC / rel


def test_console_bundle_referenced_file_exists():
    bundle = _referenced_bundle()
    assert bundle.is_file(), (
        f"index.html references {bundle.name} but the file is missing — "
        "rebuild the bundle: cd frontend && npm run build"
    )


def test_console_bundle_contains_current_features():
    bundle = _referenced_bundle()
    content = bundle.read_text(encoding="utf-8", errors="replace")
    missing = [s for s in REQUIRED_BUNDLE_SNIPPETS if s not in content]
    assert not missing, (
        f"committed console bundle ({bundle.name}) is stale — missing "
        f"{missing}. Rebuild and commit it: cd frontend && npm run build"
    )
