"""Check registry. Every check is deterministic and produces a replayable
witness: an ordered slice of the trace sufficient to demonstrate the
violation. No ML anywhere in this package, ever."""
from __future__ import annotations

from dataclasses import dataclass, field

from ..envelope import Envelope, Invariant
from ..trace import Trace

FAMILIES = ("Lifetime", "Scope", "Principal", "Provenance", "Composition", "Trajectory")


@dataclass
class Finding:
    family: str
    rule: str
    message: str
    task: str | None
    witness: list[str]  # event ids, rendered in timestamp order
    details: dict = field(default_factory=dict)

    def to_json(self) -> dict:
        return {
            "family": self.family,
            "rule": self.rule,
            "message": self.message,
            "task": self.task,
            "witness": self.witness,
            **({"details": self.details} if self.details else {}),
        }


def run_all(trace: Trace, env: Envelope) -> tuple[list[Finding], list[Invariant]]:
    """Run every v0.1 check. Returns (findings, invariants we could not check).

    Unchecked invariants are surfaced in the verdict, never dropped:
    a declared rule that silently isn't evaluated would be a silent pass.
    """
    from . import composition, lifetime, principal, scope

    findings: list[Finding] = []
    findings.extend(lifetime.check(trace, env))
    findings.extend(scope.check(trace, env))
    findings.extend(principal.check(trace, env))
    comp_findings, unchecked = composition.check(trace, env)
    findings.extend(comp_findings)
    return findings, unchecked
