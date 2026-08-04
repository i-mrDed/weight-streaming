"""
Assistant store (P7.2).

JSON-file-backed CRUD for assistants — each assistant is a named recipe of
system prompt + model + generation params, like Jan's assistants. Users can
create/edit/delete/select assistants to quickly switch chat personas.

Persistence: one JSON file per assistant under ``data/assistants/<id>.json``
(local-first, offline-friendly — no network needed). Mirrors the issues
store pattern.

Schemas (simplified, matching the Console):
    Assistant = {
        id, name, description,
        system_prompt,
        model_id,          # optional — falls back to the selected model
        params: { temperature, top_p, max_tokens },  # optional overrides
        created_at, updated_at,
    }

Concurrency: in-process lock around reads/writes (single server process).
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from typing import Any, Dict, List, Optional

import aiofiles

logger = logging.getLogger(__name__)

ASSISTANTS_DIR = "data/assistants"


def _assistants_dir() -> str:
    """Resolve the assistants directory (honor WS_DATA_DIR if set)."""
    base = os.environ.get("WS_DATA_DIR", "data")
    return os.path.join(base, "assistants")


class AssistantStore:
    """JSON-file-backed assistant store (thread-safe)."""

    def __init__(self, directory: Optional[str] = None):
        self._dir = directory or _assistants_dir()
        self._lock = threading.Lock()
        os.makedirs(self._dir, exist_ok=True)

    def _path(self, assistant_id: str) -> str:
        return os.path.join(self._dir, f"{assistant_id}.json")

    def _read(self, assistant_id: str) -> Optional[Dict[str, Any]]:
        try:
            with open(self._path(assistant_id), "r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            return None
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("read assistant %s failed: %s", assistant_id, e)
            return None

    def _write(self, assistant: Dict[str, Any]) -> None:
        with self._lock:
            with open(self._path(assistant["id"]), "w", encoding="utf-8") as f:
                json.dump(assistant, f, ensure_ascii=False, indent=2)

    def list(self) -> List[Dict[str, Any]]:
        """List all assistants (sorted by name)."""
        out: List[Dict[str, Any]] = []
        for fn in os.listdir(self._dir):
            if fn.endswith(".json"):
                try:
                    with open(os.path.join(self._dir, fn), "r", encoding="utf-8") as f:
                        a = json.load(f)
                    if isinstance(a, dict) and a.get("id"):
                        out.append(a)
                except (json.JSONDecodeError, OSError):
                    continue
        out.sort(key=lambda a: a.get("name", "").lower())
        return out

    def get(self, assistant_id: str) -> Optional[Dict[str, Any]]:
        return self._read(assistant_id)

    def create(
        self,
        name: str,
        system_prompt: str = "",
        description: str = "",
        model_id: Optional[str] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        now = int(time.time() * 1000)
        assistant = {
            "id": uuid.uuid4().hex[:12],
            "name": name,
            "description": description,
            "system_prompt": system_prompt,
            "model_id": model_id,
            "params": params or {},
            "created_at": now,
            "updated_at": now,
        }
        self._write(assistant)
        return assistant

    def update(
        self,
        assistant_id: str,
        name: Optional[str] = None,
        system_prompt: Optional[str] = None,
        description: Optional[str] = None,
        model_id: Optional[str] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        a = self._read(assistant_id)
        if a is None:
            return None
        if name is not None:
            a["name"] = name
        if system_prompt is not None:
            a["system_prompt"] = system_prompt
        if description is not None:
            a["description"] = description
        if model_id is not None:
            a["model_id"] = model_id
        if params is not None:
            a["params"] = params
        a["updated_at"] = int(time.time() * 1000)
        self._write(a)
        return a

    def delete(self, assistant_id: str) -> bool:
        try:
            os.remove(self._path(assistant_id))
            return True
        except FileNotFoundError:
            return False
        except OSError as e:
            logger.warning("delete assistant %s failed: %s", assistant_id, e)
            return False


# Singleton
_store: Optional[AssistantStore] = None


def get_assistant_store() -> AssistantStore:
    global _store
    if _store is None:
        _store = AssistantStore()
    return _store