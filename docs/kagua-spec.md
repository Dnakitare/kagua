# KAGUA — Authority Verification Harness for AI Agents

*Working name: "kagua" (Swahili: to inspect/audit) — fits the Mlinzi/Muhuri family. Rename freely.*

**One-liner:** Unit tests assert your agent did the right thing. Kagua asserts it was ever *allowed* to.

**Category:** CI harness + trace verifier. Not a gateway, not runtime enforcement, not an eval framework. It replays agent traces against declared authority envelopes and fails the build — or produces a signed certificate — when the *composition* of actions exceeds what any principal authorized, even though every individual call passed its check.

---

## 1. The core object model

Three artifacts, all files, all diffable in git:

### 1.1 Trace (input)
A DAG of events. Canonical internal format is JSONL, one event per line:

```json
{"event_id":"e17","ts":"2026-07-02T14:03:11Z","kind":"tool_call",
 "actor":"agent:triage-1","tool":"jira.create_ticket",
 "args_digest":"sha256:...","warrant":"w_8f2","parent":"e16",
 "task":"t_workorder_442","result":"ok"}
```

Event kinds: `delegation` (authority granted), `tool_call`, `task_start`, `task_end`, `token_issue`, `token_revoke`, `message` (agent↔agent).

Adapters normalize external formats into this:
- **OTel GenAI semantic conventions** (priority 1 — the ecosystem standard)
- **MCP gateway logs** (invocation logs from TrueFoundry-style gateways are near-perfect input)
- **Native SDK shim** (thin Python decorator for teams with nothing)

### 1.2 Envelope (the authority declaration)
YAML, human-writable, machine-inferable:

```yaml
principals:
  - id: human:daniel
    root: true
agents:
  - id: agent:triage-1
    delegated_by: human:daniel
    scope:
      tools: [jira.read, jira.create_ticket, slack.post:channel=ops]
    lifetime: task          # authority dies with the task
    max_delegation_depth: 1
invariants:
  - kind: budget
    metric: tool_calls{tool=~"jira.*"}
    max: 20
    per: task
  - kind: forbidden_composition
    sequence: [gmail.read, "http.post:external"]   # read-then-exfil
    within: task
  - kind: conservation
    assert: "sum(payments.amount) <= warrant.budget_usd"
```

### 1.3 Verdict (output)
- **CI mode:** exit code + failing "authority tests," each with a *witness set* — a greedily-shrunk slice of the trace DAG sufficient to demonstrate the violation. (Not "minimal": true minimality for aggregate rules is subset-sum-hard. Promise sufficiency + greedy shrink, deliver reliably.)
- **Every verdict carries a coverage grade:** `attested` (input source can prove completeness — e.g., all egress flowed through an MCP gateway) or `qualified` (violations found are real; absence of violations proves nothing beyond the visible trace). A pass on partial input must never read as a clean bill.
- **Report mode:** signed JSON + rendered PDF mapping each finding to OWASP Agentic Top 10 IDs (ASI-03 Tool Misuse, ASI-04 Delegated Trust Exploitation) and SOC 2 CC-series controls. This is the compliance artifact — the same engine, pointed at production logs instead of CI traces.

---

## 2. The invariant engine — six gap families as check classes

| Gap family | Check (deterministic) | Version |
|---|---|---|
| **Lifetime** | No event references a warrant outside its validity window; no activity after `task_end` (zombie authority) | v0.1 |
| **Scope/Intent** | Every `tool_call` ⊆ the transitive scope of its warrant chain; scope never *widens* across delegation hops | v0.1 |
| **Principal** | Every event's warrant chain terminates at a `root: true` principal; no orphaned authority | v0.1 |
| **Provenance** | Every delegation hop is present in the trace (v0.2: cryptographically signed via Muhuri — missing/unverifiable hop = failure, not warning) | v0.2 / v0.3 |
| **Composition** | Declarative rules: `budget`, `forbidden_composition`, `conservation` expressions evaluated over the whole task DAG | v0.2 |
| **Point/Trajectory** | Hardest. v0 approximation: trajectory must match one of the declared `allowed_plans` (sequence patterns); full plan-subsumption deferred | v0.3+ |

Design rules:
1. **Every check is deterministic and produces a replayable witness.** No ML in the verifier. The LLM's only role is in `infer` and in explaining findings — never in deciding pass/fail. That's the moat vs. every anomaly-scoring vendor: their output is a suspicion, yours is a proof.
2. **Causal order beats wall clock.** Ordering comes from parent links (happens-before over the DAG); timestamps are secondary with a configurable tolerance window. Distributed clocks lie; Lifetime checks that trust them produce false positives that kill adoption.
3. **Retries need identity.** Events carry an optional idempotency key; retried calls collapse to one logical action for budget/composition purposes. Without this, every LangChain retry looks like a budget violation.
4. **Expressions are CEL, not a homegrown DSL.** `conservation` asserts use Google's Common Expression Language — already the policy-expression lingua franca (Kubernetes admission, Envoy). We invent check *semantics* (trajectory-level), never expression *syntax*.

---

## 3. CLI surface

