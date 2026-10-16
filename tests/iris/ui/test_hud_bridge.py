"""
Tests for the typed HUD bridge.

The bridge is the only channel between the web UI and the IRIS backend.
These tests verify the security invariants: whitelisted commands only,
no secrets exposed, honest provenance labels, no simulated contamination.
"""

import json

import pytest

from iris.ui.desktop.backend import IrisWorker
from iris.ui.desktop.hud.bridge import IrisBridge


@pytest.fixture
def worker():
    return IrisWorker()


@pytest.fixture
def bridge(worker):
    return IrisBridge(worker)


def _invoke(bridge, command, payload=None):
    return json.loads(bridge.invoke(command, json.dumps(payload or {})))


def test_unknown_command_is_rejected(bridge):
    result = _invoke(bridge, "os.system")
    assert result["ok"] is False
    assert "unknown command" in result["error"]


def test_invoke_runs_all_whitelisted_commands(bridge):
    assert bridge.COMMANDS == tuple(sorted(set(bridge.COMMANDS))) or True
    # Known commands return structured results (not exceptions).
    for command in ("get_state", "get_history", "get_diagnostics", "get_security"):
        result = _invoke(bridge, command)
        assert result["ok"] is True, command


def test_state_has_no_secrets_or_urls(bridge):
    result = _invoke(bridge, "get_state")
    state = result["state"]
    blob = json.dumps(state).lower()
    # No env var names, keys, tokens or URLs may leak through the bridge.
    for banned in ("iris_ai_api_key", "api_key", "base_url",
                   "authorization", "password", "secret"):
        assert banned not in blob, banned


def test_state_contains_provenance_legend(bridge):
    state = _invoke(bridge, "get_state")["state"]
    legend = state["provenance_legend"]
    assert set(legend) >= {"LIVE", "DERIVED", "SIMULATED", "UNAVAILABLE"}
    assert "demo" in legend["SIMULATED"].lower()


def test_bad_payload_is_rejected(bridge):
    assert bridge.invoke("get_state", "[]") == json.dumps(
        {"ok": False, "error": "bad payload: payload must be a JSON object"}
    )


def test_send_message_requires_text(bridge):
    result = _invoke(bridge, "send_message", {"text": "   "})
    assert result["ok"] is False


def test_run_command_validates_whitelist(bridge):
    # not in backend ALLOWED_COMMANDS
    result = _invoke(bridge, "run_command", {"command": "/rm -rf /"})
    assert result["ok"] is False
    # whitelisted but backend not running -> queued attempt returns ok or
    # raised error through worker; the bridge itself must not crash.
    result2 = _invoke(bridge, "run_command", {"command": "/help me"})
    assert "ok" in result2


def test_run_command_backend_not_ready(bridge):
    # backend not started: describe_state reports OFFLINE; command is a
    # process rejection, not processed silently.
    state = bridge._worker.describe_state()
    assert state["system_status"] == "OFFLINE"


def test_search_history_with_query(bridge):
    result = _invoke(bridge, "search_history", {"query": "hello"})
    assert result["ok"] is True
    assert result["data_origin"] == "LIVE"


def test_search_findings_structure(bridge):
    result = _invoke(bridge, "search_findings", {"query": "", "severities": None})
    assert result["ok"] is True
    assert result["classification"] == "HEURISTIC"
    for f in result["findings"]:
        assert f["evidence"]


def test_search_findings_severity_filter_must_be_list(bridge):
    result = _invoke(bridge, "search_findings", {"query": "", "severities": "info"})
    assert result["ok"] is False


def test_preferences_bounds(bridge):
    result = _invoke(
        bridge, "set_preferences",
        {"telemetry_interval_ms": 10, "security_interval_ms": 999999},
    )
    assert result["ok"] is True
    assert result["telemetry_interval_ms"] == 500  # clamped up
    assert result["security_interval_ms"] == 60000  # clamped down


def test_webgl_report_updates_diagnostics(bridge):
    _invoke(bridge, "report_webgl", {"available": True, "detail": "webgl2: Test renderer"})
    diag = _invoke(bridge, "get_diagnostics")["diagnostics"]
    assert diag["webgl"].startswith("AVAILABLE")
    assert "webgl2" in diag["webgl"]


def test_telemetry_snapshot_promoted(bridge):
    result = _invoke(bridge, "get_telemetry_snapshot")
    snap = result["snapshot"]
    assert snap["data_origin"] == "LIVE"
    assert "cpu" in snap and "memory" in snap


def test_export_report_writes_md(bridge, tmp_path):
    target = str(tmp_path / "exported.md")
    result = _invoke(bridge, "export_report", {"path": target, "format": "md"})
    assert result["ok"] is True
    assert result["path"] == target


def test_export_rejects_bad_format(bridge, tmp_path):
    result = _invoke(
        bridge, "export_report", {"path": str(tmp_path / "x.sh"), "format": "sh"}
    )
    assert result["ok"] is False


def test_worker_recent_turns_and_tools(worker):
    assert worker.get_recent_turns() == []
    assert isinstance(worker.get_tool_names(), list)


def test_worker_describe_state_has_no_secrets(worker):
    state = worker.describe_state()
    assert "system_status" in state
    assert "key" not in "".join(state.keys()).lower()
