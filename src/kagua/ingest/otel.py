"""OTel GenAI adapter: OTLP/JSON span exports -> canonical Kagua JSONL.

Recognizes:
  - tool execution spans (gen_ai.operation.name == "execute_tool", or any
    span carrying gen_ai.tool.name) -> tool_call events
  - kagua.* namespaced attributes emitted by the native SDK shim
    (kagua.warrant_id, kagua.args_digest, kagua.actor, kagua.task_id,
    kagua.idempotency_key) -> recovered authority fields
  - delegation spans (kagua.delegation.subject + kagua.warrant_id)
    -> delegation events

Plain OTel GenAI data is authority-blind: no warrants, no delegation
records, no principals. The adapter ingests it anyway and reports exactly
what could not be recovered and which check families that disables.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone

from ..events import TraceMeta


@dataclass
class LossReport:
    spans_total: int = 0
    events_emitted: int = 0
    skipped: dict = field(default_factory=dict)  # reason -> count
    tool_calls: int = 0
    tool_calls_with_warrant: int = 0
    tool_calls_with_args_digest: int = 0
    args_digests_derived: int = 0  # hashed here from plaintext args, not attested by source
    delegation_records: int = 0
    distinct_tasks: int = 0
    task_id_forced: str | None = None
    actor_from_service_name: int = 0

    def skip(self, reason: str) -> None:
        self.skipped[reason] = self.skipped.get(reason, 0) + 1

    def to_meta_dict(self) -> dict:
        return {
            "spans_total": self.spans_total,
            "events_emitted": self.events_emitted,
            "skipped": self.skipped,
            "tool_calls": self.tool_calls,
            "tool_calls_with_warrant": self.tool_calls_with_warrant,
            "tool_calls_with_args_digest": self.tool_calls_with_args_digest,
            "args_digests_derived": self.args_digests_derived,
            "delegation_records": self.delegation_records,
            "distinct_tasks": self.distinct_tasks,
            "task_id_forced": self.task_id_forced,
            "actor_from_service_name": self.actor_from_service_name,
        }

    def render_text(self) -> str:
        """The plain-language honesty report (user story A2)."""
        out = [
            f"ingested {self.spans_total} spans -> {self.events_emitted} events",
        ]
        for reason, n in sorted(self.skipped.items()):
            out.append(f"  skipped {n}: {reason}")
        digests = f"{self.tool_calls_with_args_digest}/{self.tool_calls} args digests"
        if self.args_digests_derived:
            digests += f" ({self.args_digests_derived} derived here from plaintext args, not attested by source)"
        out.append(
            f"recovered: {self.tool_calls_with_warrant}/{self.tool_calls} warrants,"
            f" {self.delegation_records} delegation records, {digests}"
        )
        full_authority = (
            self.delegation_records > 0
            and self.tool_calls_with_warrant == self.tool_calls
        )
        out.append("")
        if full_authority:
            out.append(
                "authority fields recovered from kagua.* attributes:"
                " Lifetime, Scope, Principal are checkable."
            )
        else:
            out.append("this input cannot support:")
            if self.delegation_records == 0:
                out.append(
                    "  Principal   - no delegation records; warrant chains to a root"
                    " principal cannot be verified"
                )
                out.append(
                    "  Lifetime    - no warrants or task boundaries; validity windows unknowable"
                )
                out.append(
                    "  Scope       - degraded to a point check of each call against the"
                    " envelope's per-agent declarations"
                )
            else:
                out.append(
                    f"  {self.tool_calls - self.tool_calls_with_warrant} of"
                    f" {self.tool_calls} tool calls carry no warrant; those events are"
                    " unverifiable for Lifetime/Principal"
                )
            out.append("  Provenance  - not implemented until v0.2 (Muhuri-signed hops)")
        if self.actor_from_service_name:
            out.append("")
            out.append(
                f"actor identity: {self.actor_from_service_name} of {self.events_emitted} events"
                " have no per-agent identity (no gen_ai.agent.name); actor fell back to the"
                " service.name resource attribute, which cannot distinguish agents sharing a process."
            )
        if self.task_id_forced is not None:
            out.append("")
            out.append(
                f"task grouping: all events forced into task '{self.task_id_forced}' via --task."
                " That grouping is your assertion, not the trace's; the verdict inherits it."
            )
        elif self.events_emitted > 1 and self.distinct_tasks == self.events_emitted:
            out.append("")
            out.append(
                f"task grouping: {self.events_emitted} events landed in {self.distinct_tasks}"
                " disjoint traces with no shared root span. Within-task checks (composition,"
                " lifetime) cannot correlate any of them. If these belong to one logical task,"
                " wrap the run in a workflow/root span or re-ingest with --task <id>."
            )
        out.append("")
        out.append(
            "verdicts over this trace will be QUALIFIED: findings are real, but a pass"
        )
        out.append("covers only what this export saw. OTel sampling drops spans by design;")
        out.append("a sampled trace cannot prove the absence of a violation.")
        return "\n".join(out)


def _attr_value(v: dict):
    if "stringValue" in v:
        return v["stringValue"]
    if "intValue" in v:
        return int(v["intValue"])
    if "boolValue" in v:
        return v["boolValue"]
    if "doubleValue" in v:
        return v["doubleValue"]
    if "arrayValue" in v:
        return [_attr_value(x) for x in v["arrayValue"].get("values", [])]
    return None


def _attrs(span: dict) -> dict:
    return {a["key"]: _attr_value(a.get("value", {})) for a in span.get("attributes", [])}


def _ts(nanos) -> str:
    dt = datetime.fromtimestamp(int(nanos) / 1e9, tz=timezone.utc)
    return dt.isoformat().replace("+00:00", "Z")


def _load_docs(path: str) -> list[dict]:
    paths: list[str] = []
    if os.path.isdir(path):
        for name in sorted(os.listdir(path)):
            if name.endswith(".json") or name.endswith(".jsonl"):
                paths.append(os.path.join(path, name))
    else:
        paths.append(path)
    docs: list[dict] = []
    for p in paths:
        with open(p, encoding="utf-8") as fh:
            text = fh.read().strip()
        if not text:
            continue
        try:
            docs.append(json.loads(text))
        except json.JSONDecodeError:
            for line in text.splitlines():
                line = line.strip()
                if line:
                    docs.append(json.loads(line))
    return docs


def _scope_tools(value) -> list[str]:
    if isinstance(value, list):
        return [str(v) for v in value]
    if isinstance(value, str):
        return [t.strip() for t in value.split(",") if t.strip()]
    return []


def ingest(path: str, out_path: str, task_override: str | None = None) -> LossReport:
    docs = _load_docs(path)
    report = LossReport()
    report.task_id_forced = task_override

    spans: list[tuple[dict, dict]] = []  # (span, resource_attrs)
    for doc in docs:
        for rs in doc.get("resourceSpans", []):
            res_attrs = {
                a["key"]: _attr_value(a.get("value", {}))
                for a in rs.get("resource", {}).get("attributes", [])
            }
            for ss in rs.get("scopeSpans", []):
                for span in ss.get("spans", []):
                    spans.append((span, res_attrs))
    report.spans_total = len(spans)

    parent_of = {s["spanId"]: s.get("parentSpanId") for s, _ in spans}
    events: list[dict] = []
    emitted_ids: set[str] = set()

    def resolve_parent(span_id: str) -> str | None:
        cur = parent_of.get(span_id)
        seen = set()
        while cur is not None and cur not in emitted_ids:
            if cur in seen:
                return None
            seen.add(cur)
            cur = parent_of.get(cur)
        return cur

    spans.sort(key=lambda p: int(p[0].get("startTimeUnixNano", 0)))
    for span, res_attrs in spans:
        attrs = _attrs(span)
        op = attrs.get("gen_ai.operation.name")
        is_delegation = "kagua.delegation.subject" in attrs and "kagua.warrant_id" in attrs
        is_tool = op == "execute_tool" or "gen_ai.tool.name" in attrs

        def task_id() -> str:
            if task_override is not None:
                return task_override
            return attrs.get("kagua.task_id") or f"trace:{span['traceId']}"

        if is_delegation:
            ev = {
                "event_id": span["spanId"],
                "ts": _ts(span.get("startTimeUnixNano", 0)),
                "kind": "delegation",
                "actor": attrs.get("kagua.delegation.issuer")
                or attrs.get("kagua.actor")
                or attrs.get("gen_ai.agent.name")
                or res_attrs.get("service.name"),
                "warrant": attrs["kagua.warrant_id"],
                "subject": attrs["kagua.delegation.subject"],
                "parent_warrant": attrs.get("kagua.delegation.parent_warrant"),
                "scope": {"tools": _scope_tools(attrs.get("kagua.delegation.scope"))},
                "lifetime": attrs.get("kagua.delegation.lifetime", "task"),
                "task": task_id(),
            }
            report.delegation_records += 1
        elif is_tool:
            actor = attrs.get("kagua.actor") or attrs.get("gen_ai.agent.name")
            if actor is None:
                actor = res_attrs.get("service.name")
                if actor is not None:
                    report.actor_from_service_name += 1
            ev = {
                "event_id": span["spanId"],
                "ts": _ts(span.get("startTimeUnixNano", 0)),
                "kind": "tool_call",
                "actor": actor,
                "tool": attrs.get("gen_ai.tool.name") or span.get("name"),
                "task": task_id(),
            }
            if attrs.get("kagua.warrant_id"):
                ev["warrant"] = attrs["kagua.warrant_id"]
                report.tool_calls_with_warrant += 1
            if attrs.get("kagua.args_digest"):
                ev["args_digest"] = attrs["kagua.args_digest"]
                report.tool_calls_with_args_digest += 1
            else:
                # OpenLLMetry and semconv-conformant instrumentations carry the
                # call arguments in plaintext; hash them here so retries and
                # witnesses have argument identity. Derived, not attested:
                # the source never vouched for this digest, and the report says so.
                plain_args = attrs.get("gen_ai.tool.call.arguments") or attrs.get(
                    "traceloop.entity.input"
                )
                if plain_args is not None:
                    digest = hashlib.sha256(str(plain_args).encode("utf-8")).hexdigest()
                    ev["args_digest"] = f"sha256:{digest}"
                    report.tool_calls_with_args_digest += 1
                    report.args_digests_derived += 1
            if attrs.get("kagua.idempotency_key"):
                ev["idempotency_key"] = attrs["kagua.idempotency_key"]
            report.tool_calls += 1
        elif op in ("chat", "text_completion", "generate_content", "invoke_agent"):
            report.skip("model/agent invocation spans (no authority semantics)")
            continue
        elif "gen_ai.system" in attrs or op is not None:
            report.skip("other GenAI spans (no tool or delegation semantics)")
            continue
        else:
            report.skip("non-GenAI spans")
            continue

        parent = resolve_parent(span["spanId"])
        if parent is not None:
            ev["parent"] = parent
        events.append(ev)
        emitted_ids.add(span["spanId"])

    report.events_emitted = len(events)
    report.distinct_tasks = len({ev["task"] for ev in events if ev.get("task")})

    meta = TraceMeta(
        source="otel",
        coverage="unknown",
        adapter_loss=report.to_meta_dict(),
    )
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(meta.to_json()) + "\n")
        for ev in events:
            fh.write(json.dumps(ev) + "\n")
    return report
