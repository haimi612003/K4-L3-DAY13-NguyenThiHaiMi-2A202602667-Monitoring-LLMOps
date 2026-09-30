from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

import httpx
import structlog

from app import logging_config
from app.main import app
from app.middleware import resolve_correlation_id


def _post_chat(headers: dict[str, str] | None = None, message: str = "Explain traces") -> list[httpx.Response]:
    async def send() -> list[httpx.Response]:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            first = await client.post(
                "/chat",
                headers=headers or {},
                json={"user_id": "student-01", "session_id": "s-01", "feature": "qa", "message": message},
            )
            second = await client.post(
                "/chat",
                json={"user_id": "student-02", "session_id": "s-02", "feature": "summary", "message": "Hello"},
            )
            return [first, second]

    return asyncio.run(send())


def _read_log(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_generated_correlation_id_format() -> None:
    assert re.fullmatch(r"req-[0-9a-f]{8}", resolve_correlation_id(None))


def test_unsafe_request_id_header_is_replaced() -> None:
    assert re.fullmatch(r"req-[0-9a-f]{8}", resolve_correlation_id("bad id\n{json}"))
    assert resolve_correlation_id("req-abcdef12") == "req-abcdef12"


def test_request_id_is_echoed_and_context_does_not_leak(monkeypatch, tmp_path: Path) -> None:
    log_path = tmp_path / "logs.jsonl"
    monkeypatch.setattr(logging_config, "LOG_PATH", log_path)

    first, second = _post_chat(headers={"x-request-id": "req-00c0ffee"})

    assert first.headers["x-request-id"] == "req-00c0ffee"
    assert first.json()["correlation_id"] == "req-00c0ffee"
    assert float(first.headers["x-response-time-ms"]) >= 0
    assert re.fullmatch(r"req-[0-9a-f]{8}", second.headers["x-request-id"])

    api_events = [e for e in _read_log(log_path) if e.get("service") == "api"]
    by_id: dict[str, list[dict]] = {}
    for event in api_events:
        by_id.setdefault(event["correlation_id"], []).append(event)

    assert set(by_id) == {"req-00c0ffee", second.headers["x-request-id"]}
    for event in by_id["req-00c0ffee"]:
        assert event["session_id"] == "s-01" and event["feature"] == "qa"
        assert {"user_id_hash", "model", "env"} <= event.keys()
    for event in by_id[second.headers["x-request-id"]]:
        assert event["session_id"] == "s-02" and event["feature"] == "summary"


def test_pii_is_scrubbed_before_log_is_written(monkeypatch, tmp_path: Path) -> None:
    log_path = tmp_path / "logs.jsonl"
    monkeypatch.setattr(logging_config, "LOG_PATH", log_path)

    _post_chat(message="Email a@b.com, phone 0987654321, card 4111 1111 1111 1111, CCCD 079203001234")

    raw = log_path.read_text(encoding="utf-8")
    for secret in ("a@b.com", "0987654321", "4111 1111 1111 1111", "079203001234"):
        assert secret not in raw
    assert "REDACTED_EMAIL" in raw and "REDACTED_CREDIT_CARD" in raw


def test_scrub_processor_runs_before_file_writer() -> None:
    processors = structlog.get_config()["processors"]
    names = [getattr(p, "__name__", type(p).__name__) for p in processors]
    assert names.index("scrub_event") < names.index("JsonlFileProcessor")
