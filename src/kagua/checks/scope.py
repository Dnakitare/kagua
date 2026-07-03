"""Scope family: every tool_call within its warrant's scope; scope never
widens across a delegation hop; no grant exceeds the agent's declared
envelope scope.

On warrant-less (lossy) traces this degrades to a point check of each call
against the envelope declaration for its actor. The verdict's coverage
section reports the degradation; the check never silently passes.
"""
from __future__ import annotations

from ..envelope import Envelope, scope_covers, scope_widening
from ..trace import Trace
from . import Finding

FAMILY = "Scope"


def check(trace: Trace, env: Envelope) -> list[Finding]:
    findings: list[Finding] = []

    for e in trace.events:
        if e.kind != "tool_call":
            continue
        w = trace.warrants.get(e.warrant) if e.warrant else None
        if w is not None:
            if not scope_covers(w.tools, e.tool):
                findings.append(
                    Finding(
                        FAMILY,
                        "call-outside-warrant-scope",
                        f"{e.actor} called {e.tool}, not in scope of warrant {w.id}",
                        e.task,
                        [w.event_id, e.event_id],
                    )
                )
        else:
            decl = env.agent(e.actor)
            if decl is not None and not scope_covers(decl.tools, e.tool):
                findings.append(
                    Finding(
                        FAMILY,
                        "call-outside-declared-scope",
                        f"{e.actor} called {e.tool}, outside its declared envelope scope"
                        " (no warrant in trace; point check only)",
                        e.task,
                        [e.event_id],
                    )
                )

    for w in trace.warrants.values():
        if w.parent_warrant is not None:
            parent = trace.warrants.get(w.parent_warrant)
            if parent is not None:
                widened = scope_widening(w.tools, parent.tools)
                if widened:
                    findings.append(
                        Finding(
                            FAMILY,
                            "scope-widened-across-hop",
                            f"delegation {w.id} to {w.subject} widens scope beyond parent"
                            f" {parent.id}: +{', '.join(widened)}",
                            w.task,
                            [parent.event_id, w.event_id],
                            details={"widened": widened},
                        )
                    )
        decl = env.agent(w.subject)
        if decl is not None:
            widened = scope_widening(w.tools, decl.tools)
            if widened:
                findings.append(
                    Finding(
                        FAMILY,
                        "grant-exceeds-envelope",
                        f"warrant {w.id} grants {w.subject} more than its declared envelope"
                        f" scope: +{', '.join(widened)}",
                        w.task,
                        [w.event_id],
                        details={"widened": widened},
                    )
                )
    return findings
