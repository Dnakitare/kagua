# Kagua

**Unit tests assert your agent did the right thing. Kagua asserts it was ever allowed to.**

Kagua replays multi-agent traces against a declared authority envelope and fails the build when the *composition* of actions exceeds what any principal authorized, even though every individual call passed its own check.

![kagua check failing the work-order demo on a Composition violation](https://raw.githubusercontent.com/Dnakitare/kagua/main/docs/demo.svg)

<details>
<summary>Same output as text</summary>

```
$ kagua check fixtures/workorder/

FAIL  Composition / forbidden_composition
  forbidden sequence [vendors.get_quote -> payments.approve] completed within t_workorder_442; every call was individually authorized
  witness (6 events):
    e01    task_start   t_workorder_442  - WO-442: HVAC failure, Site 12
    e03    delegation   human:ops.manager -> agent:coordinator  [w_coord]  scope=6 tools  - root grant to coordinator
    e08    delegation   agent:coordinator -> agent:procurement  [w_proc]  scope=6 tools  - sub-delegate quote collection
    e13    tool_call    agent:procurement  vendors.get_quote  [w_proc]  - quote from acme-hvac: $8,400   <- forbidden[0]
    e28    delegation   agent:coordinator -> agent:finance  [w_fin]  scope=4 tools  - sub-delegate payment processing
    e33    tool_call    agent:finance      payments.approve  [w_fin]  - approve $8,400 to acme-hvac   <- forbidden[1]
  every event above passed its own Lifetime/Scope/Principal check; the composition is the violation

coverage: QUALIFIED - no enforcement point declared for this trace
families: Lifetime ok  |  Scope ok  |  Principal ok  |  Provenance n/a  |  Composition partial  |  Trajectory n/a
verdict: FAIL (1 finding)
```

</details>

Read that trace again. The coordinator was granted exactly what the envelope declares. Both sub-delegations narrowed scope. Every tool call sat inside its warrant. A per-call policy engine says yes 40 times. And the task still solicited vendor quotes and approved the payment to the winner with no human in between. That gap, agents composing past checks that each pass individually, is what Kagua exists to catch.

## Why point-in-time authorization isn't enough

Cedar and OPA decide the point; Kagua verifies the trajectory. A policy engine answers "may this call proceed?", and that's precisely the layer composed abuse defeats, because every point answer is yes. Kagua evaluates the whole task DAG after the fact (or in CI, before deploy). The two are complementary: if you already run per-call policy, composition is the gap you have left.

Three claims, each testable in this repo:

1. Point-in-time authorization cannot detect composed abuse.
2. A deterministic, replayable check over a causally-ordered trace can, for declared invariants, at declared coverage.
3. Nobody ships that artifact today. Gateways enforce, observability describes, evals score quality. None verify authority composition.

## Quickstart

```bash
pip install kagua
git clone https://github.com/Dnakitare/kagua && cd kagua
kagua check fixtures/workorder/        # exits 1, prints the witness above
```

Three artifacts, all files, all diffable in git:

- **Trace** (JSONL): a DAG of events. `delegation`, `tool_call`, `task_start`, `task_end`, `token_issue`, `token_revoke`, `message`. See `fixtures/workorder/trace.jsonl`.
- **Envelope** (YAML): who the root principals are, what each agent is scoped to do, and which compositions are forbidden. See `fixtures/workorder/envelope.yaml`.
- **Verdict** (exit code + JSON): findings with witness sets, a slice of the trace sufficient to demonstrate each violation, plus a coverage grade on every claim.

## The rules Kagua checks (v0.1)

| Family | Check | Status |
|---|---|---|
| Lifetime | No event references a warrant outside its validity window; no activity after `task_end` (zombie authority) | shipped |
| Scope | Every call inside the transitive scope of its warrant chain; scope never widens across delegation hops | shipped |
| Principal | Every warrant chain terminates at a declared root principal; no orphaned authority | shipped |
| Composition | `forbidden_composition` sequences over the task DAG | shipped (sequences only) |
| Provenance | Cryptographically signed delegation hops ([Muhuri](https://github.com/Dnakitare/muhuri)) | v0.2 |
| Trajectory | Plan subsumption | v0.3+ |

v0.1 honestly covers three of the six families plus forbidden compositions. The general composition engine (budgets, conservation rules in CEL) is v0.2.

Design rules that won't bend:

- **Every check is deterministic and produces a replayable witness.** No ML in the verifier. An anomaly score is a suspicion; a witness set is a proof.
- **Causal order beats wall clock.** Ordering comes from parent links; timestamps are a fallback with a tolerance window, because distributed clocks lie.
- **Retries have identity.** Events carry idempotency keys; a retried call can't count twice.
- **Lossy input never produces a silent pass.**

## Coverage grades: attested vs. qualified

Every verdict says what it can actually claim:

- `attested`: the input source can prove completeness (all egress flowed through a declared enforcement point, like an MCP gateway).
- `qualified`: violations found are real; the absence of violations proves nothing beyond the visible trace.

A pass on partial input is worse than no tool if it reads as a clean bill. Kagua states its own coverage boundary on every run.

## Ingesting your traces

```bash
kagua ingest ./otel-export.json --adapter otel --out trace.jsonl
```

The OTel GenAI adapter converts tool-execution spans into canonical events and tells you exactly what it couldn't recover. This is real output over a real OpenLLMetry export (a LangChain tool loop instrumented with `opentelemetry-instrumentation-langchain`; the export is checked in at `fixtures/otel/openllmetry-langchain.json`, no hand-authored spans):

```
ingested 9 spans -> 4 events
  skipped 5: model/agent invocation spans (no authority semantics)
recovered: 0/4 warrants, 0 delegation records, 4/4 args digests (4 derived here from plaintext args, not attested by source)

this input cannot support:
  Principal   - no delegation records; warrant chains to a root principal cannot be verified
  Lifetime    - no warrants or task boundaries; validity windows unknowable
  Scope       - degraded to a point check of each call against the envelope's per-agent declarations
  Provenance  - not implemented until v0.2 (Muhuri-signed hops)

actor identity: 4 of 4 events have no per-agent identity (no gen_ai.agent.name); actor fell back to the service.name resource attribute, which cannot distinguish agents sharing a process.

task grouping: 4 events landed in 4 disjoint traces with no shared root span. Within-task checks (composition, lifetime) cannot correlate any of them. If these belong to one logical task, wrap the run in a workflow/root span or re-ingest with --task <id>.

verdicts over this trace will be QUALIFIED: findings are real, but a pass
covers only what this export saw. OTel sampling drops spans by design;
a sampled trace cannot prove the absence of a violation.
```

Even at this fidelity, the composition check works: group the calls into one task (`--task`, or a root span in your instrumentation) and the quote-then-approve pair in that export fails `kagua check` with a witness. When ordering rests on clocks instead of causal links, the finding says so rather than overclaiming.

Plain OTel GenAI data is authority-blind. If your instrumentation emits the `kagua.*` span attributes (`kagua.warrant_id`, `kagua.delegation.subject`, `kagua.args_digest`, ...), the adapter recovers full authority semantics; Datadog ignores them and nothing breaks.

## CI

```yaml
# .github/workflows/authority.yml
jobs:
  authority:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: Dnakitare/kagua@main
        with:
          trace: traces/recorded/
          fail-on: any
```

A prompt edit or tool-wiring change that widens effective authority turns the PR red with a Scope-family witness before it deploys. `fixtures/scope-drift/` is a worked example: one delegation drifts to include `payments.approve` and the check fails on the exact granting event.

## What Kagua is not

- Not an eval framework. It never scores answer quality.
- Not a gateway. It never sits in the request path.
- Not an anomaly detector. If a check can't produce a replayable witness, it doesn't ship.

## Related work

The problem is getting named from several directions at once; none of these ship this artifact, and each is worth reading:

- [Authenticated Delegation and Authorized AI Agents](https://arxiv.org/abs/2501.09674) (MIT Media Lab, 2025) makes the case for verifiable delegation chains. Kagua is the check layer such chains deserve; [Muhuri](https://github.com/Dnakitare/muhuri) is our signed-credential half of that story.
- [Closure Gaps and Delegation Envelopes for Open-World AI Agents](https://arxiv.org/abs/2604.25000) (2026) formalizes delegation envelopes. Kagua's envelope YAML is a practical, git-diffable instance of the same idea, and we take the term from that lineage rather than claiming it.
- [Authorization Propagation in Multi-Agent AI Systems](https://arxiv.org/abs/2605.05440) (2026) derives requirements for workflow-level authorization, including task-scoped envelopes and aggregation bounds, and notes the field has "not yet converged on a complete architecture". Kagua is a working verifier for the post-hoc slice of those requirements.
- [Runtime Compliance Verification for AI Agents](https://arxiv.org/abs/2606.19242) (2026) intercepts tool calls at runtime. That's enforcement, the layer we deliberately don't sit in; Kagua verifies after the fact and stays out of the request path.
- Cedar and OPA decide per-call policy. Complementary, as covered above.

## Roadmap

- **v0.2**: `kagua infer` (propose an envelope from observed traces, delivered as a PR, never auto-committed), the general composition engine (budget, conservation via CEL), pytest plugin, MCP gateway log adapter.
- **v0.3**: Muhuri-signed delegation hops; Provenance moves from "trust the log" to "verify the chain". Replayable signed verdicts.
- **v0.4**: `kagua report` with OWASP Agentic Top 10 and SOC 2 CC-series mappings. Findings and evidence language throughout, never "certified compliant".

## License

Apache-2.0
