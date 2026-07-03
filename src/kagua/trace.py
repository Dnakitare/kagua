"""Trace model: causal ordering, warrant table, task boundaries.

Ordering is causal first (parent links, happens-before over the DAG);
wall-clock timestamps are a fallback with a tolerance window, because
distributed clocks lie and Lifetime checks that trust them produce
false positives.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .events import Event, TraceMeta

DEFAULT_CLOCK_TOLERANCE_S = 5.0


@dataclass
class Warrant:
    id: str
    issuer: str
    subject: str
    tools: list[str]
    lifetime: str
    task: str | None
    parent_warrant: str | None
    event_id: str  # the delegation event that issued it
    revoked_by: str | None = None  # event_id of the token_revoke, if any


class Trace:
    def __init__(
        self,
        events: list[Event],
        meta: TraceMeta | None = None,
        clock_tolerance_s: float = DEFAULT_CLOCK_TOLERANCE_S,
    ):
        self.events = events
        self.meta = meta or TraceMeta()
        self.tolerance = clock_tolerance_s
        self.by_id: dict[str, Event] = {e.event_id: e for e in events}

        self.warrants: dict[str, Warrant] = {}
        for e in events:
            if e.kind == "delegation":
                self.warrants[e.warrant] = Warrant(
                    id=e.warrant,
                    issuer=e.actor,
                    subject=e.subject,
                    tools=list((e.scope or {}).get("tools", [])),
                    lifetime=e.lifetime or "task",
                    task=e.task,
                    parent_warrant=e.parent_warrant,
                    event_id=e.event_id,
                )
        for e in events:
            if e.kind == "token_revoke":
                w = self.warrants.get(e.warrant)
                if w is not None and w.revoked_by is None:
                    w.revoked_by = e.event_id

        self.task_start: dict[str, Event] = {}
        self.task_end: dict[str, Event] = {}
        for e in events:
            if e.kind == "task_start":
                self.task_start.setdefault(e.task, e)
            elif e.kind == "task_end":
                self.task_end.setdefault(e.task, e)

        # ancestor sets over single-parent links, computed iteratively
        self._ancestors: dict[str, frozenset[str]] = {}
        for e in events:
            self._compute_ancestors(e.event_id)

    def _compute_ancestors(self, event_id: str) -> frozenset[str]:
        chain: list[str] = []
        cur: str | None = event_id
        while cur is not None and cur not in self._ancestors:
            if cur in chain:  # parent cycle; validator flags dangling, not cycles
                break
            chain.append(cur)
            ev = self.by_id.get(cur)
            cur = ev.parent if ev is not None else None
        base = self._ancestors.get(cur, frozenset()) if cur else frozenset()
        acc = set(base)
        if cur:
            acc.add(cur)
        for eid in reversed(chain):
            self._ancestors[eid] = frozenset(acc)
            acc.add(eid)
        return self._ancestors[event_id]

    def is_ancestor(self, a: Event, b: Event) -> bool:
        """True if a is a proper causal ancestor of b."""
        return a.event_id in self._ancestors.get(b.event_id, frozenset())

    def happens_before(self, a: Event, b: Event) -> bool:
        """Causal order primary; timestamps secondary within tolerance.

        Concurrent events with timestamps inside the tolerance window are
        deliberately unordered: no check may fire on them.
        """
        if a.event_id == b.event_id:
            return False
        if self.is_ancestor(a, b):
            return True
        if self.is_ancestor(b, a):
            return False
        return (b.ts - a.ts).total_seconds() > self.tolerance

    def warrant_chain(self, warrant_id: str) -> tuple[list[Warrant], str | None]:
        """Walk parent_warrant links to the root grant.

        Returns (chain from leaf to root, problem). Problem is None,
        'missing:<id>' for a hop absent from the trace, or 'cycle:<id>'.
        """
        chain: list[Warrant] = []
        seen: set[str] = set()
        cur: str | None = warrant_id
        while cur is not None:
            if cur in seen:
                return chain, f"cycle:{cur}"
            seen.add(cur)
            w = self.warrants.get(cur)
            if w is None:
                return chain, f"missing:{cur}"
            chain.append(w)
            cur = w.parent_warrant
        return chain, None
