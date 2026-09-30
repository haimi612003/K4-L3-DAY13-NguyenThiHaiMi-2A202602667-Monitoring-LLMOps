from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from scripts.dashboard import aggregate, read_events, render
from scripts.validate_dashboard import load_dashboard_config

REPO_ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 9, 30, 3, 0, 30, tzinfo=timezone.utc)


def _write(path: Path, events: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8")


def _sent(ts: str, latency: int, tool_success: bool = True) -> dict:
    return {"ts": ts, "event": "response_sent", "latency_ms": latency, "ttft_ms": 50,
            "tokens_in": 40, "tokens_out": 100, "cost_usd": 0.002, "quality_score": 0.8,
            "tool_name": "retrieval", "tool_success": tool_success}


def test_aggregate_matches_dashboard_contract(tmp_path: Path) -> None:
    log = tmp_path / "logs.jsonl"
    _write(log, [
        {"ts": "2026-09-30T01:00:00Z", "event": "request_received"},  # ngoài cửa sổ 60 phút
        {"ts": "2026-09-30T02:59:10Z", "event": "request_received"},
        {"ts": "2026-09-30T02:59:20Z", "event": "request_received"},
        _sent("2026-09-30T02:59:11Z", 200),
        {"ts": "2026-09-30T02:59:21Z", "event": "request_failed", "error_type": "RuntimeError",
         "tool_name": "retrieval", "tool_success": False},
        {"ts": "2026-09-30T03:00:05Z", "event": "request_received"},
        _sent("2026-09-30T03:00:06Z", 2600),
    ])

    data = aggregate(read_events(log), NOW, 60)

    assert data["traffic"]["summary"]["count"] == 3
    assert data["traffic"]["rate_per_minute"][-2:] == [2, 1]
    assert data["errors"]["summary"]["error_rate_pct"] == 33.33
    assert data["errors"]["summary"]["tool_success_rate_pct"] == 66.67
    assert data["errors"]["summary"]["count_by_value"] == {"RuntimeError": 1}
    assert data["latency"]["summary"]["p99"] == 2600
    assert data["tokens"]["summary"] == {"tokens_in": 80, "tokens_out": 200}
    assert data["cost"]["summary"]["total"] == 0.004
    assert data["quality"]["summary"]["mean"] == 0.8


def test_render_uses_contract_title_and_refresh(tmp_path: Path) -> None:
    config = load_dashboard_config(REPO_ROOT / "config" / "dashboard.yaml")
    page = render(config, tmp_path / "missing.jsonl", NOW)
    assert config["dashboard"]["title"] in page
    assert f'content="{config["dashboard"]["refresh_seconds"]}"' in page
