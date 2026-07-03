import os

from kagua.checks import run_all
from kagua.envelope import AgentDecl, Envelope, Principal
from kagua.events import load_trace
from kagua.ingest.otel import ingest
from kagua.trace import Trace
from kagua.verdict import build_verdict
from tests.conftest import FIXTURES

SPANS = os.path.join(FIXTURES, "otel", "spans.json")


def test_otel_ingest_produces_valid_canonical_trace(tmp_path):
    out = str(tmp_path / "trace.jsonl")
    report = ingest(SPANS, out)
    meta, events, errors = load_trace(out)
    assert errors == []
    assert meta.source == "otel"

    assert report.spans_total == 7
    kinds = [e.kind for e in events]
    assert kinds.count("tool_call") == 3
    assert kinds.count("delegation") == 1


def test_kagua_attributes_recovered(tmp_path):
    out = str(tmp_path / "trace.jsonl")
    ingest(SPANS, out)
    _, events, _ = load_trace(out)
    d = [e for e in events if e.kind == "delegation"][0]
    assert d.warrant == "w_triage"
    assert d.actor == "human:daniel"
    assert d.scope["tools"] == ["jira.read", "jira.create_ticket"]
    warranted = [e for e in events if e.kind == "tool_call" and e.warrant]
    assert len(warranted) == 1
    assert warranted[0].args_digest == "sha256:e0e1"


def test_parent_remapping_skips_dropped_spans(tmp_path):
    out = str(tmp_path / "trace.jsonl")
    ingest(SPANS, out)
    _, events, _ = load_trace(out)
    by_id = {e.event_id: e for e in events}
    # jira.read's OTel parent is the dropped chat span; must remap to an
    # emitted ancestor or none, never dangle
    for e in events:
        assert e.parent is None or e.parent in by_id


def test_loss_report_is_honest():
    report = ingest(SPANS, os.devnull)
    text = report.render_text()
    assert "cannot support" in text
    assert "QUALIFIED" in text
    assert f"{report.tool_calls_with_warrant}/{report.tool_calls} warrants" in text
    assert report.skipped  # model spans and the http span were counted, not hidden


def test_lossy_trace_never_silently_passes(tmp_path):
    """The A2 acceptance shape: qualified verdict, families marked unverifiable."""
    out = str(tmp_path / "trace.jsonl")
    ingest(SPANS, out)
    meta, events, _ = load_trace(out)
    trace = Trace(events, meta)
    env = Envelope(
        principals=[Principal(id="human:daniel", root=True)],
        agents=[AgentDecl(id="agent:triage-1", delegated_by="human:daniel",
                          tools=["jira.*", "slack.post"])],
    )
    findings, unchecked = run_all(trace, env)
    verdict = build_verdict(trace, env, findings, unchecked, out,
                            os.path.join(FIXTURES, "workorder", "envelope.yaml"))
    assert verdict["grade"] == "qualified"
    assert any("visible trace" in r for r in verdict["grade_reasons"])
