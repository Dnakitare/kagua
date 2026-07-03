import os
from datetime import datetime, timedelta, timezone

import pytest

from kagua.envelope import AgentDecl, Envelope, Invariant, Principal
from kagua.events import Event
from kagua.trace import Trace

FIXTURES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fixtures")
BASE = datetime(2026, 7, 2, 12, 0, 0, tzinfo=timezone.utc)


def ev(event_id, kind, *, offset_s=None, parent=None, task="t1", **fields):
    """Event factory: 10s spacing by default (outside the 5s clock tolerance)."""
    if offset_s is None:
        offset_s = int(event_id.lstrip("e")) * 10
    return Event(
        event_id=event_id,
        ts=BASE + timedelta(seconds=offset_s),
        kind=kind,
        parent=parent,
        task=task,
        **fields,
    )


def delegation(event_id, *, issuer, subject, warrant, tools, parent_warrant=None,
               lifetime="task", **kw):
    return ev(
        event_id,
        "delegation",
        actor=issuer,
        subject=subject,
        warrant=warrant,
        parent_warrant=parent_warrant,
        scope={"tools": tools},
        lifetime=lifetime,
        **kw,
    )


def make_trace(events, **kw):
    return Trace(events, **kw)


@pytest.fixture
def env():
    """One root principal, one agent, one sub-agent."""
    return Envelope(
        principals=[Principal(id="human:root", root=True)],
        agents=[
            AgentDecl(
                id="agent:a",
                delegated_by="human:root",
                tools=["jira.*", "email.send"],
                max_delegation_depth=1,
            ),
            AgentDecl(
                id="agent:b",
                delegated_by="agent:a",
                tools=["jira.read"],
                max_delegation_depth=2,
            ),
        ],
        invariants=[
            Invariant(
                kind="forbidden_composition",
                params={"sequence": ["jira.read", "email.send"], "within": "task"},
            )
        ],
    )
