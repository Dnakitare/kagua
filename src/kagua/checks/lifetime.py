"""Lifetime family: no event references a warrant outside its validity window.

Covers: use before issuance, use after revocation, task-scoped warrants used
in another task, and activity after task_end (zombie authority). All ordering
is causal-first; concurrent-within-tolerance events never fire a finding.
"""
from __future__ import annotations

from ..envelope import Envelope
from ..trace import Trace
from . import Finding

FAMILY = "Lifetime"


def check(trace: Trace, env: Envelope) -> list[Finding]:
    findings: list[Finding] = []
    if not trace.warrants:
        return findings  # unverifiable; the verdict's coverage section says so

    for e in trace.events:
        if e.warrant is None or e.kind == "delegation":
            continue
        w = trace.warrants.get(e.warrant)
        if w is None:
            continue  # orphaned authority is a Principal finding
        issued = trace.by_id[w.event_id]

        if trace.happens_before(e, issued):
            findings.append(
                Finding(
                    FAMILY,
                    "use-before-issue",
                    f"{e.event_id} references warrant {w.id} before it was issued",
                    e.task,
                    [e.event_id, w.event_id],
                )
            )

        if w.revoked_by is not None:
            revoke = trace.by_id[w.revoked_by]
            if trace.happens_before(revoke, e):
                findings.append(
                    Finding(
                        FAMILY,
                        "use-after-revoke",
                        f"{e.event_id} uses warrant {w.id} after it was revoked in {revoke.event_id}",
                        e.task,
                        [w.event_id, revoke.event_id, e.event_id],
                    )
                )

        if w.lifetime == "task" and w.task is not None:
            if e.task is not None and e.task != w.task:
                findings.append(
                    Finding(
                        FAMILY,
                        "cross-task-use",
                        f"{e.event_id} (task {e.task}) uses warrant {w.id}, whose authority died with task {w.task}",
                        e.task,
                        [w.event_id, e.event_id],
                    )
                )
            end = trace.task_end.get(w.task)
            if end is not None and trace.happens_before(end, e):
                findings.append(
                    Finding(
                        FAMILY,
                        "zombie-authority",
                        f"{e.event_id} acts under warrant {w.id} after {w.task} ended (zombie authority)",
                        e.task,
                        [w.event_id, end.event_id, e.event_id],
                    )
                )
    return findings
