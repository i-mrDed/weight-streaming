"""Test MCP server store CRUD via TestClient."""
import os
os.environ["WS_DATA_DIR"] = r"C:\Users\dedch\AppData\Local\Temp\wsdata-p72"
from fastapi.testclient import TestClient
from weight_stream.server.api_server import app

c = TestClient(app)

# Add MCP server
r = c.post("/v1/mcp/servers", json={"name": "filesystem", "transport": "stdio", "command": "npx", "args": ["-y", "@modelcontextprotocol/server-filesystem"]})
print("add:", r.status_code)
sid = r.json()["id"]

# List
r = c.get("/v1/mcp/servers")
print("list:", r.status_code, len(r.json()))

# Delete
r = c.delete(f"/v1/mcp/servers/{sid}")
print("delete:", r.status_code)
print("delete again:", c.delete(f"/v1/mcp/servers/{sid}").status_code)  # 404

# list tools (should return [] gracefully if mcp connect fails / no servers)
r = c.get("/v1/mcp/tools")
print("tools:", r.status_code, "len:", len(r.json()))