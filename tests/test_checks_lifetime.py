from datetime import timedelta

from kagua.checks import lifetime
from kagua.trace import Trace
from tests.conftest import delegation, ev


def base_events():
    return [
        ev("e1", "task_start"),
        delegation("e2", issuer="human:root", subject="agent:a", warrant="w1",
                   tools=["jira.*"], parent="e1"),
        ev("e3", "tool_call", actor="agent:a", tool="jira.read", warrant="w1", parent="e2"),
        ev("e4", "task_end", parent="e3"),
    ]


def rules(findings):
    return {f.rule for f in findings}


def test_clean_trace_no_findings(env):
    assert lifetime.check(Trace(base_events()), env) == []


def test_zombie_authority_after_task_end(env):
    events = base_events() + [
        ev("e5", "tool_call", actor="agent:a", tool="jira.read", warrant="w1", parent="e4")
    ]
    findings = lifetime.check(Trace(events), env)
    assert rules(findings) == {"zombie-authority"}
    assert findings[0].witness == ["e2", "e4", "e5"]


def test_use_before_issue(env):
    events = [
        ev("e1", "task_start"),
        ev("e2", "tool_call", actor="agent:a", tool="jira.read", warrant="w1", parent="e1"),
        delegation("e3", issuer="human:root", subject="agent:a", warrant="w1",
                   tools=["jira.*"], parent="e2"),
    ]
    assert rules(lifetime.check(Trace(events), env)) == {"use-before-issue"}


def test_use_after_revoke(env):
    events = base_events()[:3] + [
        ev("e4", "token_revoke", actor="agent:a", warrant="w1", parent="e3"),
        ev("e5", "tool_call", actor="agent:a", tool="jira.read", warrant="w1", parent="e4"),
        ev("e6", "task_end", parent="e5"),
    ]
    assert rules(lifetime.check(Trace(events), env)) == {"use-after-revoke"}


def test_cross_task_use(env):
    events = base_events() + [
        ev("e5", "task_start", task="t2"),
        ev("e6", "tool_call", actor="agent:a", tool="jira.read", warrant="w1",
           task="t2", parent="e5"),
    ]
    found = rules(lifetime.check(Trace(events), env))
    assert "cross-task-use" in found


def test_clock_skew_produces_no_false_positive(env):
    # task_end's clock reads 3s AFTER a later call, but they're causally
    # ordered end -> nothing; skew is inside tolerance, so no zombie finding
    events = base_events()
    events[3].ts = events[2].ts + timedelta(seconds=3)
    extra = ev("e5", "tool_call", actor="agent:a", tool="jira.read", warrant="w1",
               offset_s=None, parent="e3")
    extra.ts = events[3].ts - timedelta(seconds=1)  # concurrent with task_end
    findings = lifetime.check(Trace(events + [extra]), env)
    assert findings == []


def test_no_warrants_returns_no_findings(env):
    events = [ev("e1", "tool_call", actor="agent:a", tool="jira.read")]
    assert lifetime.check(Trace(events), env) == []
