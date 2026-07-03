#!/usr/bin/env python3
"""Sanitize an OTLP/JSON span export before sharing it publicly.

Redacts the values of content-bearing attributes (prompts, completions,
tool arguments and results) while preserving every structural property the
kagua adapter cares about: span topology, trace/span ids, timestamps,
operation names, tool names, and which attributes were present. Argument
attributes are replaced with a sha256 of their value so retry identity
survives sanitization.

Usage:
    python3 tools/sanitize_export.py export.json > export.sanitized.json

Review the output yourself before posting it anywhere. This script redacts
the attributes it knows about; it cannot know what your custom attributes
contain.
"""
import hashlib
import json
import sys

# values replaced entirely
REDACT = {
    "gen_ai.input.messages",
    "gen_ai.output.messages",
    "gen_ai.prompt",
    "gen_ai.completion",
    "gen_ai.tool.description",
    "traceloop.entity.output",
    "gen_ai.tool.call.result",
    "input.value",
    "output.value",
    "llm.input_messages",
    "llm.output_messages",
}
# values replaced with a digest, preserving identity without content
HASH = {
    "gen_ai.tool.call.arguments",
    "traceloop.entity.input",
    "kagua.args_digest",
}
# common substrings that mark content-bearing custom attributes
SUSPECT_SUBSTRINGS = ("prompt", "completion", "message", "content", "input", "output")


def _walk_attributes(attrs, notes):
    for a in attrs:
        key = a.get("key", "")
        value = a.get("value", {})
        if key in REDACT:
            a["value"] = {"stringValue": "[redacted]"}
        elif key in HASH:
            raw = json.dumps(value, sort_keys=True).encode("utf-8")
            a["value"] = {"stringValue": f"sha256:{hashlib.sha256(raw).hexdigest()}"}
        elif any(s in key.lower() for s in SUSPECT_SUBSTRINGS):
            a["value"] = {"stringValue": "[redacted:suspect]"}
            notes.add(key)


def sanitize(doc):
    notes = set()
    for rs in doc.get("resourceSpans", []):
        _walk_attributes(rs.get("resource", {}).get("attributes", []), notes)
        for ss in rs.get("scopeSpans", []):
            for span in ss.get("spans", []):
                _walk_attributes(span.get("attributes", []), notes)
                for event in span.get("events", []):
                    _walk_attributes(event.get("attributes", []), notes)
    return doc, notes


def main():
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    with open(sys.argv[1], encoding="utf-8") as fh:
        doc = json.load(fh)
    doc, notes = sanitize(doc)
    json.dump(doc, sys.stdout, indent=1)
    print(file=sys.stdout)
    if notes:
        print(
            "redacted unrecognized attributes that looked content-bearing: "
            + ", ".join(sorted(notes)),
            file=sys.stderr,
        )
    print("reminder: review the output yourself before sharing.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
