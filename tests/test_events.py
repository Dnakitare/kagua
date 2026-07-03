import json
import os

from kagua.events import load_trace, parse_event, validate_events


def test_parse_valid_tool_call():
    errors = []
    ev = parse_event(
        {
            "event_id": "e1",
            "ts": "2026-07-02T14:03:11Z",
            "kind": "tool_call",
            "actor": "agent:x",
            "tool": "jira.read",
        },
        1,
        errors,
    )
    assert ev is not None and not errors
    assert ev.tool == "jira.read"
    assert ev.ts.tzinfo is not None


def test_unknown_kind_rejected():
    errors = []
    assert parse_event({"event_id": "e1", "ts": "2026-01-01T00:00:00Z", "kind": "nope"}, 3, errors) is None
    assert "line 3" in errors[0]


def test_missing_required_field_per_kind():
    errors = []
    assert (
        parse_event(
            {"event_id": "e1", "ts": "2026-01-01T00:00:00Z", "kind": "tool_call", "actor": "a"},
            1,
            errors,
        )
        is None
    )
    assert "requires field 'tool'" in errors[0]


def test_delegation_requires_scope_shape():
    errors = []
    assert (
        parse_event(
            {
                "event_id": "e1",
                "ts": "2026-01-01T00:00:00Z",
                "kind": "delegation",
                "actor": "a",
                "warrant": "w1",
                "subject": "b",
                "scope": {"tools": "not-a-list"},
                "lifetime": "task",
            },
            1,
            errors,
        )
        is None
    )


def test_validate_duplicate_ids_and_dangling_parent():
    errors = []
    events = [
        parse_event({"event_id": "e1", "ts": "2026-01-01T00:00:00Z", "kind": "task_start", "task": "t"}, 1, errors),
        parse_event({"event_id": "e1", "ts": "2026-01-01T00:00:01Z", "kind": "task_end", "task": "t", "parent": "e9"}, 2, errors),
    ]
    problems = validate_events(events)
    assert any("duplicate event_id" in p for p in problems)
    assert any("parent 'e9'" in p for p in problems)


def test_load_trace_reads_meta_and_reports_bad_json(tmp_path):
    p = tmp_path / "t.jsonl"
    p.write_text(
        json.dumps({"kind": "trace_meta", "source": "otel", "coverage": "partial"})
        + "\n{broken\n"
        + json.dumps({"event_id": "e1", "ts": "2026-01-01T00:00:00Z", "kind": "task_start", "task": "t"})
        + "\n"
    )
    meta, events, errors = load_trace(str(p))
    assert meta.source == "otel" and meta.coverage == "partial"
    assert len(events) == 1
    assert any("invalid JSON" in e for e in errors)


def test_workorder_fixture_is_valid():
    fixtures = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fixtures")
    meta, events, errors = load_trace(os.path.join(fixtures, "workorder", "trace.jsonl"))
    assert errors == []
    assert len(events) == 40
    assert meta.source == "native"
