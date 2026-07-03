from kagua.checks import scope
from kagua.trace import Trace
from tests.conftest import delegation, ev


def rules(findings):
    return {f.rule for f in findings}


def test_call_within_warrant_scope_passes(env):
    events = [
        delegation("e1", issuer="human:root", subject="agent:a", warrant="w1", tools=["jira.*"]),
        ev("e2", "tool_call", actor="agent:a", tool="jira.read", warrant="w1", parent="e1"),
    ]
    assert scope.check(Trace(events), env) == []


def test_call_outside_warrant_scope(env):
    events = [
        delegation("e1", issuer="human:root", subject="agent:a", warrant="w1", tools=["jira.*"]),
        ev("e2", "tool_call", actor="agent:a", tool="payments.approve", warrant="w1", parent="e1"),
    ]
    findings = scope.check(Trace(events), env)
    assert rules(findings) == {"call-outside-warrant-scope"}
    assert findings[0].witness == ["e1", "e2"]


def test_scope_widening_across_hop(env):
    events = [
        delegation("e1", issuer="human:root", subject="agent:a", warrant="w1", tools=["jira.*"]),
        delegation("e2", issuer="agent:a", subject="agent:b", warrant="w2",
                   parent_warrant="w1", tools=["jira.read", "slack.post"], parent="e1"),
    ]
    findings = scope.check(Trace(events), env)
    assert "scope-widened-across-hop" in rules(findings)
    widening = [f for f in findings if f.rule == "scope-widened-across-hop"][0]
    assert widening.details["widened"] == ["slack.post"]


def test_grant_exceeding_envelope_declaration(env):
    # agent:b is declared with only jira.read; the hop grants email.send too.
    # email.send is inside the parent warrant, so only the envelope check fires.
    events = [
        delegation("e1", issuer="human:root", subject="agent:a", warrant="w1",
                   tools=["jira.*", "email.send"]),
        delegation("e2", issuer="agent:a", subject="agent:b", warrant="w2",
                   parent_warrant="w1", tools=["jira.read", "email.send"], parent="e1"),
    ]
    findings = scope.check(Trace(events), env)
    assert rules(findings) == {"grant-exceeds-envelope"}


def test_warrantless_trace_point_checks_against_envelope(env):
    events = [
        ev("e1", "tool_call", actor="agent:a", tool="payments.approve"),
        ev("e2", "tool_call", actor="agent:a", tool="jira.read"),
    ]
    findings = scope.check(Trace(events), env)
    assert rules(findings) == {"call-outside-declared-scope"}
    assert len(findings) == 1
