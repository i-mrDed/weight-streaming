"""Test assistant CRUD via TestClient."""
import os
os.environ["WS_DATA_DIR"] = r"C:\Users\dedch\AppData\Local\Temp\wsdata-p72"
from fastapi.testclient import TestClient
from weight_stream.server.api_server import app

c = TestClient(app)

# Create
r = c.post("/v1/assistants", json={"name": "Translator", "system_prompt": "Translate to Thai", "description": "test"})
print("create:", r.status_code)
aid = r.json()["id"]

# Get
r = c.get(f"/v1/assistants/{aid}")
print("get:", r.status_code, r.json()["name"])

# List
r = c.get("/v1/assistants")
print("list:", r.status_code, len(r.json()))

# Update
r = c.patch(f"/v1/assistants/{aid}", json={"name": "Renamed"})
print("update:", r.status_code, r.json()["name"])

# Delete
r = c.delete(f"/v1/assistants/{aid}")
print("delete:", r.status_code)

# Get after delete (should 404)
r = c.get(f"/v1/assistants/{aid}")
print("get after delete:", r.status_code)