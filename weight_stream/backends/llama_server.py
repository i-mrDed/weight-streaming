"""
llama-server backend adapter (P7.1b).

Runs the official llama.cpp `llama-server` executable as a subprocess and
talks to it over its OpenAI-compatible HTTP API. This is the same approach
Jan uses, and it gives us three things the Python binding (llama-cpp-python
0.3.34) cannot:

1. **Native reasoning control** — `--reasoning on|off|auto` + `--reasoning-budget N`
   (the binding has no reasoning fields in its C API).
2. **GPU offload** — binaries built with CUDA/Vulkan offload layers to the GPU
   (the CPU-only binding explains the 2–4 vs 35–40 tok/s gap vs Jan).
3. **A foundation for P7.3/P7.4** — tool calling + MCP need the server's
   OpenAI-compatible /v1/chat/completions with tools support.

Design:
- Lazily spawns llama-server on the first request (or explicitly via `start()`).
- Uses a dedicated port, never colliding with the API server.
- `stream_chat()` consumes the server's SSE stream and yields text deltas.
- `get_stats()` reports real generation timing + token usage.
- `get_capabilities()` reuses the same heuristic detector.
- Falls back gracefully: if the server binary is missing, `is_available()`
  is False and the caller keeps using the binding backend.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import time
import urllib.request
import urllib.error
from typing import Any, Dict, Iterator, List, Optional

from ._base import WeightStreamBackend
from ..core.exceptions import ModelError, GenerationError

logger = logging.getLogger(__name__)

# Where llama-server binaries live (Jan ships CUDA builds alongside this app).
_JAN_BACKENDS = os.path.join(
    os.environ.get("APPDATA", ""),
    "Jan", "data", "llamacpp", "backends",
)

# Fixed port for the server subprocess (API server uses 8765/8804/...).
DEFAULT_SERVER_PORT = 8805
DEFAULT_HOST = "127.0.0.1"


def _find_llama_server() -> Optional[str]:
    """Locate a llama-server executable (newest version preferred)."""
    # 1) Explicit env override
    env = os.environ.get("WS_LLAMA_SERVER")
    if env and os.path.isfile(env):
        return env
    # 2) Jan's bundled backends
    if os.path.isdir(_JAN_BACKENDS):
        candidates = []
        for base, _, files in os.walk(_JAN_BACKENDS):
            for f in files:
                if f == "llama-server.exe" or f == "llama-server":
                    candidates.append(os.path.join(base, f))
        if candidates:
            # Prefer newest (sort by modification time desc)
            candidates.sort(key=lambda p: os.path.getmtime(p), reverse=True)
            return candidates[0]
    # 3) PATH
    found = shutil.which("llama-server")
    return found


class LlamaServerBackend(WeightStreamBackend):
    """Backend that runs llama-server as a subprocess and uses its HTTP API."""

    def __init__(
        self,
        model_path: str,
        n_ctx: int = 2048,
        n_threads: Optional[int] = None,
        gpu_layers: int = -1,  # -1 = auto (use all available)
        server_binary: Optional[str] = None,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_SERVER_PORT,
        **kwargs,
    ):
        self._model_path = model_path
        self._n_ctx = n_ctx
        self._n_threads = n_threads
        self._gpu_layers = gpu_layers
        self._server_binary = server_binary or _find_llama_server()
        self._host = host
        self._port = port
        self._proc: Optional[subprocess.Popen] = None
        self._base_url = f"http://{host}:{port}"
        self._last_gen_stats: Dict[str, Any] = {}
        self._metadata: Dict[str, Any] = {}
        self._ready = False
        self._started = False

        # Detect capabilities from the GGUF metadata (arch + name).
        try:
            from weight_stream.gguf.parser import GGUFParser
            with GGUFParser(model_path) as parser:
                self._metadata = parser.metadata or {}
        except Exception:
            self._metadata = {}

    # ── Availability ────────────────────────────────────────────────
    @classmethod
    def is_available(cls) -> bool:
        return _find_llama_server() is not None

    @property
    def is_loaded(self) -> bool:
        return self._ready and self._proc is not None and self._proc.poll() is None

    # ── Lifecycle ───────────────────────────────────────────────────
    def start(self):
        """Spawn llama-server subprocess (idempotent)."""
        if self._started:
            return
        if not self._server_binary:
            raise ModelError(
                "llama-server not found",
                details={"hint": "Set WS_LLAMA_SERVER or install Jan"},
            )
        cmd = [
            self._server_binary,
            "-m", self._model_path,
            "-c", str(self._n_ctx),
            "--host", self._host,
            "--port", str(self._port),
            "--reasoning", "auto",
            "--reasoning-budget", "-1",
        ]
        if self._n_threads:
            cmd += ["-t", str(self._n_threads)]
        if self._gpu_layers != -1:
            cmd += ["-ngl", str(self._gpu_layers)]
        # Quiet: don't spam logs
        cmd += ["--log-disable"]

        logger.info(f"Starting llama-server: port={self._port} model={os.path.basename(self._model_path)}")
        self._proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        self._started = True
        self._wait_ready(timeout=60)

    def _wait_ready(self, timeout: float = 60.0):
        """Poll /health until the server is up."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self._proc is not None and self._proc.poll() is not None:
                raise ModelError(
                    "llama-server exited early",
                    details={"returncode": self._proc.returncode},
                )
            try:
                with urllib.request.urlopen(f"{self._base_url}/health", timeout=2) as r:
                    if r.status == 200:
                        self._ready = True
                        return
            except Exception:
                pass
            time.sleep(0.5)
        raise ModelError("llama-server not ready (timeout)", details={"port": self._port})

    # ── OpenAI-compatible request helper ────────────────────────────
    def _request(
        self,
        path: str,
        payload: Dict[str, Any],
        timeout: float = 300.0,
    ) -> Iterator[Dict[str, Any]]:
        """POST to the server, yielding parsed SSE events (streaming)."""
        if not self.is_loaded:
            self.start()
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self._base_url}{path}",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                for raw in resp:
                    line = raw.decode("utf-8", errors="replace").strip()
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        yield json.loads(data)
                    except json.JSONDecodeError:
                        continue
        except urllib.error.HTTPError as e:
            msg = e.read().decode("utf-8", errors="replace")
            raise GenerationError(f"llama-server HTTP {e.code}: {msg[:300]}")
        except Exception as e:
            raise GenerationError(f"llama-server request failed: {e}")

    # ── Public API (matches WeightStreamBackend) ────────────────────
    @staticmethod
    def _inject_current_date(messages: List[dict]) -> List[dict]:
        """Inject the current date into the system message.

        Models don't know today's date — without it they hallucinate
        (e.g. answering "June" in August). Jan does the same via the
        `{{current_date}}` placeholder. We inject at the backend so every
        client (console, IDE, API) gets the correct date.
        """
        import datetime
        now = datetime.datetime.now()
        date_str = now.strftime("%B %d, %Y")  # e.g. "August 04, 2026"
        out = list(messages)
        # Prepend a system message with the current date (keep existing).
        out.insert(0, {
            "role": "system",
            "content": f"Current date: {date_str}.",
        })
        return out

    def generate(
        self,
        prompt: str,
        max_tokens: int = 128,
        temperature: float = 0.7,
        top_p: float = 0.9,
        **kwargs,
    ) -> str:
        return "".join(self.stream_chat(
            [{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
            **kwargs,
        ))

    def stream_chat(
        self,
        messages: List[dict],
        max_tokens: int = 128,
        temperature: float = 0.7,
        top_p: float = 0.9,
        reasoning_mode: str = "auto",
        tools: Optional[List[dict]] = None,
        tool_choice: Optional[Any] = None,
        **kwargs,
    ) -> Iterator[str]:
        """Stream chat via llama-server's OpenAI-compatible API.

        reasoning_mode: auto|on|off → passed to the server as `reasoning`.
        The server itself handles thinking extraction (message.reasoning_content),
        so content deltas are the final answer only.

        tools/tool_choice (P7.3): passed through to llama-server, which
        natively supports tool calling. tool_calls are returned via the
        ``tool_calls`` attribute on this instance after generation.
        """
        if not self.is_loaded:
            self.start()

        mode = (reasoning_mode or "auto").lower()
        if mode not in ("on", "off"):
            mode = "auto"

        # Inject current date so the model doesn't hallucinate the date.
        messages = self._inject_current_date(messages)

        payload = {
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_p": top_p,
            "stream": True,
            "reasoning": mode,
            # Keep everything in `content` (no reasoning_content split). We
            # manage thinking ourselves with parseThinks (prose + tags) so
            # qwen35-family models (Qwythos/Ornith) that don't close their
            # reasoning tags still return their answer in content.
            "reasoning_format": "none",
        }
        if tools:
            payload["tools"] = tools
        if tool_choice is not None:
            payload["tool_choice"] = tool_choice

        # Reset accumulated tool_calls from any previous generation.
        self._tool_calls: List[dict] = []

        start_time = time.time()
        token_count = 0
        reasoning_chunks: List[str] = []
        try:
            for event in self._request("/v1/chat/completions", payload):
                choices = event.get("choices") or []
                if not choices:
                    continue
                delta = (choices[0].get("delta") or {})
                # llama-server (--reasoning-format deepseek) separates the
                # chain-of-thought into `reasoning_content` and the final
                # answer into `content`. We yield only the answer; the
                # reasoning trace is captured for stats/UI.
                rtext = delta.get("reasoning_content") or ""
                if rtext:
                    reasoning_chunks.append(rtext)
                text = delta.get("content") or ""
                if text:
                    token_count += 1
                    yield text
                # Tool calls (P7.3): accumulate across delta chunks.
                tc = delta.get("tool_calls")
                if tc:
                    self._accumulate_tool_calls(tc)
        except GeneratorExit:
            raise
        finally:
            elapsed = time.time() - start_time
            self._last_gen_stats = {
                "token_count": token_count,
                "elapsed": elapsed,
                "tokens_per_sec": token_count / elapsed if elapsed > 0 else 0,
                "prompt": self._summarize_messages(messages),
                "backend": "llama-server",
                "reasoning_chars": sum(len(c) for c in reasoning_chunks),
                "tool_calls": len(self._tool_calls),
            }

    def stream_prompt(
        self,
        prompt: str,
        max_tokens: int = 128,
        temperature: float = 0.7,
        top_p: float = 0.9,
        **kwargs,
    ) -> Iterator[str]:
        return self.stream_chat(
            [{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
            **kwargs,
        )

    def close(self):
        """Stop the llama-server subprocess. Safe to call multiple times."""
        if self._proc is not None:
            try:
                self._proc.terminate()
                try:
                    self._proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self._proc.kill()
            except Exception:
                pass
            self._proc = None
        self._ready = False
        self._started = False

    def get_stats(self) -> Dict[str, Any]:
        return {
            "generation": self._last_gen_stats,
            "model": {
                "path": self._model_path,
                "arch": self._get_arch(),
                "backend": "llama-server",
            },
            "page_cache": None,
        }

    def get_capabilities(self) -> dict:
        from ..server.capabilities import detect_capabilities
        arch = self._get_arch()
        name = str(self._metadata.get("general.name", ""))
        caps = detect_capabilities(arch=arch, name=name)
        caps.tools = True  # llama-server supports tool calling
        return caps.to_dict()

    def _get_arch(self) -> str:
        return str(self._metadata.get("general.architecture", "unknown"))

    @staticmethod
    def _summarize_messages(messages: List[dict]) -> str:
        last = ""
        for msg in messages:
            if msg.get("role") == "user" and msg.get("content"):
                last = msg["content"]
        if not last and messages:
            last = messages[-1].get("content") or ""
        return str(last)[:50] + ("..." if len(str(last)) > 50 else "")

    # ── Tool calling (P7.3) ─────────────────────────────────────────
    def _accumulate_tool_calls(self, tool_calls: List[dict]) -> None:
        """Accumulate streaming tool-call deltas into complete calls.

        OpenAI streaming sends tool_calls as incremental fragments:
          [{"index":0,"id":"call_x","function":{"name":"f","arguments":""}}]
          [{"index":0,"function":{"arguments":"{\"a\":"}}]
          [{"index":0,"function":{"arguments":"1}"}}]
        We merge fragments by index into ``self._tool_calls``.
        """
        if not hasattr(self, "_tool_calls"):
            self._tool_calls = []
        for frag in tool_calls:
            idx = frag.get("index", 0)
            while len(self._tool_calls) <= idx:
                self._tool_calls.append({"id": "", "type": "function", "function": {"name": "", "arguments": ""}})
            target = self._tool_calls[idx]
            if frag.get("id"):
                target["id"] = frag["id"]
            fn = frag.get("function") or {}
            if fn.get("name"):
                target["function"]["name"] = fn["name"]
            if fn.get("arguments"):
                target["function"]["arguments"] += fn["arguments"]

    @property
    def tool_calls(self) -> List[dict]:
        """Completed tool calls from the last generation (P7.3)."""
        return list(getattr(self, "_tool_calls", []))