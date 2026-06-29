from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any


BASE_DIR = Path(__file__).resolve().parent / "data"
STATE_PATH = BASE_DIR / "state.json"
AUDIT_LOG_PATH = BASE_DIR / "audit_log.jsonl"

_lock = Lock()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def ensure_storage() -> None:
    BASE_DIR.mkdir(parents=True, exist_ok=True)
    if not STATE_PATH.exists():
        with STATE_PATH.open("w", encoding="utf-8") as handle:
            json.dump({"submissions": {}, "appeals": {}}, handle, indent=2, sort_keys=True)
    if not AUDIT_LOG_PATH.exists():
        AUDIT_LOG_PATH.touch()


def load_state() -> dict[str, Any]:
    ensure_storage()
    with _lock:
        with STATE_PATH.open("r", encoding="utf-8") as handle:
            return json.load(handle)


def save_state(state: dict[str, Any]) -> None:
    ensure_storage()
    with _lock:
        with tempfile.NamedTemporaryFile("w", delete=False, dir=BASE_DIR, encoding="utf-8") as handle:
            json.dump(state, handle, indent=2, sort_keys=True)
            temp_path = handle.name
        os.replace(temp_path, STATE_PATH)


def append_audit_entry(entry: dict[str, Any]) -> None:
    ensure_storage()
    with _lock:
        with AUDIT_LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, sort_keys=True) + "\n")


def get_audit_entries(limit: int | None = None) -> list[dict[str, Any]]:
    ensure_storage()
    entries: list[dict[str, Any]] = []
    with AUDIT_LOG_PATH.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            entries.append(json.loads(line))
    if limit is not None:
        return entries[-limit:]
    return entries


def store_submission(record: dict[str, Any]) -> None:
    state = load_state()
    state.setdefault("submissions", {})[record["content_id"]] = record
    save_state(state)


def get_submission(content_id: str) -> dict[str, Any] | None:
    state = load_state()
    return state.get("submissions", {}).get(content_id)


def update_submission(content_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
    state = load_state()
    submissions = state.setdefault("submissions", {})
    existing = submissions.get(content_id)
    if existing is None:
        return None
    existing.update(updates)
    save_state(state)
    return existing


def store_appeal(record: dict[str, Any]) -> None:
    state = load_state()
    state.setdefault("appeals", {})[record["appeal_id"]] = record
    save_state(state)


def get_appeal_entries(limit: int | None = None) -> list[dict[str, Any]]:
    state = load_state()
    appeals = list(state.get("appeals", {}).values())
    appeals.sort(key=lambda item: item.get("timestamp", ""))
    if limit is not None:
        return appeals[-limit:]
    return appeals
