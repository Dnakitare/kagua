"""Terminal rendering of verdicts. Witness sets stay readable: the demo
promise is a violation you can read in the terminal in 25 lines or less."""
from __future__ import annotations

import sys

from .trace import Trace

MAX_WITNESS_EVENTS = 12

_STATUS_MARK = {
    "checked": "ok",
    "partial": "partial",
    "degraded": "degraded",
    "unverifiable": "unverifiable",
    "not_implemented": "n/a",
}


def _color(enabled: bool):
    def paint(code: str, s: str) -> str:
        return f"\033[{code}m{s}\033[0m" if enabled else s

    return paint


def _event_line(trace: Trace, event_id: str, marks: dict[str, str]) -> str:
    e = trace.by_id.get(event_id)
    if e is None:
        return f"    {event_id}  (event not in trace)"
    parts = [f"    {e.event_id:<6} {e.kind:<11}"]
    if e.kind == "delegation":
        parts.append(f"{e.actor} -> {e.subject}  [{e.warrant}]  scope={len((e.scope or {}).get('tools', []))} tools")
    elif e.kind == "tool_call":
        parts.append(f"{e.actor:<18} {e.tool}  [{e.warrant or 'no warrant'}]")
    elif e.kind in ("task_start", "task_end"):
        parts.append(f"{e.task}")
    else:
        parts.append(f"{e.actor or ''}  [{e.warrant or ''}]".rstrip(" []"))
    if e.summary:
        parts.append(f"- {e.summary}")
    line = "  ".join(parts)
    if event_id in marks:
        line += f"   <- {marks[event_id]}"
    return line


def render_verdict(verdict: dict, trace: Trace, use_color: bool | None = None) -> str:
    if use_color is None:
        use_color = sys.stdout.isatty()
    c = _color(use_color)
    out: list[str] = []

    findings = verdict["findings"]
    # only true when composition is the sole failing family
    point_checks_clean = not any(
        f["family"] in ("Lifetime", "Scope", "Principal") for f in findings
    )
    for f in findings:
        head = c("1;31", f"FAIL  {f['family']} / {f['rule']}")
        out.append(head)
        out.append(f"  {f['message']}")
        seq_events = (f.get("details") or {}).get("sequence_events", [])
        marks = {eid: f"forbidden[{i}]" for i, eid in enumerate(seq_events)}
        witness = f["witness"]
        shown = witness[:MAX_WITNESS_EVENTS]
        out.append(f"  witness ({len(witness)} events):")
        for eid in shown:
            out.append(_event_line(trace, eid, marks))
        if len(witness) > len(shown):
            out.append(f"    ... +{len(witness) - len(shown)} more events (see --json output)")
        if f["family"] == "Composition" and point_checks_clean:
            out.append(
                "  " + c("2", "every event above passed its own Lifetime/Scope/Principal check;"
                          " the composition is the violation")
            )
        out.append("")

    for inv in verdict["unchecked_invariants"]:
        out.append(
            c("1;33", f"UNCHECKED  invariant '{inv['kind']}' is not evaluated in v0.1")
            + " (declared in envelope; not silently passed)"
        )
    if verdict["unchecked_invariants"]:
        out.append("")

    grade = verdict["grade"]
    grade_str = c("1", grade.upper())
    out.append(f"coverage: {grade_str} - {verdict['grade_reasons'][0]}")
    fam = verdict["families"]
    fam_bits = []
    for name, info in fam.items():
        fam_bits.append(f"{name} {_STATUS_MARK.get(info['status'], info['status'])}")
    out.append("families: " + "  |  ".join(fam_bits))
    for name, info in fam.items():
        if info["status"] in ("degraded", "unverifiable") and info["detail"]:
            out.append(f"  {name}: {info['detail']}")

    if findings:
        out.append(c("1;31", f"verdict: FAIL ({len(findings)} finding{'s' if len(findings) != 1 else ''})"))
    else:
        out.append(c("1;32", "verdict: PASS") + f" ({grade})")
        if grade == "qualified":
            out.append(
                c("2", "  a qualified pass covers only the visible trace; it is not a clean bill")
            )
    return "\n".join(out)
