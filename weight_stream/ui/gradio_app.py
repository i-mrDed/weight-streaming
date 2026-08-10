"""
Gradio Web UI for weight-streaming.

Provides an interactive chat interface that connects to the
weight-streaming API server. Features:
- Streaming chat with stop button
- Model management (load/unload/switch)
- Live stats panel (buffer, prefetcher, page cache)
- Settings (temperature, max tokens, buffer size)

Usage:
    python -m weight_stream ui
    python -m weight_stream ui --server http://localhost:8080
"""

from __future__ import annotations

import json
import time
import requests
from typing import Generator

import gradio as gr

# ── Theme ────────────────────────────────────────────────────────────

theme = gr.themes.Soft(
    primary_hue="purple",
    secondary_hue="teal",
    neutral_hue="slate",
    font=gr.themes.GoogleFont("Inter"),
).set(
    body_background_fill="*neutral_950",
    body_background_fill_dark="*neutral_950",
    block_background_fill="*neutral_900",
    block_background_fill_dark="*neutral_900",
    block_border_color="*neutral_800",
    block_title_text_color="*primary_300",
    input_background_fill="*neutral_800",
    button_primary_background_fill="*primary_500",
    button_primary_text_color="white",
)


# ── API Client ───────────────────────────────────────────────────────


class APIClient:
    """Thin HTTP client for the weight-streaming API server."""

    def __init__(self, base_url: str = "http://127.0.0.1:8765"):
        self.base_url = base_url.rstrip("/")

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def health(self) -> dict:
        r = requests.get(self._url("/health"), timeout=5)
        r.raise_for_status()
        return r.json()

    def list_models(self) -> list[dict]:
        r = requests.get(self._url("/v1/models"), timeout=10)
        r.raise_for_status()
        return r.json()

    def load_model(self, model_id: str, model_path: str,
                   buffer_mb: int = 64, n_ctx: int = 512) -> dict:
        r = requests.post(self._url("/v1/models/load"), json={
            "model_id": model_id, "model_path": model_path,
            "buffer_mb": buffer_mb, "n_ctx": n_ctx,
        }, timeout=60)
        r.raise_for_status()
        return r.json()

    def unload_model(self, model_id: str) -> dict:
        r = requests.post(self._url("/v1/models/unload"), json={
            "model_id": model_id,
        }, timeout=30)
        r.raise_for_status()
        return r.json()

    def generate(self, model: str, prompt: str, max_tokens: int = 128,
                 temperature: float = 0.7, stream: bool = True) -> Generator:
        """Stream generation via SSE."""
        r = requests.post(self._url("/v1/generate"), json={
            "model": model, "prompt": prompt,
            "max_tokens": max_tokens, "temperature": temperature,
            "stream": stream,
        }, timeout=300, stream=stream)

        if not stream:
            r.raise_for_status()
            data = r.json()
            yield data["output"]
            return

        r.raise_for_status()
        for line in r.iter_lines():
            if line and line.startswith(b"data: "):
                event = json.loads(line[6:])
                if event.get("done"):
                    break
                if event.get("token"):
                    yield event["token"]

    def get_stats(self, model: str | None = None) -> dict:
        url = self._url("/v1/stats")
        if model:
            url += f"?model={model}"
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        return r.json()


# ── UI Components ────────────────────────────────────────────────────


