from kagua.checks import composition
from kagua.envelope import Invariant
from kagua.trace import Trace
from tests.conftest import delegation, ev


def base(seq_first="jira.read", seq_second="email.send"):
    return [
        ev("e1", "task_start"),
        delegation("e2", issuer="human:root", subject="agent:a", warrant="w1",
                   tools=["jira.*", "email.send"], parent="e1"),
        ev("e3", "tool_call", actor="agent:a", tool=seq_first, warrant="w1", parent="e2"),
        ev("e4", "tool_call", actor="agent:a", tool=seq_second, warrant="w1", parent="e3"),
        ev("e5", "task_end", parent="e4"),
    ]


def test_forbidden_sequence_detected(env):
    findings, unchecked = composition.check(Trace(base()), env)
    assert len(findings) == 1
    f = findings[0]
    assert f.rule == "forbidden_composition"
    assert f.details["sequence_events"] == ["e3", "e4"]
    # witness includes the granting delegation and task boundary
    assert "e2" in f.witness and "e1" in f.witness
    assert unchecked == []


def test_reversed_order_is_no_violation(env):
    events = base(seq_first="email.send", seq_second="jira.read")
    findings, _ = composition.check(Trace(events), env)
    assert findings == []


def test_sequence_across_tasks_is_no_violation(env):
    events = base()
    events[3].task = "t2"  # the email.send happens in a different task
    findings, _ = composition.check(Trace(events), env)
    assert findings == []


def test_retry_cannot_match_two_slots_of_same_tool(env):
    env.invariants = [
        Invariant(kind="forbidden_composition",
                  params={"sequence": ["jira.read", "jira.read"], "within": "task"})
    ]
    events = [
        ev("e1", "task_start"),
        delegation("e2", issuer="human:root", subject="agent:a", warrant="w1",
                   tools=["jira.*"], parent="e1"),
        ev("e3", "tool_call", actor="agent:a", tool="jira.read", warrant="w1",
           parent="e2", idempotency_key="k1"),
        ev("e4", "tool_call", actor="agent:a", tool="jira.read", warrant="w1",
           parent="e3", idempotency_key="k1", result="retry"),
        ev("e5", "task_end", parent="e4"),
    ]
    findings, _ = composition.check(Trace(events), env)
    assert findings == []
    # two genuinely distinct reads DO match
    events[3].idempotency_key = "k2"
    findings, _ = composition.check(Trace(events), env)
    assert len(findings) == 1


def test_unsupported_invariant_kinds_are_returned_not_dropped(env):
    env.invariants.append(Invariant(kind="budget", params={"max": 20}))
    findings, unchecked = composition.check(Trace(base()), env)
    assert [i.kind for i in unchecked] == ["budget"]


def test_pattern_matching_in_sequence(env):
    env.invariants = [
        Invariant(kind="forbidden_composition",
                  params={"sequence": ["jira.*", "email.send"], "within": "task"})
    ]
    findings, _ = composition.check(Trace(base()), env)
    assert len(findings) == 1
