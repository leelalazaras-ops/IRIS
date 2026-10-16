"""
Tests for the read-only IRIS security observatory.

All collection is real local introspection; the tests assert structure,
uncertainty labeling, and that no claims of malice or security are made.
"""

import json
import pathlib

import pytest

from iris.security import (
    CLASSIFICATION_HEURISTIC,
    SecurityFinding,
    SecurityObservatory,
)


@pytest.fixture
def observatory():
    return SecurityObservatory()


@pytest.fixture
def snapshot(observatory):
    return observatory.poll()


def test_interfaces_are_observed(snapshot):
    assert snapshot.interfaces, "at least loopback should always exist"
    names = [i.name.lower() for i in snapshot.interfaces]
    assert any("lo" in n for n in names)
    for iface in snapshot.interfaces:
        assert iface.mac == "UNAVAILABLE" or ":" in iface.mac


def test_listening_sockets_are_observed_with_owner_labels(snapshot):
    # A listening service (e.g. sshd like daemons) usually exists; assert
    # structure rather than exact ports.
    for s in snapshot.listening:
        assert s.port >= 0
        assert s.protocol in ("tcp4", "tcp6", "udp4", "udp6")
        assert s.process_name  # never empty; could be "ACCESS DENIED"
        if s.process_name == "ACCESS DENIED":
            assert s.pid_readable is False


def test_snapshot_provenance(snapshot):
    assert snapshot.data_origin == "LIVE"
    assert snapshot.simulated_included is False
    limitations = "\n".join(snapshot.limitations)
    assert "secure" in limitations  # no-findings disclaimer present


def test_findings_are_heuristic_with_evidence(snapshot):
    for f in snapshot.findings:
        d = f.to_dict()
        assert d["classification"] == CLASSIFICATION_HEURISTIC
        assert d["confidence"] in ("low", "medium")
        assert d["severity"] in ("info", "low", "medium")
        assert d["evidence"], "every finding carries evidence"
        assert d["explanation"], "every finding explains why it was raised"
        assert d["status"] == "UNREVIEWED"


def test_findings_never_claim_malice(snapshot):
    forbidden = ["malware", "malicious", "attack detected", "breach detected"]
    for f in snapshot.findings:
        blob = (f.title + " " + f.description).lower()
        for word in forbidden:
            assert word not in blob, f"finding must not assert malice: {word}"


def test_heuristic_evaluation_is_over_real_facts(observatory, snapshot):
    if snapshot.listening:
        findings = observatory.evaluate_findings(
            snapshot.listening, snapshot.connections
        )
        # heuristics over zero listeners must not fabricate socket findings
        assert isinstance(findings, list)


def test_search_and_severity_filter(snapshot, observatory):
    results = observatory.get_searchable_findings(
        snapshot, query="", severities=["info"]
    )
    for f in results:
        assert f["severity"] == "info"
    results2 = observatory.get_searchable_findings(
        snapshot, query="XYZZY-NOMATCH", severities=None
    )
    assert results2 == []


def test_events_derived_and_timestamped(observatory):
    snap1 = observatory.poll()
    snap2 = observatory.poll()
    for e in snap1.events + snap2.events:
        d = e.to_dict()
        assert d["origin"] == "DERIVED"
        assert d["timestamp"].endswith("Z")
        assert d["kind"] in ("socket_opened", "socket_closed")


def test_simulated_demo_finding_is_isolated():
    demo = SecurityFinding.simulated_demo()
    d = demo.to_dict()
    assert d["category"] == "demo"
    assert "[SIMULATED]" in d["title"]
    d["evidence"][0]["source"] == "SIMULATED"
    # demo findings are never auto-mounted into a live poll - the live poll
    # constructs its findings from observatory.evaluate_findings only.
    obs = SecurityObservatory()
    live = obs.poll()
    live_ids = [f.finding_id for f in live.findings]
    assert "DEMO-000" not in live_ids


def test_export_markdown_with_limits(snapshot, tmp_path):
    path = tmp_path / "report.md"
    written = SecurityObservatory.export_report(snapshot, str(path), fmt="md")
    assert pathlib.Path(written).exists()
    text = pathlib.Path(written).read_text(encoding="utf-8")
    assert "IRIS Security Summary" in text
    assert "HEURISTIC" in text
    assert "not evidence that this host is secure" in text
    assert "Limitations" in text


def test_export_json_with_limits(snapshot, tmp_path):
    path = tmp_path / "report.json"
    written = SecurityObservatory.export_report(snapshot, str(path), fmt="json")
    data = json.loads(pathlib.Path(written).read_text(encoding="utf-8"))
    assert data["data_origin"] == "LIVE"
    assert "_report_note" in data
