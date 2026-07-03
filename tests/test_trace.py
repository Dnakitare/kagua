from datetime import timedelta

from kagua.trace import Trace
from tests.conftest import BASE, delegation, ev


def linear_events():
    return [
        ev("e1", "task_start"),
        delegation("e2", issuer="human:root", subject="agent:a", warrant="w1",
                   tools=["jira.*"], parent="e1"),
        ev("e3", "tool_call", actor="agent:a", tool="jira.read", warrant="w1", parent="e2"),
        ev("e4", "task_end", parent="e3"),
    ]


def test_causal_order_beats_wall_clock():
    events = linear_events()
    # e3's clock is skewed 30s before its parent e2; causality must win
    events[2].ts = BASE - timedelta(seconds=30)
    t = Trace(events)
    assert t.happens_before(t.by_id["e2"], t.by_id["e3"])
    assert not t.happens_before(t.by_id["e3"], t.by_id["e2"])


def test_concurrent_within_tolerance_is_unordered():
    a = ev("e1", "tool_call", actor="x", tool="a.b", offset_s=0)
    b = ev("e2", "tool_call", actor="x", tool="c.d", offset_s=3)  # inside 5s tolerance
    t = Trace([a, b])
    assert not t.happens_before(a, b)
    assert not t.happens_before(b, a)


def test_timestamp_fallback_beyond_tolerance():
    a = ev("e1", "tool_call", actor="x", tool="a.b", offset_s=0)
    b = ev("e2", "tool_call", actor="x", tool="c.d", offset_s=30)
    t = Trace([a, b])
    assert t.happens_before(a, b)


def test_warrant_chain_walks_to_root():
    events = [
        delegation("e1", issuer="human:root", subject="agent:a", warrant="w1", tools=["jira.*"]),
        delegation("e2", issuer="agent:a", subject="agent:b", warrant="w2",
                   parent_warrant="w1", tools=["jira.read"], parent="e1"),
    ]
    t = Trace(events)
    chain, problem = t.warrant_chain("w2")
    assert problem is None
    assert [w.id for w in chain] == ["w2", "w1"]


def test_warrant_chain_reports_missing_hop():
    events = [
        delegation("e1", issuer="agent:a", subject="agent:b", warrant="w2",
                   parent_warrant="w_ghost", tools=["jira.read"]),
    ]
    t = Trace(events)
    chain, problem = t.warrant_chain("w2")
    assert problem == "missing:w_ghost"


def test_token_revoke_marks_warrant():
    events = linear_events() + [
        ev("e5", "token_revoke", actor="agent:a", warrant="w1", parent="e4")
    ]
    t = Trace(events)
    assert t.warrants["w1"].revoked_by == "e5"
