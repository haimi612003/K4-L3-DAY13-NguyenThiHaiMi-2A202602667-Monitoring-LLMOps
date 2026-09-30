"""Dashboard runtime 6 panel đọc trực tiếp từ data/logs.jsonl.

Chạy: python scripts/dashboard.py  rồi mở http://127.0.0.1:8050
Time range, refresh, đơn vị và threshold lấy từ config/dashboard.yaml (contract chấm điểm).
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from statistics import mean
from zoneinfo import ZoneInfo

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.cli import configure_utf8_stdio
from app.metrics import percentile
from scripts.validate_dashboard import load_dashboard_config

LOCAL_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


def read_events(log_path: Path) -> list[dict]:
    if not log_path.exists():
        return []
    events = []
    for line in log_path.read_text(encoding="utf-8").splitlines():
        try:
            event = json.loads(line)
            event["_ts"] = datetime.fromisoformat(event["ts"].replace("Z", "+00:00"))
        except (json.JSONDecodeError, KeyError, ValueError):
            continue
        events.append(event)
    return events


def _pct(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator * 100, 2) if denominator else None


def aggregate(events: list[dict], now: datetime, minutes: int) -> dict:
    """Tính giá trị theo từng phút và cho cả cửa sổ, đúng logic trong dashboard.yaml."""
    start = (now - timedelta(minutes=minutes - 1)).replace(second=0, microsecond=0)
    buckets = [start + timedelta(minutes=i) for i in range(minutes)]
    in_window = [e for e in events if start <= e["_ts"] <= now]

    def by_minute(event_name: str) -> list[list[dict]]:
        grouped: list[list[dict]] = [[] for _ in buckets]
        for e in in_window:
            if e.get("event") == event_name:
                idx = int((e["_ts"] - start).total_seconds() // 60)
                if 0 <= idx < minutes:
                    grouped[idx].append(e)
        return grouped

    sent = by_minute("response_sent")
    received = by_minute("request_received")
    failed = by_minute("request_failed")

    def series(groups: list[list[dict]], fn) -> list[float | None]:
        return [fn(g) if g else None for g in groups]

    def tool_events(i: int) -> list[dict]:
        return [e for e in sent[i] + failed[i] if e.get("tool_success") is not None]

    all_sent = [e for g in sent for e in g]
    all_failed = [e for g in failed for e in g]
    all_received = [e for g in received for e in g]
    all_tool = [e for e in all_sent + all_failed if e.get("tool_success") is not None]
    latencies = [e["latency_ms"] for e in all_sent]
    ttfts = [e["ttft_ms"] for e in all_sent]

    return {
        "labels": [b.astimezone(LOCAL_TZ).strftime("%H:%M") for b in buckets],
        "window": {
            "start": start.astimezone(LOCAL_TZ).strftime("%Y-%m-%d %H:%M"),
            "end": now.astimezone(LOCAL_TZ).strftime("%Y-%m-%d %H:%M:%S"),
        },
        "latency": {
            "p50": series(sent, lambda g: percentile([e["latency_ms"] for e in g], 50)),
            "p95": series(sent, lambda g: percentile([e["latency_ms"] for e in g], 95)),
            "p99": series(sent, lambda g: percentile([e["latency_ms"] for e in g], 99)),
            "ttft_p95": series(sent, lambda g: percentile([e["ttft_ms"] for e in g], 95)),
            "summary": {
                "p50": percentile(latencies, 50),
                "p95": percentile(latencies, 95),
                "p99": percentile(latencies, 99),
                "ttft_p95": percentile(ttfts, 95),
            },
        },
        "traffic": {
            "rate_per_minute": [len(g) for g in received],
            "summary": {"count": len(all_received)},
        },
        "errors": {
            "error_rate_pct": [
                _pct(len(failed[i]), len(received[i])) if received[i] else None
                for i in range(minutes)
            ],
            "tool_success_rate_pct": [
                _pct(sum(e["tool_success"] is True for e in tool_events(i)), len(tool_events(i)))
                for i in range(minutes)
            ],
            "summary": {
                "error_rate_pct": _pct(len(all_failed), len(all_received)) or 0.0,
                "tool_success_rate_pct": _pct(
                    sum(e["tool_success"] is True for e in all_tool), len(all_tool)
                ),
                "count_by_value": dict(Counter(e.get("error_type") for e in all_failed)),
            },
        },
        "cost": {
            "sum_by_minute": series(sent, lambda g: round(sum(e["cost_usd"] for e in g), 6)),
            "summary": {"total": round(sum(e["cost_usd"] for e in all_sent), 6)},
        },
        "tokens": {
            "tokens_in": series(sent, lambda g: sum(e["tokens_in"] for e in g)),
            "tokens_out": series(sent, lambda g: sum(e["tokens_out"] for e in g)),
            "summary": {
                "tokens_in": sum(e["tokens_in"] for e in all_sent),
                "tokens_out": sum(e["tokens_out"] for e in all_sent),
            },
        },
        "quality": {
            "mean": series(sent, lambda g: round(mean(e["quality_score"] for e in g), 3)),
            "summary": {
                "mean": round(mean(e["quality_score"] for e in all_sent), 3) if all_sent else None
            },
        },
    }


PAGE = """<!doctype html>
<html lang="vi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="__REFRESH__">
<title>__TITLE__</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>
  :root { --bg:#f6f7f9; --card:#fff; --ink:#1d2330; --muted:#5f6b7a; --line:#e3e6ea; --bad:#c62828; --ok:#2e7d32; }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--ink); font:14px/1.45 -apple-system,Segoe UI,Roboto,sans-serif; }
  header { padding:16px 24px; border-bottom:1px solid var(--line); background:var(--card); display:flex; flex-wrap:wrap; gap:8px 24px; align-items:baseline; }
  h1 { font-size:18px; margin:0; }
  .meta { color:var(--muted); font-size:13px; }
  main { display:grid; grid-template-columns:repeat(auto-fit,minmax(420px,1fr)); gap:16px; padding:16px 24px; }
  section { background:var(--card); border:1px solid var(--line); border-radius:8px; padding:14px 16px; min-width:0; }
  h2 { font-size:15px; margin:0 0 2px; }
  .sub { color:var(--muted); font-size:12px; margin-bottom:8px; }
  .stats { display:flex; flex-wrap:wrap; gap:6px 18px; margin-bottom:8px; font-variant-numeric:tabular-nums; }
  .stats b { font-size:16px; }
  .bad { color:var(--bad); } .ok { color:var(--ok); }
  canvas { width:100% !important; height:220px !important; }
  @media (max-width:520px) { main { grid-template-columns:1fr; padding:12px; } header { padding:12px; } }
</style></head><body>
<header><h1>__TITLE__</h1>
<span class="meta">Time range: last __MINUTES__ min (__START__ → __END__, Asia/Ho_Chi_Minh)</span>
<span class="meta">Auto-refresh: __REFRESH__s · Source: data/logs.jsonl</span></header>
<main id="panels"></main>
<script>
const D = __DATA__;
const P = __PANELS__;
const C = {p50:"#1e88e5", p95:"#fb8c00", p99:"#8e24aa", ttft:"#00897b", thr:"#c62828", a:"#3949ab", b:"#43a047"};
const fmt = (v, d=2) => v === null || v === undefined ? "–" : Number(v).toLocaleString("en-US", {maximumFractionDigits:d});
function thrLine(value) { return {label:"threshold", data:D.labels.map(()=>value), borderColor:C.thr, borderDash:[6,4], pointRadius:0, borderWidth:1.5, fill:false}; }
function line(label, data, color) { return {label, data, borderColor:color, backgroundColor:color, spanGaps:true, pointRadius:2, borderWidth:2, tension:.2}; }
function bar(label, data, color) { return {type:"bar", label, data, backgroundColor:color}; }
function passes(p, value) { if (value === null || value === undefined) return null; return p.threshold.operator === "lte" ? value <= p.threshold.value : value >= p.threshold.value; }
function stat(label, value, unit, p) {
  const ok = p ? passes(p, value) : null;
  const cls = ok === null ? "" : ok ? "ok" : "bad";
  return `<span>${label}: <b class="${cls}">${fmt(value, 4)}</b> ${unit}</span>`;
}
function panel(id, stats, datasets, yTitle, extra="") {
  const p = P[id];
  const el = document.createElement("section");
  el.innerHTML = `<h2>${p.title}</h2><div class="sub">unit: ${p.unit} · threshold: ${p.threshold.aggregation} ${p.threshold.operator === "lte" ? "≤" : "≥"} ${p.threshold.value}</div><div class="stats">${stats}</div>${extra}<canvas></canvas>`;
  document.getElementById("panels").appendChild(el);
  new Chart(el.querySelector("canvas"), {type:"line", data:{labels:D.labels, datasets},
    options:{animation:false, maintainAspectRatio:false, interaction:{mode:"index", intersect:false},
      scales:{y:{beginAtZero:true, title:{display:true, text:yTitle}}, x:{ticks:{maxTicksLimit:12}}},
      plugins:{legend:{position:"bottom", labels:{boxWidth:12}}}}});
}
const L = D.latency.summary;
panel("latency",
  stat("P50", L.p50, "ms") + stat("P95", L.p95, "ms", P.latency) + stat("P99", L.p99, "ms") + stat("TTFT P95", L.ttft_p95, "ms"),
  [line("latency p50", D.latency.p50, C.p50), line("latency p95", D.latency.p95, C.p95), line("latency p99", D.latency.p99, C.p99), line("TTFT p95", D.latency.ttft_p95, C.ttft), thrLine(P.latency.threshold.value)], "ms");
panel("traffic", stat("Requests", D.traffic.summary.count, "req"),
  [bar("requests / minute", D.traffic.rate_per_minute, C.a), thrLine(P.traffic.threshold.value)], "requests / minute");
const E = D.errors.summary;
const breakdown = Object.entries(E.count_by_value).map(([k,v]) => `${k}: ${v}`).join(", ") || "none";
panel("errors",
  stat("Error rate", E.error_rate_pct, "%", P.errors) + stat("Retrieval success", E.tool_success_rate_pct, "%"),
  [line("error rate %", D.errors.error_rate_pct, C.thr), line("retrieval success %", D.errors.tool_success_rate_pct, C.b), thrLine(P.errors.threshold.value)], "percent",
  `<div class="sub">error breakdown: ${breakdown}</div>`);
panel("cost", stat("Total", D.cost.summary.total, "USD", P.cost),
  [bar("cost USD / minute", D.cost.sum_by_minute, C.a)], "USD",
  `<div class="sub">threshold applies to window total (${P.cost.threshold.value} USD)</div>`);
panel("tokens",
  stat("Input", D.tokens.summary.tokens_in, "tokens", P.tokens) + stat("Output", D.tokens.summary.tokens_out, "tokens", P.tokens),
  [bar("tokens_in / minute", D.tokens.tokens_in, C.a), bar("tokens_out / minute", D.tokens.tokens_out, C.b)], "tokens",
  `<div class="sub">threshold applies to each field's window sum (${P.tokens.threshold.value} tokens)</div>`);
panel("quality", stat("Mean", D.quality.summary.mean, "score", P.quality),
  [line("quality mean", D.quality.mean, C.a), thrLine(P.quality.threshold.value)], "score 0–1");
</script></body></html>"""


def render(config: dict, log_path: Path, now: datetime | None = None) -> str:
    dashboard = config["dashboard"]
    minutes = dashboard["time_range_minutes"]
    data = aggregate(read_events(log_path), now or datetime.now(timezone.utc), minutes)
    panels = {p["id"]: p for p in dashboard["panels"]}
    replacements = {
        "__TITLE__": dashboard["title"],
        "__REFRESH__": str(dashboard["refresh_seconds"]),
        "__MINUTES__": str(minutes),
        "__START__": data["window"]["start"],
        "__END__": data["window"]["end"],
        "__DATA__": json.dumps(data),
        "__PANELS__": json.dumps(panels),
    }
    page = PAGE
    for key, value in replacements.items():
        page = page.replace(key, value)
    return page


def main() -> None:
    configure_utf8_stdio()
    parser = argparse.ArgumentParser(description="Dashboard 6 panel từ data/logs.jsonl")
    parser.add_argument("--port", type=int, default=8050)
    parser.add_argument("--log", type=Path, default=REPO_ROOT / "data" / "logs.jsonl")
    parser.add_argument("--config", type=Path, default=REPO_ROOT / "config" / "dashboard.yaml")
    args = parser.parse_args()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path.split("?")[0] not in ("/", "/index.html"):
                self.send_error(404)
                return
            # Đọc lại config và log mỗi lần refresh để dashboard phản ánh dữ liệu mới nhất.
            body = render(load_dashboard_config(args.config), args.log).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args) -> None:
            return None

    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"Dashboard: http://127.0.0.1:{args.port}  (Ctrl+C để dừng)")
    server.serve_forever()


if __name__ == "__main__":
    main()
