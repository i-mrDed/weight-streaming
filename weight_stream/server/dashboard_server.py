"""Live Streaming Dashboard Server.

Provides real-time visualization of Weight Streaming metrics:
- NVMe I/O Throughput (MB/s)
- Buffer Hit/Miss Rate (%)
- Memory Residency Ratio (QueryWorkingSetEx)
- Active Expert Heatmap
"""

import http.server
import socketserver
import json
import time
from typing import Dict, Any

METRICS_CACHE: Dict[str, Any] = {
    "timestamp": time.time(),
    "buffer": {"hit_rate": 0.85, "hits": 850, "misses": 150, "capacity_mb": 256, "used_mb": 192},
    "io": {"read_speed_mbps": 4200.0, "latency_ms": 4.2},
    "page_cache": {"working_set_mb": 12400.0, "resident_ratio": 0.94},
    "active_experts": [12, 45, 67, 88, 102, 145, 201, 310]
}

def update_metrics(new_data: Dict[str, Any]):
    global METRICS_CACHE
    METRICS_CACHE.update(new_data)
    METRICS_CACHE["timestamp"] = time.time()

HTML_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
    <title>Weight Streaming Live Dashboard</title>
    <meta http-equiv="refresh" content="2">
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0f172a; color: #f8fafc; margin: 0; padding: 24px; }
        h1 { color: #38bdf8; border-bottom: 2px solid #334155; padding-bottom: 12px; }
        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 20px; margin-top: 20px; }
        .card { background: #1e293b; border-radius: 12px; padding: 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.3); border: 1px solid #334155; }
        .card h3 { margin-top: 0; color: #94a3b8; font-size: 14px; text-transform: uppercase; }
        .value { font-size: 32px; font-weight: bold; color: #38bdf8; margin: 8px 0; }
        .subtext { font-size: 13px; color: #64748b; }
        .tag { display: inline-block; background: #0284c7; color: #fff; padding: 4px 10px; border-radius: 99px; font-size: 12px; margin: 2px; }
    </style>
</head>
<body>
    <h1>🚀 Weight-Streaming Live Dashboard</h1>
    <div class="grid">
        <div class="card">
            <h3>Buffer Hit Rate</h3>
            <div class="value">__HIT_RATE__%</div>
            <div class="subtext">Hits: __HITS__ | Misses: __MISSES__</div>
        </div>
        <div class="card">
            <h3>NVMe Read Bandwidth</h3>
            <div class="value">__IO_SPEED__ MB/s</div>
            <div class="subtext">Latency: __IO_LATENCY__ ms</div>
        </div>
        <div class="card">
            <h3>RAM Page Cache Residency</h3>
            <div class="value">__RESIDENT_RATIO__%</div>
            <div class="subtext">Working Set: __WORKING_SET__ MB</div>
        </div>
        <div class="card">
            <h3>Active Experts (Top-K)</h3>
            <div style="margin-top: 12px;">__EXPERTS_TAGS__</div>
        </div>
    </div>
</body>
</html>
"""

class DashboardRequestHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/api/metrics":
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(METRICS_CACHE).encode())
        else:
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            
            b_stats = METRICS_CACHE["buffer"]
            io_stats = METRICS_CACHE["io"]
            pc_stats = METRICS_CACHE["page_cache"]
            exp_list = METRICS_CACHE["active_experts"]

            html = HTML_TEMPLATE.replace("__HIT_RATE__", f"{b_stats['hit_rate']*100:.1f}")
            html = html.replace("__HITS__", str(b_stats["hits"]))
            html = html.replace("__MISSES__", str(b_stats["misses"]))
            html = html.replace("__IO_SPEED__", f"{io_stats['read_speed_mbps']:.1f}")
            html = html.replace("__IO_LATENCY__", f"{io_stats['latency_ms']:.1f}")
            html = html.replace("__RESIDENT_RATIO__", f"{pc_stats['resident_ratio']*100:.1f}")
            html = html.replace("__WORKING_SET__", f"{pc_stats['working_set_mb']:.1f}")
            
            tags = "".join([f'<span class="tag">Expert #{e}</span>' for e in exp_list])
            html = html.replace("__EXPERTS_TAGS__", tags)

            self.wfile.write(html.encode())

def run_dashboard_server(port: int = 8766):
    handler = DashboardRequestHandler
    with socketserver.TCPServer(("", port), handler) as httpd:
        print(f"Serving Weight Streaming Live Dashboard at http://localhost:{port}")
        httpd.serve_forever()

if __name__ == "__main__":
    run_dashboard_server(8766)
