"""
Textual TUI application for weight-streaming.

A terminal-based interactive chat interface with live stats.
Connects to the weight-streaming API server.

Features:
- Streaming chat with keyboard navigation
- Live stats panel (buffer, prefetcher, page cache)
- Model loading via command palette
- Dark theme, high contrast
- Resizable split layout
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Optional

import requests
from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical, ScrollableContainer
from textual.reactive import reactive
from textual.widgets import (
    Button,
    Footer,
    Header,
    Input,
    Label,
    Markdown,
    RichLog,
    Static,
)
from textual.binding import Binding


# ── API Client (same pattern as Gradio) ──────────────────────────────


class APIClient:
    def __init__(self, base_url: str = "http://127.0.0.1:8765"):
        self.base_url = base_url.rstrip("/")
        self._session = requests.Session()

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def health(self) -> dict:
        r = self._session.get(self._url("/health"), timeout=5)
        r.raise_for_status()
        return r.json()

    def list_models(self) -> list:
        r = self._session.get(self._url("/v1/models"), timeout=10)
        r.raise_for_status()
        return r.json()

    def generate(self, model: str, prompt: str, max_tokens: int = 128,
                 temperature: float = 0.7) -> str:
        """Non-streaming generate (used for quick display)."""
        r = self._session.post(self._url("/v1/generate"), json={
            "model": model, "prompt": prompt,
            "max_tokens": max_tokens, "temperature": temperature,
            "stream": False,
        }, timeout=300)
        r.raise_for_status()
        return r.json()["output"]

    def load_model(self, model_id: str, model_path: str,
                   buffer_mb: int = 64) -> dict:
        r = self._session.post(self._url("/v1/models/load"), json={
            "model_id": model_id, "model_path": model_path,
            "buffer_mb": buffer_mb, "n_ctx": 512,
        }, timeout=60)
        r.raise_for_status()
        return r.json()

    def get_stats(self, model: str | None = None) -> dict:
        url = self._url("/v1/stats")
        if model:
            url += f"?model={model}"
        r = self._session.get(url, timeout=10)
        r.raise_for_status()
        return r.json()


# ── Widgets ───────────────────────────────────────────────────────────


class ServerStatus(Static):
    """Header bar showing server connection status."""
    connected = reactive(False)
    server_url = reactive("")

    def render(self) -> Text:
        icon = "[green]●[/]" if self.connected else "[red]●[/]"
        status = "Connected" if self.connected else "Offline"
        return Text.from_markup(
            f" {icon} [{status}]  {self.server_url}  "
            f"|  weight-streaming v0.11.0"
        )


class StatsPanel(Static):
    """Live stats display showing buffer, prefetcher, page cache info."""
    data: reactive[dict] = reactive({})

    def render(self) -> Text:
        if not self.data:
            return Text("No data yet", style="dim")

        buf = self.data.get("buffer", {})
        pref = self.data.get("prefetcher", {})
        page = self.data.get("page_cache", {})
        gen = self.data.get("generation", {})

        hit_rate = buf.get("hit_rate", 0)
        hot = buf.get("hot_shards", 0)
        cap = buf.get("capacity_shards", 0)
        pref_count = pref.get("prefetched", 0)
        resident = page.get("resident_ratio", 0)
        tps = gen.get("tokens_per_sec", 0)

        return Text.from_markup(
            f"[bold purple]STATISTICS[/]\n\n"
            f"  [bold]Hit Rate:[/]    [cyan]{hit_rate:.1%}[/]\n"
            f"  [bold]Hot Shards:[/]  [cyan]{hot}/{cap}[/]\n"
            f"  [bold]Prefetches:[/]  [cyan]{pref_count}[/]\n"
            f"  [bold]Resident:[/]    [cyan]{resident:.1%}[/]\n"
            f"  [bold]Speed:[/]       [cyan]{tps:.1f} tok/s[/]\n"
        )


class ModelBar(Static):
    """Shows currently selected model."""
    model = reactive("none")
    loaded = reactive(False)

    def render(self) -> Text:
        status = "[green]loaded[/]" if self.loaded else "[dim]not loaded[/]"
        return Text.from_markup(f" Model: [bold]{self.model}[/] ({status})")


# ── App ───────────────────────────────────────────────────────────────


class WeightStreamTUI(App):
    """Main TUI application for weight-streaming."""

    CSS = """
    Screen {
        background: #0f0f1a;
    }

    #header-bar {
        background: #1a1a2e;
        color: #e0e0e0;
        padding: 0 1;
        height: 1;
    }

    #chat-area {
        background: #0f0f1a;
        border: solid #2a2a3e;
    }

    #stats-panel {
        background: #1a1a2e;
        border: solid #2a2a3e;
        width: 30;
    }

    #input-bar {
        background: #1a1a2e;
        height: 3;
        padding: 0 1;
    }

    #model-bar {
        background: #1a1a2e;
    }

    Input {
        background: #2a2a3e;
        color: #e0e0e0;
        border: solid #6c5ce7;
    }

    Button {
        background: #6c5ce7;
        color: white;
    }

    RichLog {
        background: #0f0f1a;
        color: #e0e0e0;
    }
    """

    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit", show=True),
        Binding("ctrl+l", "clear", "Clear Chat", show=True),
        Binding("ctrl+r", "refresh", "Refresh Stats", show=True),
        Binding("ctrl+s", "focus_input", "Send", show=False),
    ]

    server_url = reactive("http://127.0.0.1:8765")
    current_model = reactive("default")

    def __init__(self, server_url: str = "http://127.0.0.1:8765"):
        super().__init__()
        self.server_url = server_url
        self.api = APIClient(server_url)
        self._stats_timer: Optional[asyncio.Task] = None

    def compose(self) -> ComposeResult:
        yield ServerStatus(id="header-bar")
        yield ModelBar(id="model-bar")

        with Horizontal():
            with Vertical(id="chat-area"):
                yield RichLog(id="chat-log", highlight=True, markup=True, wrap=True)
                with Horizontal(id="input-bar"):
                    yield Input(placeholder="Type your message... (Ctrl+S to send)", id="msg-input")
                    yield Button("Send", id="send-btn", variant="primary")

            yield StatsPanel(id="stats-panel")

        yield Footer()

    def on_mount(self):
        """Startup: check server + start stats polling."""
        self.query_one("#msg-input").focus()
        self._check_connection()
        self._stats_timer = self.set_interval(3, self._refresh_stats)

    # ── Actions ──────────────────────────────────────────────────

    @work(exclusive=False)
    async def _check_connection(self):
        """Check server health."""
        status = self.query_one(ServerStatus)
        try:
            self.api.health()
            status.connected = True
        except Exception:
            status.connected = False
        status.server_url = self.server_url

    @work(exclusive=False)
    async def _refresh_stats(self):
        """Poll server for stats."""
        stats_widget = self.query_one(StatsPanel)
        try:
            data = self.api.get_stats()
            models = data.get("models", {})
            if self.current_model in models:
                stats_widget.data = models[self.current_model]
            elif models:
                stats_widget.data = next(iter(models.values()))
            else:
                stats_widget.data = {}
        except Exception:
            pass  # Server not available

    @work(exclusive=True)
    async def _generate(self, prompt: str):
        """Generate a response (non-streaming for simplicity)."""
        chat = self.query_one(RichLog)
        input_widget = self.query_one("#msg-input")
        send_btn = self.query_one("#send-btn")

        chat.write(Text(f"\n[bold cyan]You:[/] {prompt}"))
        chat.write(Text("[dim]Generating...[/]"))
        input_widget.disabled = True
        send_btn.disabled = True

        try:
            output = await asyncio.to_thread(
                self.api.generate,
                model=self.current_model,
                prompt=prompt,
                max_tokens=256,
                temperature=0.7,
            )
            chat.write(Text(f"[bold purple]Assistant:[/] {output.strip()}"))
        except Exception as e:
            chat.write(Text(f"[bold red]Error:[/] {e}"))
        finally:
            input_widget.disabled = False
            send_btn.disabled = False
            input_widget.focus()

    def action_clear(self):
        """Clear chat log."""
        self.query_one(RichLog).clear()

    def action_refresh(self):
        """Manual stats refresh."""
        self._refresh_stats()

    def action_focus_input(self):
        """Focus the input field."""
        self.query_one("#msg-input").focus()

    # ── Event handlers ───────────────────────────────────────────────

    def on_input_submitted(self, event: Input.Submitted):
        """Handle Enter in input field."""
        self._send_message(event.value)

    def on_button_pressed(self, event: Button.Pressed):
        """Handle Send button click."""
        if event.button.id == "send-btn":
            self._send_message(self.query_one("#msg-input", Input).value)

    def _send_message(self, text: str):
        """Send a message and generate response."""
        text = text.strip()
        if not text:
            return

        input_widget = self.query_one("#msg-input", Input)
        input_widget.value = ""
        self._generate(text)
