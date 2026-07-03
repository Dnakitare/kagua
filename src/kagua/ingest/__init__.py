"""Adapters normalize external trace formats into canonical Kagua JSONL.

Design rule: adapters degrade honestly. Whatever an adapter cannot recover
(delegation records, warrants, argument digests) is counted, reported in
plain language, and stamped into the trace_meta line so the verdict's
coverage grade reflects it. Lossy input must never produce a silent pass.
"""
