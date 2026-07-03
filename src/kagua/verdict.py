"""Verdict assembly: findings + coverage grade + per-family checkability.

Two grades, per spec section 1.3:
  attested  - the input source can prove completeness (a declared enforcement
              point covered all egress). v0.1 only grants this when the trace
              meta declares an enforcement point AND complete coverage.
  qualified - violations found are real; absence of violations proves nothing
              beyond the visible trace. A pass on partial input must never
              read as a clean bill.
"""
from __future__ import annotations

import hashlib

from . import __version__
from .checks import Finding
from .envelope import Envelope, Invariant
from .trace import Trace


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def family_coverage(trace: Trace, env: Envelope) -> dict[str, dict]:
    has_warrants = bool(trace.warrants)
    comp_declared = any(i.kind == "forbidden_composition" for i in env.invariants)
    cov: dict[str, dict] = {}
    cov["Lifetime"] = (
        {"status": "checked", "detail": ""}
        if has_warrants
        else {
            "status": "unverifiable",
            "detail": "no delegation records in trace; warrant validity windows unknowable",
        }
    )
    cov["Scope"] = (
        {"status": "checked", "detail": ""}
        if has_warrants
        else {
            "status": "degraded",
            "detail": "no warrant chains; each call point-checked against envelope declarations only",
        }
    )
    cov["Principal"] = (
        {"status": "checked", "detail": ""}
        if has_warrants
        else {
            "status": "unverifiable",
            "detail": "no delegation records in trace; chains to a root principal cannot exist",
        }
    )
    cov["Provenance"] = {
        "status": "not_implemented",
        "detail": "v0.2 (Muhuri-signed delegation hops)",
    }
    cov["Composition"] = (
        {"status": "partial", "detail": "forbidden_composition rules only in v0.1"}
        if comp_declared
        else {
            "status": "partial",
            "detail": "forbidden_composition only in v0.1; envelope declares none",
        }
    )
    cov["Trajectory"] = {"status": "not_implemented", "detail": "v0.3+"}
    return cov


def build_verdict(
    trace: Trace,
    env: Envelope,
    findings: list[Finding],
    unchecked: list[Invariant],
    trace_path: str,
    envelope_path: str,
) -> dict:
    grade_reasons: list[str] = []
    meta = trace.meta
    if meta.enforcement_point and meta.coverage == "complete":
        grade = "attested"
        grade_reasons.append(
            f"source declares enforcement point '{meta.enforcement_point}' with complete coverage"
        )
    else:
        grade = "qualified"
        if not meta.enforcement_point:
            grade_reasons.append("no enforcement point declared for this trace")
        if meta.coverage != "complete":
            grade_reasons.append(f"trace coverage is '{meta.coverage}', not 'complete'")
        grade_reasons.append(
            "findings are real; absence of findings proves nothing beyond the visible trace"
        )

    return {
        "kagua_version": __version__,
        "inputs": {
            "trace": {"path": trace_path, "sha256": _sha256(trace_path)},
            "envelope": {"path": envelope_path, "sha256": _sha256(envelope_path)},
        },
        "grade": grade,
        "grade_reasons": grade_reasons,
        "families": family_coverage(trace, env),
        "unchecked_invariants": [
            {"kind": i.kind, "params": i.params} for i in unchecked
        ],
        "findings": [f.to_json() for f in findings],
        "passed": not findings,
    }
