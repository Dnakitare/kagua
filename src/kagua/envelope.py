"""Authority envelope: the declared bound on what each agent may do.

YAML, human-writable, diffable in git. Scope patterns:
  - exact:            "jira.read" matches only tool "jira.read"
  - prefix wildcard:  "jira.*" matches any tool starting with "jira."
  - qualifier:        "slack.post:channel=ops" matches only that exact string;
                      an unqualified grant "slack.post" also covers any
                      qualified call "slack.post:...". Qualifiers ride in the
                      tool string in v0.1.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import yaml


class EnvelopeError(Exception):
    pass


@dataclass
class Principal:
    id: str
    root: bool = False


@dataclass
class AgentDecl:
    id: str
    delegated_by: str | None = None
    tools: list[str] = field(default_factory=list)
    lifetime: str = "task"
    max_delegation_depth: int | None = None


@dataclass
class Invariant:
    kind: str
    params: dict = field(default_factory=dict)


@dataclass
class Envelope:
    principals: list[Principal] = field(default_factory=list)
    agents: list[AgentDecl] = field(default_factory=list)
    invariants: list[Invariant] = field(default_factory=list)

    def is_root(self, principal_id: str | None) -> bool:
        return any(p.id == principal_id and p.root for p in self.principals)

    def agent(self, agent_id: str | None) -> AgentDecl | None:
        for a in self.agents:
            if a.id == agent_id:
                return a
        return None


def covers(pattern: str, tool: str) -> bool:
    """Does a scope pattern authorize a tool string (or a narrower pattern)?"""
    if pattern == tool:
        return True
    if pattern.endswith("*") and tool.startswith(pattern[:-1]):
        return True
    # unqualified grant covers any qualified use: "slack.post" covers "slack.post:channel=ops"
    if tool.startswith(pattern + ":"):
        return True
    return False


def scope_covers(patterns: list[str], tool: str) -> bool:
    return any(covers(p, tool) for p in patterns)


def scope_widening(child: list[str], parent: list[str]) -> list[str]:
    """Child scope entries not covered by any parent entry (i.e. the widening)."""
    return [c for c in child if not any(covers(p, c) for p in parent)]


def load_envelope(path: str) -> Envelope:
    with open(path, encoding="utf-8") as fh:
        try:
            doc = yaml.safe_load(fh)
        except yaml.YAMLError as exc:
            raise EnvelopeError(f"invalid YAML: {exc}") from exc
    if not isinstance(doc, dict):
        raise EnvelopeError("envelope must be a YAML mapping")

    errors: list[str] = []
    env = Envelope()

    for i, p in enumerate(doc.get("principals") or []):
        if not isinstance(p, dict) or not p.get("id"):
            errors.append(f"principals[{i}]: needs an 'id'")
            continue
        env.principals.append(Principal(id=p["id"], root=bool(p.get("root", False))))

    for i, a in enumerate(doc.get("agents") or []):
        if not isinstance(a, dict) or not a.get("id"):
            errors.append(f"agents[{i}]: needs an 'id'")
            continue
        scope = a.get("scope") or {}
        tools = scope.get("tools") if isinstance(scope, dict) else None
        if not isinstance(tools, list) or not all(isinstance(t, str) for t in tools):
            errors.append(f"agents[{i}] ({a['id']}): scope.tools must be a list of strings")
            tools = []
        depth = a.get("max_delegation_depth")
        if depth is not None and (not isinstance(depth, int) or depth < 1):
            errors.append(f"agents[{i}] ({a['id']}): max_delegation_depth must be a positive integer")
            depth = None
        env.agents.append(
            AgentDecl(
                id=a["id"],
                delegated_by=a.get("delegated_by"),
                tools=list(tools),
                lifetime=a.get("lifetime", "task"),
                max_delegation_depth=depth,
            )
        )

    for i, inv in enumerate(doc.get("invariants") or []):
        if not isinstance(inv, dict) or not inv.get("kind"):
            errors.append(f"invariants[{i}]: needs a 'kind'")
            continue
        params = {k: v for k, v in inv.items() if k != "kind"}
        if inv["kind"] == "forbidden_composition":
            seq = params.get("sequence")
            if not isinstance(seq, list) or len(seq) < 2:
                errors.append(
                    f"invariants[{i}]: forbidden_composition needs a 'sequence' of at least 2 tool patterns"
                )
                continue
        env.invariants.append(Invariant(kind=inv["kind"], params=params))

    if not any(p.root for p in env.principals):
        errors.append("envelope declares no root principal (need at least one 'root: true')")
    if errors:
        raise EnvelopeError("; ".join(errors))
    return env
