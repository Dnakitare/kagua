from kagua.checks import principal
from kagua.trace import Trace
from tests.conftest import delegation, ev


def rules(findings):
    return {f.rule for f in findings}


def test_clean_chain_no_findings(env):
    events = [
        delegation("e1", issuer="human:root", subject="agent:a", warrant="w1", tools=["jira.*"]),
        ev("e2", "tool_call", actor="agent:a", tool="jira.read", warrant="w1", parent="e1"),
    ]
    assert principal.check(Trace(events), env) == []


def test_orphaned_warrant_reference(env):
    events = [
        delegation("e1", issuer="human:root", subject="agent:a", warrant="w1", tools=["jira.*"]),
        ev("e2", "tool_call", actor="agent:a", tool="jira.read", warrant="w_ghost", parent="e1"),
    ]
    assert rules(principal.check(Trace(events), env)) == {"missing-delegation-hop"}


def test_chain_terminating_at_non_root(env):
    events = [
        # issuer is another agent with no chain of its own
        delegation("e1", issuer="agent:rogue", subject="agent:a", warrant="w1", tools=["jira.*"]),
        ev("e2", "tool_call", actor="agent:a", tool="jira.read", warrant="w1", parent="e1"),
    ]
    found = rules(principal.check(Trace(events), env))
    assert "non-root-chain" in found


def test_actor_using_someone_elses_warrant(env):
    events = [
        delegation("e1", issuer="human:root", subject="agent:a", warrant="w1", tools=["jira.*"]),
        ev("e2", "tool_call", actor="agent:b", tool="jira.read", warrant="w1", parent="e1"),
    ]
    assert "actor-warrant-mismatch" in rules(principal.check(Trace(events), env))


def test_delegation_depth_exceeded(env):
    # agent:a is declared max_delegation_depth=1 but holds a depth-2 warrant
    events = [
        delegation("e1", issuer="human:root", subject="agent:b", warrant="w1",
                   tools=["jira.read"]),
        delegation("e2", issuer="agent:b", subject="agent:a", warrant="w2",
                   parent_warrant="w1", tools=["jira.read"], parent="e1"),
        ev("e3", "tool_call", actor="agent:a", tool="jira.read", warrant="w2", parent="e2"),
    ]
    assert "depth-exceeded" in rules(principal.check(Trace(events), env))


def test_undeclared_delegator(env):
    # envelope says agent:b is delegated by agent:a, not human:root
    events = [
        delegation("e1", issuer="human:root", subject="agent:b", warrant="w1", tools=["jira.read"]),
    ]
    assert "undeclared-delegator" in rules(principal.check(Trace(events), env))


def test_tool_call_with_no_warrant_in_warranted_trace(env):
    events = [
        delegation("e1", issuer="human:root", subject="agent:a", warrant="w1", tools=["jira.*"]),
        ev("e2", "tool_call", actor="agent:a", tool="jira.read", parent="e1"),
    ]
    assert "orphaned-authority" in rules(principal.check(Trace(events), env))


def test_warrantless_trace_is_unverifiable_not_flooded(env):
    events = [ev("e1", "tool_call", actor="agent:a", tool="jira.read")]
    assert principal.check(Trace(events), env) == []


def test_chain_findings_dedupe_per_warrant(env):
    events = [
        delegation("e1", issuer="agent:rogue", subject="agent:a", warrant="w1", tools=["jira.*"]),
    ] + [
        ev(f"e{i}", "tool_call", actor="agent:a", tool="jira.read", warrant="w1", parent="e1")
        for i in range(2, 6)
    ]
    findings = principal.check(Trace(events), env)
    assert len([f for f in findings if f.rule == "non-root-chain"]) == 1
