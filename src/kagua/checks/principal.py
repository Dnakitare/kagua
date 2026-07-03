"""Principal family: every event's warrant chain terminates at a declared
root principal; no orphaned authority; actors only use warrants issued to
them; chain depth stays within the declared maximum.

If the trace contains no delegation records at all (lossy ingest), the whole
family is unverifiable and the verdict's coverage section says so; we emit
no findings rather than flooding false orphans.
"""
from __future__ import annotations

from ..envelope import Envelope
from ..trace import Trace
from . import Finding

FAMILY = "Principal"


def check(trace: Trace, env: Envelope) -> list[Finding]:
    findings: list[Finding] = []
    if not trace.warrants:
        return findings

    # chain-level findings dedupe per warrant, not per referencing event
    seen: set[tuple[str, str]] = set()

    def once(key: tuple[str, str]) -> bool:
        if key in seen:
            return False
        seen.add(key)
        return True

    for e in trace.events:
        if e.kind == "delegation":
            decl = env.agent(e.subject)
            if decl is not None and decl.delegated_by is not None and e.actor != decl.delegated_by:
                findings.append(
                    Finding(
                        FAMILY,
                        "undeclared-delegator",
                        f"{e.actor} delegated to {e.subject}, but the envelope declares"
                        f" {e.subject} as delegated by {decl.delegated_by}",
                        e.task,
                        [e.event_id],
                    )
                )
            continue

        if e.warrant is None:
            if e.kind == "tool_call":
                findings.append(
                    Finding(
                        FAMILY,
                        "orphaned-authority",
                        f"{e.event_id}: {e.actor} called {e.tool} with no warrant",
                        e.task,
                        [e.event_id],
                    )
                )
            continue

        chain, problem = trace.warrant_chain(e.warrant)
        if problem is not None:
            kind, _, wid = problem.partition(":")
            rule = "missing-delegation-hop" if kind == "missing" else "warrant-cycle"
            if once((rule, e.warrant)):
                findings.append(
                    Finding(
                        FAMILY,
                        rule,
                        f"warrant chain of {e.warrant} is broken at {wid} ({kind})",
                        e.task,
                        [w.event_id for w in chain] + [e.event_id],
                    )
                )
            continue

        root = chain[-1]
        if not env.is_root(root.issuer) and once(("non-root-chain", e.warrant)):
            findings.append(
                Finding(
                    FAMILY,
                    "non-root-chain",
                    f"warrant chain of {e.warrant} terminates at {root.issuer},"
                    " which is not a declared root principal",
                    e.task,
                    [w.event_id for w in reversed(chain)] + [e.event_id],
                )
            )

        w = chain[0]
        if e.kind in ("tool_call", "message") and e.actor is not None and e.actor != w.subject:
            findings.append(
                Finding(
                    FAMILY,
                    "actor-warrant-mismatch",
                    f"{e.actor} used warrant {w.id}, which was issued to {w.subject}",
                    e.task,
                    [w.event_id, e.event_id],
                )
            )

        decl = env.agent(w.subject)
        if (
            decl is not None
            and decl.max_delegation_depth is not None
            and len(chain) > decl.max_delegation_depth
            and once(("depth-exceeded", w.id))
        ):
            findings.append(
                Finding(
                    FAMILY,
                    "depth-exceeded",
                    f"warrant {w.id} sits {len(chain)} hops from root; envelope allows"
                    f" {decl.max_delegation_depth} for {w.subject}",
                    e.task,
                    [x.event_id for x in reversed(chain)],
                )
            )
    return findings