```
kagua ingest  --adapter otel ./traces/raw --out traces.jsonl
kagua infer   traces.jsonl -o envelope.yaml     # proposes the envelope it observed
kagua check   traces.jsonl --envelope envelope.yaml [--fail-on any|composition|...]
kagua diff    envelope.yaml traces.jsonl        # authority drift since last run
kagua report  traces.jsonl --envelope envelope.yaml --map owasp-asi,soc2 -o report.pdf
```

**`infer` is the adoption wedge — with a guard against rubber-stamping.** Teams haven't declared authority envelopes; nobody will hand-write YAML on day one. `infer` watches traces and emits the envelope it observed ("agent:triage-1 used 4 tools, max depth 1, ≤12 jira calls/task"). But an envelope inferred from behavior *blesses* that behavior — including any laundering already present. Two mitigations, both mandatory:
1. `infer` runs the six-family checks against its own output and annotates anything structurally suspect (`# WARNING: observed delegation depth 3 — confirm this is intended`) rather than silently baking it in.
2. The inferred envelope is delivered as a **pull request, never auto-committed.** The human review of that PR *is* the principal's declaration of intent — the missing ceremony the whole authority model requires. Position this explicitly: envelope review is where a human root principal first says "this is what I authorize."

From then on `check` catches drift. Zero-config first value in under five minutes, without laundering the baseline.

Plus a **GitHub Action** (`kagua/check-action`) and a **pytest plugin** (`@authority_test` — record an agent run as a fixture, assert invariants in-line).

---

## 4. v0.1 — build scope (target: 2–3 weeks in Claude Code)

