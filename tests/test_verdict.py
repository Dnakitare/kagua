import os

from kagua.checks import run_all
from kagua.envelope import load_envelope
from kagua.events import TraceMeta, load_trace
from kagua.trace import Trace
from kagua.verdict import build_verdict
from tests.conftest import FIXTURES

TRACE = os.path.join(FIXTURES, "workorder", "trace.jsonl")
ENVELOPE = os.path.join(FIXTURES, "workorder", "envelope.yaml")


def test_attested_requires_enforcement_point_and_complete_coverage():
    _, events, _ = load_trace(TRACE)
    env = load_envelope(ENVELOPE)

    meta = TraceMeta(source="mcp-gateway", coverage="complete",
                     enforcement_point="gateway:truefoundry-prod")
    trace = Trace(events, meta)
    findings, unchecked = run_all(trace, env)
    verdict = build_verdict(trace, env, findings, unchecked, TRACE, ENVELOPE)
    assert verdict["grade"] == "attested"

    # same enforcement point with partial coverage must degrade to qualified
    meta = TraceMeta(source="mcp-gateway", coverage="partial",
                     enforcement_point="gateway:truefoundry-prod")
    verdict = build_verdict(Trace(events, meta), env, findings, unchecked, TRACE, ENVELOPE)
    assert verdict["grade"] == "qualified"


def test_verdict_is_content_addressed():
    meta, events, _ = load_trace(TRACE)
    env = load_envelope(ENVELOPE)
    trace = Trace(events, meta)
    findings, unchecked = run_all(trace, env)
    v1 = build_verdict(trace, env, findings, unchecked, TRACE, ENVELOPE)
    v2 = build_verdict(trace, env, findings, unchecked, TRACE, ENVELOPE)
    assert v1 == v2
    assert len(v1["inputs"]["trace"]["sha256"]) == 64


def test_unchecked_invariants_surface_in_verdict():
    meta, events, _ = load_trace(TRACE)
    env = load_envelope(ENVELOPE)
    env.invariants.append(type(env.invariants[0])(kind="budget", params={"max": 20}))
    trace = Trace(events, meta)
    findings, unchecked = run_all(trace, env)
    verdict = build_verdict(trace, env, findings, unchecked, TRACE, ENVELOPE)
    assert verdict["unchecked_invariants"] == [{"kind": "budget", "params": {"max": 20}}]
