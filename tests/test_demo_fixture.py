"""User story A1: the demo where every individual call is authorized and the
composition still fails. This is the README. If these tests break, the
product's first five minutes break."""
import os

from kagua.checks import run_all
from kagua.envelope import load_envelope
from kagua.events import load_trace
from kagua.render import render_verdict
from kagua.trace import Trace
from kagua.verdict import build_verdict
from tests.conftest import FIXTURES

TRACE = os.path.join(FIXTURES, "workorder", "trace.jsonl")
ENVELOPE = os.path.join(FIXTURES, "workorder", "envelope.yaml")


def run_demo():
    meta, events, errors = load_trace(TRACE)
    assert errors == []
    env = load_envelope(ENVELOPE)
    trace = Trace(events, meta)
    findings, unchecked = run_all(trace, env)
    return trace, env, findings, unchecked


def test_every_individual_call_is_authorized():
    trace, env, findings, _ = run_demo()
    point_families = {"Lifetime", "Scope", "Principal"}
    point_findings = [f for f in findings if f.family in point_families]
    assert point_findings == [], [f.message for f in point_findings]


def test_composition_is_the_only_failure():
    trace, env, findings, unchecked = run_demo()
    assert len(findings) == 1
    f = findings[0]
    assert f.family == "Composition"
    assert f.task == "t_workorder_442"
    assert unchecked == []


def test_witness_names_the_two_forbidden_calls():
    trace, _, findings, _ = run_demo()
    seq = findings[0].details["sequence_events"]
    tools = [trace.by_id[eid].tool for eid in seq]
    assert tools == ["vendors.get_quote", "payments.approve"]


def test_witness_renders_in_25_lines_or_less():
    trace, env, findings, unchecked = run_demo()
    verdict = build_verdict(trace, env, findings, unchecked, TRACE, ENVELOPE)
    text = render_verdict(verdict, trace, use_color=False)
    assert len(text.splitlines()) <= 25, text
    assert "FAIL" in text and "Composition" in text


def test_removing_the_invariant_yields_a_qualified_pass():
    meta, events, _ = load_trace(TRACE)
    env = load_envelope(ENVELOPE)
    env.invariants = []
    trace = Trace(events, meta)
    findings, unchecked = run_all(trace, env)
    assert findings == []
    verdict = build_verdict(trace, env, findings, unchecked, TRACE, ENVELOPE)
    assert verdict["passed"] is True
    assert verdict["grade"] == "qualified"  # no enforcement point: never a clean bill


def test_scope_drift_fixture_turns_ci_red_with_scope_witness():
    """User story A3: a tool-wiring change that widens effective authority."""
    trace_path = os.path.join(FIXTURES, "scope-drift", "trace.jsonl")
    env_path = os.path.join(FIXTURES, "scope-drift", "envelope.yaml")
    meta, events, errors = load_trace(trace_path)
    assert errors == []
    trace = Trace(events, meta)
    findings, _ = run_all(trace, load_envelope(env_path))
    scope_findings = [f for f in findings if f.family == "Scope"]
    assert any(f.rule == "grant-exceeds-envelope" for f in scope_findings)
    assert any("payments.approve" in f.message for f in scope_findings)