**In:**
1. JSONL trace schema + validator
2. OTel GenAI adapter (even if lossy — document what's missing)
3. Envelope YAML parser + Lifetime, Scope, Principal checks
4. `check` with counterexample rendering (terminal + JSON)
5. GitHub Action
6. **The demo that sells it:** the Castellan maintenance work-order scenario as a fixture — a 40-event trace where *every individual call is authorized* and `kagua check` fails it on a Composition violation (use one hardcoded `forbidden_composition` rule even though the general engine is v0.2). README leads with this trace.

**Out (explicitly):** infer, Muhuri signing, report mode, trajectory subsumption, any UI.

**Repo shape:** Python (matches Muhuri), `pip install kagua`, MIT or Apache-2.0. Monorepo later if Rust port lands.

## 5. Sequencing after v0.1

- **v0.2:** `infer`, Composition rule engine (budget/forbidden/conservation), pytest plugin, MCP-gateway log adapter
- **v0.3:** Muhuri integration — signed delegation hops turn Provenance from "trust the log" into "verify the chain." This is the point where Kagua and Muhuri become one story: Muhuri makes authority *provable*, Kagua makes it *checked*.
- **v0.4:** `report` mode with OWASP-ASI / SOC 2 mapping → the paid artifact

## 6. Revenue surfaces (same engine)

1. **OSS harness** — free, bottom-up, engineers, no procurement
2. **Audit engagements** — `kagua report` over a customer's production logs; $10–30K, sold to whoever owns the SOC 2 renewal (EU AI Act high-risk obligations hit Aug 2, 2026; Colorado enforceable since June — the deadline pressure is real and current)
3. **Later:** hosted drift monitoring (continuous `diff` against committed envelopes)

## 7. Validation gates (kill criteria)

- **Gate 1 (week 4):** 3 external users have run `check` on their own real traces (not the demo). If zero after genuine distribution effort → the ingestion boundary is wrong; fix adapters or stop.
- **Gate 2 (week 10):** 1 design partner with a SOC 2 renewal ≤ 6 months out agrees to a paid or heavily-discounted report engagement. If no one converts → the compliance surface is premature; stay OSS-only or stop.

## 8. Known risks

- **Trace availability** is the whole game. Teams without structured traces can't be customers yet. Mitigation: the SDK shim + riding MCP gateway adoption (their logs are your input; gateways are channel, not competition).
- **False-positive grind:** the "legitimate exceptions" library must be earned per framework (LangChain's internal retries look like scope violations, etc.). Budget real time for this after Gate 1.
- **Point/Trajectory over-promise:** do not market plan-subsumption before it exists. v0.1 honestly covers 3 of 6 families; say so.
- **Naming/prior-art:** run the same prior-art sweep done for "authority laundering" before publishing the README framing.

---

## 9. Ingestion strategy (decided)

**Canonical model owns semantics; adapters degrade honestly; no forks.**

| Tier | Source | Fidelity | Notes |
|---|---|---|---|
| 1 | **MCP gateway invocation logs** | Highest | Gateways sit exactly where authority is exercised: tool, identity, payload, per-call. Environments that route *all* egress through a gateway can produce **attested** verdicts. Gateways are channel, not competition. |
| 2 | **Native SDK shim** | High | Emits standard OTel GenAI spans **plus** namespaced attributes: `kagua.warrant_id`, `kagua.delegation.parent`, `kagua.principal_root`, `kagua.args_digest`. Datadog ignores them; Kagua reads them; nothing breaks. |
| 3 | **Plain OTel GenAI / OpenInference / Langfuse exports** | Lossy | Authority-blind. Ingestible, but Provenance and Principal checks return `unverifiable`, and the verdict is `qualified`. Never let lossy input produce a silent pass. |

**Sampling is the disqualifying gap, not the schema.** OTel tolerates loss because observability does; verification doesn't — a sampled trace cannot prove absence of a violation. The coverage grade (§1.3) is the containment: lossy or sampled input degrades the verdict's *claims*, never its *correctness*.

**Standards play instead of forking:** if the harness gets traction, take the `kagua.*` attribute set to the OTel GenAI SIG as the delegation-semantics proposal. Becoming the standard's authority layer beats maintaining a fork of it. **Output side:** emit findings as OCSF security events so SIEMs and compliance stacks consume verdicts natively.

## 10. Adversarial review — findings folded into the design

Interrogated before build. Each finding either changed the spec (marked ✎, already applied above) or is a standing constraint.

**F1 — "The verifier verifies the log, not reality."** ✎ Deepest attack. An agent acting outside instrumented paths (raw shell, direct API) is invisible; a pass on partial input is *worse* than no tool — it manufactures false assurance. Resolution: attested vs. qualified verdicts (§1.3), with attestation grounded in an enforcement point (gateway-routed egress), not self-report. This is honest differentiation, not weakness: SOC 2 assessors live on scoped evidence; a tool that states its own coverage boundary is *more* credible to them, not less.

**F2 — "infer launders the baseline."** ✎ Resolved via warning-annotated inference + envelope-as-PR (§3). Side effect: the PR review ceremony supplies the principal-intent declaration the taxonomy always needed.

**F3 — "Minimal counterexamples are NP-hard for aggregates."** ✎ Downgraded to greedily-shrunk witness sets (§1.3).

**F4 — "Real traces break determinism."** ✎ Causal ordering primary, timestamps secondary; idempotency keys for retries (§2 design rules 2–3). The exceptions library (per-framework quirks: LangChain retries, incident-to-style rollups in any domain) is a first-class asset with its own directory in the repo, versioned and tested — it is the earned moat, treat it like one.

**F5 — "Why not just OPA or Cedar?"** Standing positioning line, put it in the README: **Cedar/OPA decide the point; Kagua verifies the trajectory.** Point-in-time policy engines answer "may this call proceed?" — which is precisely the layer authority laundering defeats, because every point answer is *yes*. Kagua evaluates the composed trajectory after (or in CI, before) the fact. Complementary, not competitive; a team running Cedar is a *better* Kagua prospect because their per-call hygiene makes composition the only remaining gap.

**F6 — "A gateway vendor clones this in a quarter."** Four-layer defense, in order of durability: (a) **structural neutrality** — a gateway auditing its own enforcement is the fox counting hens; assessors want independent verification, and independence cannot be retrofitted by an enforcement vendor; (b) **replayable signed verdicts** — any third party can re-run the check over the same input and get the same answer, which is the trust primitive certificates need; (c) **Muhuri-signed provenance** (v0.3) — cryptographic delegation chains are an ecosystem, not a feature, and hard to retrofit; (d) the exceptions library (F4). The taxonomy-to-OTel-SIG play (§9) converts first-mover into standard-setter.

**F7 — "Does CI even have the pain? Violations happen in prod."** Partially conceded; reframed as **two loops, prod-first in value, CI-first in adoption.** The drift/report loop over production traces is where money and stakes live (compliance deadlines, real credentials). The CI loop over recorded/synthetic traces catches *design* regressions — a prompt edit or tool-wiring change that widens effective authority — before deploy. Market the prod loop; distribute via the CI loop.

**F8 — "Certificate" implies liability.** Standing constraint on all report-mode language: the artifact is **evidence, not attestation.** It signs "these checks passed over this input at this coverage grade" — a pen-test-shaped finding, never an opinion of compliance (which only the assessor renders, and which a non-CPA cannot legally offer for SOC 2 anyway). Word choice in templates: "findings," "evidence package," never "certified compliant."

**F9 — Scale.** Long-running fleets produce large traces. Checks are designed for streaming evaluation with per-task windowing; nothing in the six families requires whole-history residency except explicitly cross-task conservation rules, which declare their window. Constraint, not blocker; note in architecture, don't over-build in v0.1.

**F10 — Names.** Prior-art sweep on "authority verification harness" framing + trademark check on "Kagua" before the README goes public. Same discipline as the authority-laundering/Chris Hood episode — cheap now, expensive later.

### What survives the review — the honest core

Strip away everything contestable and three claims remain, each independently defensible:
1. **Point-in-time authorization cannot detect composed abuse** (the six families are the proof structure).
2. **A deterministic, replayable check over a causally-ordered trace can** — for declared invariants, at declared coverage.
3. **Nobody ships that artifact today** — gateways enforce, observability describes, evals score quality; none verify authority composition, and the regulatory calendar (EU AI Act Aug 2026, SOC 2 agent controls) is manufacturing demand for exactly this evidence shape.

If any of the three breaks, stop. Gate 1 tests #3's adoption half; Gate 2 tests its willingness-to-pay half; #1 and #2 are testable in the v0.1 demo fixture itself.
