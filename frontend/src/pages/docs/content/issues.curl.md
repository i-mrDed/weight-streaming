```bash
# Create (debug context is merged server-side if omitted)
curl -X POST http://127.0.0.1:8765/v1/issues \
  -H "Content-Type: application/json" \
  -d '{"title": "Crash on unload", "description": "Server exits when unloading the last model while a request is in flight.", "severity": "high"}'

# List / filter / export
curl "http://127.0.0.1:8765/v1/issues?status=open"
curl "http://127.0.0.1:8765/v1/issues/export?format=md"

# Maintainer: mark fixed (requires root_cause + fix_summary + verify_steps)
curl -X PATCH http://127.0.0.1:8765/v1/issues/ISSUE-001 \
  -H "Content-Type: application/json" \
  -d '{"status": "fixed", "root_cause": "use-after-free in manager", "fix_summary": "hold ref until request done", "verify_steps": "unload during a stream, expect no crash"}'

# User verification
curl -X POST http://127.0.0.1:8765/v1/issues/ISSUE-001/verify \
  -H "Content-Type: application/json" -d '{"verified": true}'
```
