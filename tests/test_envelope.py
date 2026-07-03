import os

import pytest

from kagua.envelope import EnvelopeError, covers, load_envelope, scope_widening
from tests.conftest import FIXTURES


def test_covers_exact_wildcard_and_qualifier():
    assert covers("jira.read", "jira.read")
    assert covers("jira.*", "jira.read")
    assert not covers("jira.*", "slack.post")
    # unqualified grant covers qualified use, never the reverse
    assert covers("slack.post", "slack.post:channel=ops")
    assert not covers("slack.post:channel=ops", "slack.post")
    assert covers("slack.post:channel=ops", "slack.post:channel=ops")


def test_scope_widening_detects_escape():
    assert scope_widening(["jira.read"], ["jira.*"]) == []
    assert scope_widening(["jira.read", "payments.approve"], ["jira.*"]) == ["payments.approve"]


def test_load_workorder_envelope():
    env = load_envelope(os.path.join(FIXTURES, "workorder", "envelope.yaml"))
    assert env.is_root("human:ops.manager")
    assert not env.is_root("agent:coordinator")
    assert env.agent("agent:finance").max_delegation_depth == 2
    assert env.invariants[0].kind == "forbidden_composition"
    assert env.invariants[0].params["sequence"] == ["vendors.get_quote", "payments.approve"]


def test_envelope_without_root_principal_rejected(tmp_path):
    p = tmp_path / "env.yaml"
    p.write_text("principals:\n  - id: human:x\nagents: []\n")
    with pytest.raises(EnvelopeError, match="root principal"):
        load_envelope(str(p))


def test_forbidden_composition_needs_sequence(tmp_path):
    p = tmp_path / "env.yaml"
    p.write_text(
        "principals:\n  - id: human:x\n    root: true\n"
        "invariants:\n  - kind: forbidden_composition\n    sequence: [only-one]\n"
    )
    with pytest.raises(EnvelopeError, match="sequence"):
        load_envelope(str(p))
