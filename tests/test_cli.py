import json
import os

import pytest

from kagua.cli import main
from tests.conftest import FIXTURES

WORKORDER = os.path.join(FIXTURES, "workorder")


def test_check_directory_form_fails_build(capsys):
    rc = main(["check", WORKORDER, "--color", "never"])
    assert rc == 1
    out = capsys.readouterr().out
    assert "Composition / forbidden_composition" in out
    assert "QUALIFIED" in out


def test_check_json_format(capsys):
    rc = main(["check", WORKORDER, "--format", "json"])
    assert rc == 1
    verdict = json.loads(capsys.readouterr().out)
    assert verdict["passed"] is False
    assert verdict["findings"][0]["family"] == "Composition"
    assert verdict["inputs"]["trace"]["sha256"]


def test_fail_on_filters_families(capsys):
    # only lifetime failures fail the build; the composition finding is
    # still rendered but the exit code is 0
    rc = main(["check", WORKORDER, "--fail-on", "lifetime", "--color", "never"])
    assert rc == 0
    assert "Composition" in capsys.readouterr().out


def test_check_missing_envelope_is_usage_error(tmp_path, capsys):
    trace = tmp_path / "trace.jsonl"
    trace.write_text('{"event_id":"e1","ts":"2026-01-01T00:00:00Z","kind":"task_start","task":"t"}\n')
    rc = main(["check", str(trace)])
    assert rc == 2


def test_check_invalid_trace_is_input_error(tmp_path, capsys):
    trace = tmp_path / "trace.jsonl"
    trace.write_text('{"event_id":"e1","kind":"tool_call"}\n')
    rc = main(["check", str(trace), "--envelope", os.path.join(WORKORDER, "envelope.yaml")])
    assert rc == 2
    assert "ts" in capsys.readouterr().err


def test_validate_ok(capsys):
    rc = main(["validate", os.path.join(WORKORDER, "trace.jsonl")])
    assert rc == 0
    assert "OK: 40 events" in capsys.readouterr().out


def test_ingest_otel_end_to_end(tmp_path, capsys):
    out = str(tmp_path / "trace.jsonl")
    rc = main(["ingest", os.path.join(FIXTURES, "otel", "spans.json"),
               "--adapter", "otel", "--out", out])
    assert rc == 0
    assert os.path.exists(out)
    printed = capsys.readouterr().out
    assert "QUALIFIED" in printed


def test_version(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
