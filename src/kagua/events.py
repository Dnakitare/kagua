"""Canonical Kagua trace: JSONL event schema, parser, and structural validator.

One event per line. The optional first line may be a trace_meta record
describing the source and its coverage claims; everything downstream
(coverage grading, family checkability) keys off it.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime

EVENT_KINDS = frozenset(
    {
        "delegation",
        "tool_call",
        "task_start",
        "task_end",
        "token_issue",
        "token_revoke",
        "message",
    }
)

# Fields that must be present (non-null) per kind, beyond event_id/ts/kind.
REQUIRED_BY_KIND = {
    "delegation": ("actor", "warrant", "subject", "scope", "lifetime"),
    "tool_call": ("actor", "tool"),
    "task_start": ("task",),
    "task_end": ("task",),
    "token_issue": ("actor", "warrant"),
    "token_revoke": ("actor", "warrant"),
    "message": ("actor",),
}

LIFETIMES = frozenset({"task", "unbounded"})


@dataclass
class TraceMeta:
    """Source claims about the trace. Drives the verdict's coverage grade."""

    source: str = "native"
    coverage: str = "unknown"  # complete | partial | unknown
    enforcement_point: str | None = None
    adapter_loss: dict | None = None

    def to_json(self) -> dict:
        d = {"kind": "trace_meta", "source": self.source, "coverage": self.coverage}
        if self.enforcement_point:
            d["enforcement_point"] = self.enforcement_point
        if self.adapter_loss:
            d["adapter_loss"] = self.adapter_loss
        return d


@dataclass
class Event:
    event_id: str
    ts: datetime
    kind: str
    actor: str | None = None
    tool: str | None = None
    args_digest: str | None = None
    warrant: str | None = None
    parent: str | None = None
    task: str | None = None
    result: str | None = None
    idempotency_key: str | None = None
    # delegation-only fields
    subject: str | None = None
    parent_warrant: str | None = None
    scope: dict | None = None
    lifetime: str | None = None
    # optional human-readable one-liner, rendered in witnesses
    summary: str | None = None
    raw: dict = field(default_factory=dict, repr=False)

    @property
    def logical_id(self) -> str:
        """Retried calls share an idempotency key and collapse to one action."""
        return self.idempotency_key or self.event_id


def parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


_STR_FIELDS = (
    "actor",
    "tool",
    "args_digest",
    "warrant",
    "parent",
    "task",
    "result",
    "idempotency_key",
    "subject",
    "parent_warrant",
    "lifetime",
    "summary",
)


def parse_event(obj: dict, lineno: int, errors: list[str]) -> Event | None:
    def err(msg: str) -> None:
        errors.append(f"line {lineno}: {msg}")

    if not isinstance(obj, dict):
        err("event is not a JSON object")
        return None
    kind = obj.get("kind")
    if kind not in EVENT_KINDS:
        err(f"unknown event kind {kind!r}")
        return None
    event_id = obj.get("event_id")
    if not isinstance(event_id, str) or not event_id:
        err("missing or invalid event_id")
        return None
    try:
        ts = parse_ts(obj["ts"])
    except (KeyError, TypeError, ValueError):
        err(f"event {event_id}: missing or unparseable ts (want RFC 3339)")
        return None

    ev = Event(event_id=event_id, ts=ts, kind=kind, raw=obj)
    for f in _STR_FIELDS:
        v = obj.get(f)
        if v is not None and not isinstance(v, str):
            err(f"event {event_id}: field {f!r} must be a string")
            return None
        setattr(ev, f, v)
    scope = obj.get("scope")
    if scope is not None:
        if not isinstance(scope, dict) or not isinstance(scope.get("tools"), list):
            err(f"event {event_id}: scope must be an object with a 'tools' list")
            return None
        ev.scope = scope

    for f in REQUIRED_BY_KIND[kind]:
        if getattr(ev, f) is None:
            err(f"event {event_id}: kind {kind!r} requires field {f!r}")
            return None
    if ev.lifetime is not None and ev.lifetime not in LIFETIMES:
        err(f"event {event_id}: lifetime must be one of {sorted(LIFETIMES)}")
        return None
    return ev


def validate_events(events: list[Event]) -> list[str]:
    """Cross-event structural checks. Semantic checks live in kagua.checks."""
    errors: list[str] = []
    seen_ids: set[str] = set()
    warrants_issued: set[str] = set()
    for ev in events:
        if ev.event_id in seen_ids:
            errors.append(f"duplicate event_id {ev.event_id!r}")
        seen_ids.add(ev.event_id)
        if ev.kind == "delegation":
            if ev.warrant in warrants_issued:
                errors.append(
                    f"event {ev.event_id}: warrant {ev.warrant!r} issued more than once"
                )
            warrants_issued.add(ev.warrant)
    for ev in events:
        if ev.parent is not None and ev.parent not in seen_ids:
            errors.append(
                f"event {ev.event_id}: parent {ev.parent!r} does not exist in trace"
            )
    return errors


def load_trace(path: str) -> tuple[TraceMeta, list[Event], list[str]]:
    """Parse a JSONL trace file. Returns (meta, events, errors)."""
    meta = TraceMeta()
    events: list[Event] = []
    errors: list[str] = []
    with open(path, encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                errors.append(f"line {lineno}: invalid JSON ({exc.msg})")
                continue
            if isinstance(obj, dict) and obj.get("kind") == "trace_meta":
                meta = TraceMeta(
                    source=obj.get("source", "native"),
                    coverage=obj.get("coverage", "unknown"),
                    enforcement_point=obj.get("enforcement_point"),
                    adapter_loss=obj.get("adapter_loss"),
                )
                continue
            ev = parse_event(obj, lineno, errors)
            if ev is not None:
                events.append(ev)
    errors.extend(validate_events(events))
    return meta, events, errors
