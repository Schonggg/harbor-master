"""Persist organizer scoreboard responses. Never reads ground truth."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from harbormaster.config import _repo_root


SCORE_KEYS = ("category", "status", "review_reason", "has_defect", "defect_fields")


def reports_dir() -> Path:
    path = _repo_root() / "reports"
    path.mkdir(parents=True, exist_ok=True)
    return path


def history_dir() -> Path:
    path = reports_dir() / "official_scores"
    path.mkdir(parents=True, exist_ok=True)
    return path


def latest_path() -> Path:
    return reports_dir() / "official_score.json"


def organizer_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Strip ledger-only keys so /submit matches the sponsor sample shape."""
    out: dict[str, Any] = {}
    for eid, rec in payload.items():
        if not isinstance(rec, dict):
            continue
        out[str(eid)] = {k: rec.get(k) for k in SCORE_KEYS}
    return out


def persist_scoreboard(scoreboard: dict[str, Any], *, source: str = "submit") -> Path:
    recorded_at = datetime.now(timezone.utc).isoformat()
    record = {
        "recorded_at": recorded_at,
        "source": source,
        "scoreboard": scoreboard,
    }
    stamp = recorded_at.replace(":", "").replace("+", "Z")[:20]
    snap = history_dir() / f"{stamp}.json"
    snap.parent.mkdir(parents=True, exist_ok=True)
    snap.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
    latest = latest_path()
    history: list[Any] = []
    if latest.is_file():
        try:
            loaded = json.loads(latest.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            loaded = []
        if isinstance(loaded, list):
            history = loaded
        elif isinstance(loaded, dict) and loaded:
            history = [loaded]
    history.append(record)
    latest.write_text(json.dumps(history, indent=2, ensure_ascii=False), encoding="utf-8")
    return snap


def load_history() -> list[dict[str, Any]]:
    path = latest_path()
    if not path.is_file():
        return []
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    if isinstance(loaded, list):
        return [r for r in loaded if isinstance(r, dict)]
    if isinstance(loaded, dict) and loaded:
        return [loaded]
    return []


def latest_record() -> dict[str, Any] | None:
    history = load_history()
    return history[-1] if history else None


def _nested(board: dict[str, Any], *keys: str, default: Any = None) -> Any:
    cur: Any = board
    for key in keys:
        if isinstance(cur, dict) and key in cur:
            cur = cur[key]
        else:
            return default
    return cur


def format_report(record: dict[str, Any] | None = None) -> str:
    rec = record if record is not None else latest_record()
    if not rec:
        return (
            "No official score recorded yet.\n"
            "Internal checks (format matrix, crash-free 520 ritual, EQUIVALENT traps) "
            "are not the competition metric.\n"
            "To obtain a real score: `make submit` POSTs data/submission.json to INBOX_BASE_URL/submit "
            "and writes reports/official_score.json. Or hand the file to organizers for score_cli.py."
        )
    board = rec.get("scoreboard") if isinstance(rec.get("scoreboard"), dict) else rec
    if not isinstance(board, dict):
        board = {}
    final = board.get("final_score")
    stage1 = _nested(board, "stage1", "macro_f1")
    if stage1 is None:
        stage1 = board.get("stage1_macro_f1")
    stage3 = _nested(board, "stage3", "defect_f1")
    if stage3 is None:
        stage3 = board.get("stage3_defect_f1")
    e2e = _nested(board, "end_to_end", "rate")
    if e2e is None:
        e2e = board.get("end_to_end_rate")
    lines = [
        "Official scoreboard (organizer aggregate only — no per-email gold)",
        f"recorded_at: {rec.get('recorded_at') or '—'}",
        f"source: {rec.get('source') or '—'}",
        f"final_score: {final if final is not None else '—'}",
        f"  0.30 * stage1.macro_f1: {stage1 if stage1 is not None else '—'}",
        f"  0.20 * stage3.defect_f1: {stage3 if stage3 is not None else '—'}",
        f"  0.50 * end_to_end.rate: {e2e if e2e is not None else '—'}",
    ]
    reliability = board.get("reliability") or board.get("escalation") or {}
    if isinstance(reliability, dict) and reliability:
        lines.append("reliability / NEEDS_REVIEW:")
        for reason, val in reliability.items():
            lines.append(f"  {reason}: {val}")
    err = board.get("error")
    if err:
        lines.append(f"error: {err}")
    return "\n".join(lines) + "\n"
