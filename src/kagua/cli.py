"""kagua CLI: ingest, validate, check.

Exit codes: 0 pass, 1 findings (filtered by --fail-on), 2 invalid input/usage.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from . import __version__
from .checks import FAMILIES, run_all
from .envelope import EnvelopeError, load_envelope
from .events import load_trace
from .render import render_verdict
from .trace import DEFAULT_CLOCK_TOLERANCE_S, Trace
from .verdict import build_verdict


def _fail(msg: str) -> int:
    print(f"kagua: {msg}", file=sys.stderr)
    return 2


def cmd_validate(args: argparse.Namespace) -> int:
    meta, events, errors = load_trace(args.trace)
    if errors:
        for e in errors:
            print(f"kagua: {args.trace}: {e}", file=sys.stderr)
        return 2
    print(f"OK: {len(events)} events, source={meta.source}, coverage={meta.coverage}")
    return 0


def cmd_ingest(args: argparse.Namespace) -> int:
    if args.adapter != "otel":
        return _fail(f"unknown adapter {args.adapter!r} (v0.1 ships: otel)")
    from .ingest import otel

    try:
        report = otel.ingest(args.input, args.out)
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        return _fail(f"could not ingest {args.input}: {exc}")
    print(f"wrote {args.out}")
    print()
    print(report.render_text())
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    # `kagua check some/dir/` picks up trace.jsonl + envelope.yaml inside it
    if os.path.isdir(args.trace):
        candidate = os.path.join(args.trace, "envelope.yaml")
        if args.envelope is None and os.path.exists(candidate):
            args.envelope = candidate
        args.trace = os.path.join(args.trace, "trace.jsonl")
    if args.envelope is None:
        return _fail("no envelope: pass --envelope or point check at a directory containing envelope.yaml")

    meta, events, errors = load_trace(args.trace)
    if errors:
        for e in errors:
            print(f"kagua: {args.trace}: {e}", file=sys.stderr)
        return 2
    try:
        env = load_envelope(args.envelope)
    except (OSError, EnvelopeError) as exc:
        return _fail(f"envelope {args.envelope}: {exc}")

    trace = Trace(events, meta, clock_tolerance_s=args.clock_tolerance)
    findings, unchecked = run_all(trace, env)
    verdict = build_verdict(trace, env, findings, unchecked, args.trace, args.envelope)

    if args.format == "json":
        print(json.dumps(verdict, indent=2))
    else:
        print(render_verdict(verdict, trace, use_color=None if args.color == "auto" else args.color == "always"))
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as fh:
            json.dump(verdict, fh, indent=2)

    fail_on = {f.strip().lower() for f in args.fail_on.split(",")}
    if "any" in fail_on:
        failing = findings
    else:
        failing = [f for f in findings if f.family.lower() in fail_on]
    return 1 if failing else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="kagua",
        description="Authority verification harness for AI agents. Unit tests assert"
        " your agent did the right thing; kagua asserts it was ever allowed to.",
    )
    parser.add_argument("--version", action="version", version=f"kagua {__version__}")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_check = sub.add_parser("check", help="replay a trace against an authority envelope")
    p_check.add_argument(
        "trace",
        help="canonical JSONL trace file, or a directory containing trace.jsonl and envelope.yaml",
    )
    p_check.add_argument("--envelope", default=None, help="authority envelope YAML")
    p_check.add_argument(
        "--fail-on",
        default="any",
        help="comma-separated families that fail the build (default: any); "
        f"choices: any,{','.join(f.lower() for f in FAMILIES)}",
    )
    p_check.add_argument("--format", choices=("text", "json"), default="text")
    p_check.add_argument("--json", dest="json_out", metavar="PATH", help="also write verdict JSON to PATH")
    p_check.add_argument(
        "--clock-tolerance",
        type=float,
        default=DEFAULT_CLOCK_TOLERANCE_S,
        metavar="SECONDS",
        help="tolerance for ordering causally-unrelated events by timestamp (default: 5)",
    )
    p_check.add_argument("--color", choices=("auto", "always", "never"), default="auto")
    p_check.set_defaults(fn=cmd_check)

    p_validate = sub.add_parser("validate", help="validate a JSONL trace against the schema")
    p_validate.add_argument("trace")
    p_validate.set_defaults(fn=cmd_validate)

    p_ingest = sub.add_parser("ingest", help="normalize an external trace format to canonical JSONL")
    p_ingest.add_argument("input", help="input file or directory")
    p_ingest.add_argument("--adapter", required=True, choices=("otel",))
    p_ingest.add_argument("--out", required=True, help="output JSONL path")
    p_ingest.set_defaults(fn=cmd_ingest)

    args = parser.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
