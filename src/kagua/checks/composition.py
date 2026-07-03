"""Composition family, v0.1 slice: forbidden_composition only.

A forbidden_composition invariant declares a sequence of tool patterns that
must never all occur, causally ordered, within one task, even though each
call is individually authorized. The general composition engine (budget,
conservation) is v0.2; any invariant kind we cannot evaluate is returned as
unchecked and surfaced in the verdict rather than silently passing.

Retries collapse by idempotency key: a retried call cannot match two slots
of the same sequence.
"""
from __future__ import annotations

from collections import defaultdict

from ..envelope import Envelope, Invariant, covers
from ..events import Event
from ..trace import Trace
from . import Finding

FAMILY = "Composition"


def check(trace: Trace, env: Envelope) -> tuple[list[Finding], list[Invariant]]:
    findings: list[Finding] = []
    unchecked = [i for i in env.invariants if i.kind != "forbidden_composition"]

    calls_by_task: dict[str, list[Event]] = defaultdict(list)
    for e in trace.events:
        if e.kind == "tool_call" and e.task is not None:
            calls_by_task[e.task].append(e)

    for inv in env.invariants:
        if inv.kind != "forbidden_composition":
            continue
        sequence: list[str] = inv.params["sequence"]
        for task, calls in sorted(calls_by_task.items()):
            matched = _match_sequence(trace, sorted(calls, key=lambda e: e.ts), sequence)
            if matched is None:
                continue
            ordering = _ordering_quality(trace, matched)
            message = (
                f"forbidden sequence [{' -> '.join(sequence)}] completed within {task};"
                " every call was individually authorized"
            )
            if "concurrent-within-tolerance" in ordering:
                message += (
                    "; order between some steps is within clock tolerance"
                    " (co-occurrence in the task is proven, exact order is not)"
                )
            findings.append(
                Finding(
                    FAMILY,
                    "forbidden_composition",
                    message,
                    task,
                    _witness(trace, task, matched),
                    details={
                        "sequence_events": [e.event_id for e in matched],
                        "ordering": ordering,
                    },
                )
            )
    return findings, unchecked


def _match_sequence(
    trace: Trace, calls: list[Event], sequence: list[str]
) -> list[Event] | None:
    """Greedy earliest match, scanning in timestamp order.

    A candidate for the next slot is rejected only when causality contradicts
    the claimed order (the candidate is a causal ancestor of the previous
    match). Requiring positive happens-before proof here would let the clock
    tolerance window suppress true positives: real agent loops fire tool
    calls milliseconds apart across disjoint traces, and a forbidden pair
    co-occurring in one task must not pass because clocks can't order it.
    Causal order still wins wherever it exists.
    """
    matched: list[Event] = []
    used_logical: set[str] = set()
    for e in calls:
        idx = len(matched)
        if idx == len(sequence):
            break
        if e.tool is None or not covers(sequence[idx], e.tool):
            continue
        if e.logical_id in used_logical:
            continue  # a retry of an already-matched call is the same action
        if matched and trace.happens_before(e, matched[-1]):
            continue  # causally contradicted: candidate provably precedes the previous step
        matched.append(e)
        used_logical.add(e.logical_id)
    return matched if len(matched) == len(sequence) else None


def _ordering_quality(trace: Trace, matched: list[Event]) -> list[str]:
    """Per adjacent pair: how the claimed order is established."""
    quality: list[str] = []
    for a, b in zip(matched, matched[1:]):
        if trace.is_ancestor(a, b):
            quality.append("causal")
        elif (b.ts - a.ts).total_seconds() > trace.tolerance:
            quality.append("clock")
        else:
            quality.append("concurrent-within-tolerance")
    return quality


def _witness(trace: Trace, task: str, matched: list[Event]) -> list[str]:
    """Sufficient slice: task boundary, the matched calls, and the delegation
    events granting each matched call's authority (to show every call was
    individually legitimate). Greedily small by construction."""
    ids: set[str] = set()
    start = trace.task_start.get(task)
    if start is not None:
        ids.add(start.event_id)
    for e in matched:
        ids.add(e.event_id)
        if e.warrant:
            chain, _ = trace.warrant_chain(e.warrant)
            ids.update(w.event_id for w in chain)
    return sorted(ids, key=lambda i: (trace.by_id[i].ts, i))
