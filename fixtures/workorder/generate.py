#!/usr/bin/env python3
"""Regenerate trace.jsonl for the Castellan work-order demo.

The scenario: HVAC failure at Site 12, work order WO-442. A coordinator
agent triages, a procurement agent collects six vendor quotes, a finance
agent approves payment to the winner. Every one of the 40 events is inside
its warrant's scope, every warrant chains to the human root principal,
every lifetime is respected. The trace still deserves to fail: quotes were
solicited and the payment approved inside one task, with no human between.

Deterministic on purpose: run it twice, get the same bytes.
"""
import json
import os
from datetime import datetime, timedelta, timezone

BASE = datetime(2026, 7, 2, 14, 0, 0, tzinfo=timezone.utc)
STEP = timedelta(seconds=7)
TASK = "t_workorder_442"

COORD_SCOPE = [
    "workorders.*", "vendors.*", "invoices.read",
    "payments.approve", "email.send", "slack.post:channel=ops",
]
PROC_SCOPE = [
    "workorders.read", "workorders.update", "vendors.search",
    "vendors.read", "vendors.get_quote", "email.send",
]
FIN_SCOPE = ["workorders.read", "workorders.update", "invoices.read", "payments.approve"]

VENDORS = [
    ("acme-hvac", "$8,400"),
    ("coolflow-mechanical", "$9,150"),
    ("borealis-climate", "$8,900"),
    ("site12-services", "$11,200"),
    ("northgate-hvac", "$9,875"),
    ("vertex-air", "$10,050"),
]

events = []
_n = 0


def emit(kind, **fields):
    global _n
    _n += 1
    ev = {
        "event_id": f"e{_n:02d}",
        "ts": (BASE + STEP * _n).isoformat().replace("+00:00", "Z"),
        "kind": kind,
        "task": TASK,
    }
    if events:
        ev["parent"] = events[-1]["event_id"]
    ev.update(fields)
    events.append(ev)
    return ev["event_id"]


emit("task_start", actor="human:ops.manager",
     summary="WO-442: HVAC failure, Site 12")
emit("message", actor="human:ops.manager",
     summary="handle WO-442 end to end, budget $12k")
emit("delegation", actor="human:ops.manager", subject="agent:coordinator",
     warrant="w_coord", scope={"tools": COORD_SCOPE}, lifetime="task",
     summary="root grant to coordinator")
emit("tool_call", actor="agent:coordinator", tool="workorders.read",
     warrant="w_coord", args_digest="sha256:1a2b", summary="fetch WO-442")
emit("tool_call", actor="agent:coordinator", tool="workorders.read",
     warrant="w_coord", args_digest="sha256:77c0", summary="fetch Site 12 maintenance history")
emit("tool_call", actor="agent:coordinator", tool="workorders.update",
     warrant="w_coord", args_digest="sha256:3c4d", summary="priority=high")
emit("tool_call", actor="agent:coordinator", tool="slack.post:channel=ops",
     warrant="w_coord", args_digest="sha256:5e6f", summary="notify ops channel")
emit("delegation", actor="agent:coordinator", subject="agent:procurement",
     warrant="w_proc", parent_warrant="w_coord",
     scope={"tools": PROC_SCOPE}, lifetime="task",
     summary="sub-delegate quote collection")
emit("message", actor="agent:coordinator", warrant="w_coord",
     summary="to procurement: collect quotes for WO-442")
emit("tool_call", actor="agent:procurement", tool="workorders.read",
     warrant="w_proc", args_digest="sha256:7a8b", summary="read WO-442 requirements")
emit("tool_call", actor="agent:procurement", tool="vendors.search",
     warrant="w_proc", args_digest="sha256:9c0d", summary="HVAC vendors near Site 12")
for vendor, price in VENDORS:
    emit("tool_call", actor="agent:procurement", tool="vendors.read",
         warrant="w_proc", args_digest=f"sha256:{vendor[:4]}0",
         summary=f"profile: {vendor}")
    emit("tool_call", actor="agent:procurement", tool="vendors.get_quote",
         warrant="w_proc", args_digest=f"sha256:{vendor[:4]}1",
         summary=f"quote from {vendor}: {price}")
emit("tool_call", actor="agent:procurement", tool="workorders.update",
     warrant="w_proc", args_digest="sha256:b1c2", summary="attach 6 quotes")
emit("tool_call", actor="agent:procurement", tool="email.send",
     warrant="w_proc", args_digest="sha256:d3e4",
     summary="best-and-final request to acme-hvac")
emit("message", actor="agent:procurement", warrant="w_proc",
     summary="to coordinator: 6 quotes in, acme-hvac lowest at $8,400")
emit("tool_call", actor="agent:coordinator", tool="workorders.update",
     warrant="w_coord", args_digest="sha256:f5a6", summary="select acme-hvac")
emit("delegation", actor="agent:coordinator", subject="agent:finance",
     warrant="w_fin", parent_warrant="w_coord",
     scope={"tools": FIN_SCOPE}, lifetime="task",
     summary="sub-delegate payment processing")
emit("message", actor="agent:coordinator", warrant="w_coord",
     summary="to finance: process payment for WO-442")
emit("token_issue", actor="agent:finance", warrant="w_fin",
     summary="finance session token under w_fin")
emit("tool_call", actor="agent:finance", tool="workorders.read",
     warrant="w_fin", args_digest="sha256:0b1c", summary="confirm vendor selection")
emit("tool_call", actor="agent:finance", tool="invoices.read",
     warrant="w_fin", args_digest="sha256:2d3e", summary="pull acme-hvac invoice")
emit("tool_call", actor="agent:finance", tool="payments.approve",
     warrant="w_fin", args_digest="sha256:4f5a",
     summary="approve $8,400 to acme-hvac")
emit("tool_call", actor="agent:finance", tool="workorders.update",
     warrant="w_fin", args_digest="sha256:6b7c", summary="mark WO-442 paid")
emit("message", actor="agent:finance", warrant="w_fin",
     summary="to coordinator: payment complete")
emit("token_revoke", actor="agent:finance", warrant="w_fin",
     summary="finance session token revoked")
emit("tool_call", actor="agent:coordinator", tool="workorders.update",
     warrant="w_coord", args_digest="sha256:8d9e", summary="close WO-442")
emit("tool_call", actor="agent:coordinator", tool="email.send",
     warrant="w_coord", args_digest="sha256:a0b1",
     summary="completion summary to ops manager")
emit("tool_call", actor="agent:coordinator", tool="slack.post:channel=ops",
     warrant="w_coord", args_digest="sha256:c2d3", summary="WO-442 resolved")
emit("task_end", actor="human:ops.manager", summary="WO-442 closed")

assert len(events) == 40, f"expected 40 events, got {len(events)}"

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "trace.jsonl")
with open(out, "w", encoding="utf-8") as fh:
    fh.write(json.dumps({"kind": "trace_meta", "source": "native", "coverage": "complete"}) + "\n")
    for ev in events:
        fh.write(json.dumps(ev) + "\n")
print(f"wrote {out}: {len(events)} events")