def create_app(server_url: str = "http://127.0.0.1:8765") -> gr.Blocks:
    """Create the Gradio Web UI application."""
    api = APIClient(server_url)

    # Server check
    try:
        api.health()
        server_ok = True
    except Exception:
        server_ok = False

    with gr.Blocks(
        title="Weight Streaming",
    ) as app:
        # State
        current_model = gr.State("default")
        model_list = gr.State([])

        # ── Header ────────────────────────────────────────────────
        gr.HTML("""
        <div style="text-align:center; padding:8px 0;">
            <h1 style="margin:0; font-size:1.6em; background:linear-gradient(135deg, #6C5CE7, #00CEC9); 
                       -webkit-background-clip:text; -webkit-text-fill-color:transparent;">
                Weight Streaming
            </h1>
            <p style="margin:4px 0 0; opacity:0.6; font-size:0.85em;">
                Run LLMs larger than your RAM
            </p>
        </div>
        """)

        # ── Server status bar ─────────────────────────────────────
        server_indicator = gr.HTML(
            '<div style="text-align:center; padding:4px; background:#1A3A1A; border-radius:6px; '
            f'color:#4ADE80;">Server connected: {server_url}</div>'
            if server_ok else
            '<div style="text-align:center; padding:4px; background:#3A1A1A; border-radius:6px; '
            f'color:#EF4444;">Server offline: {server_url}</div>'
        )

        with gr.Row():
            # ── Left: Chat Column ───────────────────────────────
            with gr.Column(scale=3):
                chatbot = gr.Chatbot(
                    label="Chat",
                    height=480,
                    placeholder="Load a model and start chatting...",
                )
                with gr.Row():
                    msg = gr.Textbox(
                        label="Message",
                        placeholder="Type your message...",
                        scale=8,
                        show_label=False,
                    )
                    send = gr.Button("Send", variant="primary", scale=1)
                with gr.Row():
                    stop_btn = gr.Button("Stop", variant="stop", size="sm")
                    clear_btn = gr.Button("Clear", size="sm")

            # ── Right: Controls Column ──────────────────────────
            with gr.Column(scale=1):
                gr.Markdown("### Model")
                model_dropdown = gr.Dropdown(
                    label="Select model",
                    choices=[],
                    value=None,
                    interactive=True,
                )
                load_status = gr.Textbox(
                    label="", show_label=False, container=False,
                    interactive=False, lines=1,
                    visible=not server_ok,
                )

                with gr.Accordion("Load Model", open=True if server_ok else False):
                    model_path_input = gr.Textbox(
                        label="Model Path",
                        placeholder="path/to/model.gguf",
                    )
                    model_id_input = gr.Textbox(
                        label="Model ID", value="default",
                    )
                    buffer_mb_input = gr.Slider(
                        label="Buffer (MB)", minimum=8, maximum=512,
                        value=64, step=8,
                    )
                    n_ctx_input = gr.Slider(
                        label="Context Window", minimum=64, maximum=8192,
                        value=512, step=64,
                    )
                    load_btn = gr.Button("Load Model", variant="secondary")

                with gr.Accordion("Settings", open=False):
                    temperature_slider = gr.Slider(
                        label="Temperature", minimum=0.0, maximum=2.0,
                        value=0.7, step=0.05,
                    )
                    max_tokens_slider = gr.Slider(
                        label="Max Tokens", minimum=8, maximum=4096,
                        value=256, step=8,
                    )

                # ── Stats Panel ──────────────────────────────
                with gr.Accordion("Statistics", open=False):
                    stats_html = gr.HTML("No data yet")
                    refresh_stats_btn = gr.Button("Refresh", size="sm")

        # ── Functions ───────────────────────────────────────────

        def update_model_dropdown():
            """Fetch loaded models and update dropdown."""
            try:
                models = api.list_models()
                choices = [m["id"] for m in models]
                return gr.Dropdown(choices=choices)
            except Exception:
                return gr.Dropdown(choices=[])

        def load_model_fn(model_path, model_id, buffer_mb, n_ctx):
            """Load a model via API."""
            if not model_path:
                return "Please enter a model path", update_model_dropdown()
            try:
                result = api.load_model(
                    model_id=model_id,
                    model_path=model_path,
                    buffer_mb=int(buffer_mb),
                    n_ctx=int(n_ctx),
                )
                return f"Loaded: {model_id}", update_model_dropdown()
            except Exception as e:
                return f"Error: {e}", update_model_dropdown()

        def generate_fn(message, history, model, temperature, max_tokens):
            """Generate a response (streaming)."""
            if not message.strip():
                yield history, ""
                return
            try:
                history = history or []
                history.append({"role": "user", "content": message})

                full_response = ""
                for token in api.generate(
                    model=model,
                    prompt=message,
                    max_tokens=int(max_tokens),
                    temperature=float(temperature),
                    stream=True,
                ):
                    full_response += token
                    # Yield intermediate state for streaming
                    interim = list(history)
                    interim.append({"role": "assistant", "content": full_response})
                    yield interim, ""
                yield interim, ""
            except Exception as e:
                error_msg = f"Error: {e}"
                history.append({"role": "assistant", "content": error_msg})
                yield history, ""

        def refresh_stats():
            """Fetch and format stats."""
            try:
                data = api.get_stats()
                models = data.get("models", {})
                html = ""
                for mid, ms in models.items():
                    # LlamaServerBackend (GPU) sends buffer/prefetcher/page_cache
                    # as None — render honest "n/a" instead of fake zeros.
                    buf_na = ms.get("buffer") is None
                    pref_na = ms.get("prefetcher") is None
                    page_na = ms.get("page_cache") is None
                    buf = ms.get("buffer") or {}
                    pref = ms.get("prefetcher") or {}
                    page = ms.get("page_cache") or {}
                    gen = ms.get("generation", {})

                    hit = 'n/a' if buf_na else f"{buf.get('hit_rate', 0):.1%}"
                    shards = 'n/a' if buf_na else f"{buf.get('hot_shards', 0)}/{buf.get('capacity_shards', 0)}"
                    prefs = 'n/a' if pref_na else f"{pref.get('prefetched', 0)}"
                    resident = 'n/a' if page_na else f"{page.get('resident_ratio', 0):.1%}"

                    html += f"""
                    <div class="stats-card">
                        <b style="color:#A78BFA;">{mid}</b>
                        <div style="display:grid; grid-template-columns:1fr 1fr; gap:6px; margin-top:6px;">
                            <div><span class="stat-label">Hit Rate</span><br>
                                <span class="stat-value">{hit}</span></div>
                            <div><span class="stat-label">Hot Shards</span><br>
                                <span class="stat-value">{shards}</span></div>
                            <div><span class="stat-label">Prefetches</span><br>
                                <span class="stat-value">{prefs}</span></div>
                            <div><span class="stat-label">Resident</span><br>
                                <span class="stat-value">{resident}</span></div>
                            <div><span class="stat-label">Speed</span><br>
                                <span class="stat-value">{gen.get('tokens_per_sec', 0):.1f} tok/s</span></div>
                            <div><span class="stat-label">Tokens</span><br>
                                <span class="stat-value">{gen.get('token_count', 0)}</span></div>
                        </div>
                    </div>"""
                if not html:
                    html = "<p style='opacity:0.5;'>No models loaded</p>"
                return html
            except Exception as e:
                return f"<p style='color:red;'>Error loading stats: {e}</p>"

        # ── Event Bindings ──────────────────────────────────────

        load_btn.click(
            fn=load_model_fn,
            inputs=[model_path_input, model_id_input, buffer_mb_input, n_ctx_input],
            outputs=[load_status, model_dropdown],
        )

        send.click(
            fn=generate_fn,
            inputs=[msg, chatbot, current_model, temperature_slider, max_tokens_slider],
            outputs=[chatbot, msg],
        ).then(
            fn=lambda: "", outputs=[msg],
        )

        msg.submit(
            fn=generate_fn,
            inputs=[msg, chatbot, current_model, temperature_slider, max_tokens_slider],
            outputs=[chatbot, msg],
        ).then(
            fn=lambda: "", outputs=[msg],
        )

        clear_btn.click(fn=lambda: ([], ""), outputs=[chatbot, msg])

        model_dropdown.change(
            fn=lambda x: x,
            inputs=[model_dropdown],
            outputs=[current_model],
        )

        refresh_stats_btn.click(
            fn=refresh_stats,
            outputs=[stats_html],
        )

        # Initial refresh
        app.load(
            fn=update_model_dropdown,
            outputs=[model_dropdown],
        )

    return app


def launch(server_url: str = "http://127.0.0.1:8765",
           share: bool = False, **kwargs):
    """Launch the Gradio Web UI."""
    app = create_app(server_url)
    app.queue(default_concurrency_limit=3)
    
    # CSS styling (Gradio 6.x: pass to launch())
    css = """
    .stats-card {
        padding: 12px 16px;
        border-radius: 8px;
        background: var(--block-background-fill);
        border: 1px solid var(--block-border-color);
        margin-bottom: 8px;
    }
    .stat-value {
        font-size: 1.3em;
        font-weight: 700;
        color: var(--primary-400);
    }
    .stat-label {
        font-size: 0.8em;
        color: var(--body-text-color-subdued);
    }
    footer { display: none !important; }
    """
    
    app.launch(
        server_name="127.0.0.1",
        server_port=7860,
        share=share,
        show_error=True,
        theme=theme,
        css=css,
        **kwargs,
    )
