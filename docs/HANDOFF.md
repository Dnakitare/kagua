# Kagua — Claude Code Handoff

**Read order:**
1. `kagua-user-stories.md` — north star, non-goals, personas. Section 0 governs all design decisions.
2. `kagua-spec.md` — product spec. Sections 9–10 contain decided architecture (ingestion tiers) and adversarial-review constraints; treat them as binding.

**Build target: v0.1 only** (spec §4). Deliverables:
- JSONL trace schema + validator
- OTel GenAI adapter with honest lossy-ingest reporting (story A2)
- Envelope YAML parser + Lifetime, Scope, Principal checks
- `kagua check` with witness-set rendering + coverage grade (attested/qualified)
- GitHub Action
- Demo fixture: work-order trace where every call passes, composition fails (story A1 — this is the README)

**Acceptance = Epic A stories (A1–A3).** Explicitly out of scope: infer, Muhuri, report mode, trajectory subsumption, any UI.

**Binding design rules (spec §2):** deterministic checks only, replayable witnesses, causal ordering over wall clock, idempotency keys for retries, CEL for expressions, no silent pass on lossy input.

**Pre-publish blockers (before README goes public):** trademark/prior-art sweep on "Kagua"; prior-art check on framing language.

Language: Python, `pip install kagua`, Apache-2.0 or MIT.
