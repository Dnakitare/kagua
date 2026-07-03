# KAGUA — North Star & User Stories

*Companion to `kagua-spec.md`. The spec says what to build; this says why, for whom, and what "done" means from the outside.*

---

## 0. The greater goal, crystallized

**Mission (one sentence):**
> No autonomous action without a provable chain of authority to a human principal — and no composition of actions that escapes what any principal ever authorized.

**Why it matters:** Software ate the world by executing decisions; agents are now *making* them. Every governance regime — enterprise, regulatory, national — assumes authority can be traced and bounded. Agents break that assumption not by defeating checks but by composing past them. Whoever makes composed authority *verifiable* builds the trust layer the agent economy runs on.

**The stack this project belongs to (the through-line):**

| Layer | Artifact | Status |
|---|---|---|
| Theory | Authority-laundering taxonomy (six gap families) | Written, essay pending prior-art reframe |
| Provable credentials | **Muhuri** — cryptographic delegation chains | Library built; cross-lang test vectors next |
| **Verification** | **Kagua** — this product: replay traces, prove/refute composition | Spec'd, building |
| Enforcement | **Mlinzi** — capability broker, runtime | Architecture spec'd, deferred |
| Institutional | Health-data governance enforcement (Africa CDC gap), sovereign infrastructure | Horizon |

Kagua is the *wedge* layer deliberately: verification is adoptable without permission (read logs, render verdicts), while enforcement requires trust you haven't earned yet. Verification earns it.

**North-star metric:** number of agent actions per month covered by an `attested` Kagua verdict. Everything else (stars, engagements, revenue) is a proxy.

**Non-goals (guard rails against drift):**
- Not an eval framework. We never score answer *quality*.
- Not a gateway. We never sit in the request path (until Mlinzi, deliberately, later).
- Not an anomaly detector. If a check can't produce a replayable witness, it doesn't ship.

---

## 1. Personas

- **P1 — Amara, agent platform engineer** at a 60-person AI-native company. Ships multi-agent workflows on LangChain + MCP. Owns "don't let the agents do something insane."
- **P2 — Dev, security engineer** at a mid-size fintech. Inherited 40 agents nobody inventoried. Has an MCP gateway; drowning in its logs.
- **P3 — Priya, compliance lead** (owns SOC 2 renewal, watching EU AI Act). Needs evidence for the assessor, not another dashboard.
- **P4 — the external assessor** auditing P3's company. Trusts nothing she can't independently re-derive.
- **P5 — OSS tinkerer** who found the repo from the README demo. Five minutes of patience, max.
- **P6 — Gateway vendor PM** looking for differentiation. Potential channel, potential cloner.
- **P7 — incident responder**, day 2 of "the agent did *what* to the billing system?"

---

## 2. User stories with acceptance criteria

### Epic A — First contact (v0.1) — *these are the v0.1 acceptance tests*

**A1.** As **P5**, I run the README demo (`kagua check fixtures/workorder/`) and within 5 minutes I see a trace where *every individual call is authorized* fail on a Composition violation, with a witness set I can read in the terminal.
✓ Done when: fresh clone → failing check ≤ 5 min, no config; witness renders ≤ 25 lines; README leads with the output screenshot.

**A2.** As **P1**, I point `kagua ingest --adapter otel` at my existing OTel export and get a canonical JSONL trace plus a plain-language report of what the adapter *couldn't* recover (missing delegation records, redacted args).
✓ Done when: lossy input produces a `qualified` note listing which of the six families are checkable, which return `unverifiable`. Never a silent pass.

**A3.** As **P1**, I write a 20-line `envelope.yaml` for one agent and wire `kagua check` into GitHub Actions so a prompt or tool-wiring change that widens effective authority fails the PR.
✓ Done when: the demo repo includes a PR that changes one tool scope and turns CI red with a Scope-family witness.

### Epic B — Envelope lifecycle (v0.2)

**B1.** As **P1**, I run `kagua infer` on a week of traces and receive an envelope **as a pull request**, with structurally suspect observations annotated (`# WARNING: observed delegation depth 3`), so my approval is an explicit act of authorization — not a rubber stamp of whatever the agents already did.
✓ Done when: infer output always self-checks against the six families; auto-commit is impossible by design.

**B2.** As **P1**, after merging the envelope, `kagua diff` in nightly CI tells me only about *drift* — new tools, widened scopes, deeper chains — with zero noise from retries or clock skew.
✓ Done when: LangChain retry storms and 5s clock skew produce no findings on the reference fixtures (the exceptions library has regression tests).

**B3.** As **P2**, I feed my MCP gateway's invocation logs to Kagua and get **attested** verdicts, because the gateway is the enforcement point for all egress.
✓ Done when: attestation requires declared enforcement-point coverage; absent that, verdicts are marked `qualified` and say why.

### Epic C — Money loop (v0.3–v0.4)

**C1.** As **P3**, I hand my assessor a Kagua evidence package: findings mapped to OWASP ASI-03/04 and SOC 2 CC-series, coverage grade on every claim, "findings/evidence" language throughout — never "certified compliant."
✓ Done when: the report template survives review by one real assessor (design-partner gate).

**C2.** As **P4**, I re-run `kagua check` on the same trace bundle and envelope and reproduce the verdict bit-for-bit, verifying the signature over inputs + outputs.
✓ Done when: verdicts are content-addressed and replayable by a third party with no Kagua account or service dependency.

**C3.** As **P7**, during an incident I run `kagua check` over the last 72h of prod traces with the committed envelope and get the witness set for *when authority first leaked* — the delegation hop where scope widened — instead of grepping raw logs for a day.
✓ Done when: witness includes the full warrant chain from violating event back to root principal, renderable as a timeline.

**C4.** As **P2**, Kagua emits findings as OCSF events into my SIEM so authority violations land in the same queue as everything else.
✓ Done when: one documented Splunk/Datadog ingestion path exists.

### Epic D — Ecosystem (v0.3+, opportunistic)

**D1.** As **P6**, I bundle Kagua as the independent verification layer over my gateway's logs — I enforce, Kagua proves — because my customers' assessors won't take my self-audit.
✓ Done when: one gateway vendor co-marketing conversation converts to a documented integration. (Channel test; also the F6 moat test.)

**D2.** As **P1** on the Muhuri SDK, my delegation hops are signed, so Kagua's Provenance checks return *cryptographically verified* rather than "trust the log" — and forged or missing hops fail loudly.
✓ Done when: the Muhuri fixture demonstrates a tampered hop turning a pass into a Provenance failure.

**D3.** (Horizon, not scheduled) As a **data-governance authority** with a policy framework but no enforcement mechanism, I can require Kagua-shaped evidence — replayable, coverage-graded, independent — from entities processing data under my framework. *This is the Africa CDC shape. It is why non-goals matter: the institutional buyer needs a verifier with no stake in the systems it verifies.*

---

## 3. Story-to-gate mapping

- **Gate 1 (wk 4, 3 external users on real traces):** tests A1→A2. If people run the demo but never ingest their own traces, the failure is the adapter, not the idea.
- **Gate 2 (wk 10, one paid/discounted design partner):** tests C1. Priya is the buyer; the assessor's acceptance (C2) is what she's paying for.
- **North-star check (quarterly):** attested-action coverage growing? If all growth is `qualified`, the enforcement-point strategy (gateways, Muhuri) is stalling and needs attention before revenue does.
