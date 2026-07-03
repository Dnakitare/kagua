"""Regression tests against a GENUINE OpenLLMetry export (fixtures/otel/
openllmetry-langchain.json): real opentelemetry-instrumentation-langchain
spans from a LangChain tool loop, zero hand-authored spans.

These encode what first contact with reality taught us:
- a bare agent loop shares no root span, so every call lands in its own
  OTel trace and within-task checks correlate nothing (must be reported)
- plaintext tool arguments can be hashed into derived (not attested) digests
- actor identity falls back to service.name and must be flagged
- clock tolerance must not suppress composition true positives on
  millisecond-apart, causally-disconnected calls
"""
import os

from kagua.checks import run_all
from kagua.envelope import AgentDecl, Envelope, Invariant, Principal
from kagua.events import load_trace
from kagua.ingest.otel import ingest
from kagua.trace import Trace
from tests.conftest import FIXTURES

EXPORT = os.path.join(FIXTURES, "otel", "openllmetry-langchain.json")


def real_envelope():
    return Envelope(
        principals=[Principal(id="human:ops.manager", root=True)],
        agents=[
            AgentDecl(
                id="workorder-agents",
                delegated_by="human:ops.manager",
                tools=["workorders_read", "vendors_search", "vendors_get_quote", "payments_approve"],
            )
        ],
        invariants=[
            Invariant(
                kind="forbidden_composition",
                params={"sequence": ["vendors_get_quote", "payments_approve"], "within": "task"},
            )
        ],
    )


def test_real_export_ingests_all_tool_calls(tmp_path):
    out = str(tmp_path / "t.jsonl")
    report = ingest(EXPORT, out)
    assert report.tool_calls == 4
    assert report.skipped  # the 5 chat spans are counted, not hidden
    _, events, errors = load_trace(out)
    assert errors == []
    assert sorted(e.tool for e in events) == [
        "payments_approve", "vendors_get_quote", "vendors_search", "workorders_read",
    ]


def test_task_fragmentation_is_reported_not_silent(tmp_path):
    report = ingest(EXPORT, str(tmp_path / "t.jsonl"))
    assert report.distinct_tasks == report.events_emitted == 4
    text = report.render_text()
    assert "disjoint traces" in text
    assert "--task" in text


def test_task_override_groups_and_declares_itself(tmp_path):
    out = str(tmp_path / "t.jsonl")
    report = ingest(EXPORT, out, task_override="t_wo")
    assert report.distinct_tasks == 1
    assert "your assertion" in report.render_text()
    _, events, _ = load_trace(out)
    assert all(e.task == "t_wo" for e in events)


def test_derived_args_digests_are_flagged(tmp_path):
    report = ingest(EXPORT, str(tmp_path / "t.jsonl"))
    assert report.tool_calls_with_args_digest == 4
    assert report.args_digests_derived == 4
    assert "not attested by source" in report.render_text()


def test_actor_fallback_to_service_name_is_flagged(tmp_path):
    out = str(tmp_path / "t.jsonl")
    report = ingest(EXPORT, out)
    assert report.actor_from_service_name == 4
    assert "service.name" in report.render_text()
    _, events, _ = load_trace(out)
    assert all(e.actor == "workorder-agents" for e in events)


def test_composition_fires_on_real_trace_despite_clock_tolerance(tmp_path):
    """The bug reality found: ms-apart calls with no causal links were
    'unordered' under the tolerance window and the forbidden pair passed."""
    out = str(tmp_path / "t.jsonl")
    ingest(EXPORT, out, task_override="t_wo")
    meta, events, _ = load_trace(out)
    trace = Trace(events, meta)
    findings, _ = run_all(trace, real_envelope())
    comp = [f for f in findings if f.family == "Composition"]
    assert len(comp) == 1
    assert "concurrent-within-tolerance" in comp[0].details["ordering"]
    assert "co-occurrence" in comp[0].message
