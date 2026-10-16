"""
Read-only local security observability for IRIS.

This module collects facts about the local host (network interfaces,
listening sockets, process-to-connection correlation) and derives
*heuristic* indicators from them. It never terminates processes, never
modifies firewall settings or system configuration, never runs external
scans, and never claims a host is secure.

Data classification surfaced to the UI:
    OBSERVED  - a directly read fact (interface address, listening port)
    DERIVED   - computed from observed facts (delta timeline events)
    HEURISTIC - an indicator raised by a rule over facts, with LOW or
                MEDIUM confidence and evidence attached

Heuristics are explicitly uncertain: an unfamiliar process, open port, or
connection is NOT automatically malicious. Finding records carry evidence,
timestamps, the rule that raised them, and why they were raised. An empty
finding set is reported with the caveat that absence of indicators is not
proof of security.
"""

from __future__ import annotations

import json
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Optional

import psutil

_PROVENANCE = "PROVENANCE_UNKNOWN"


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# Data classification labels
CLASSIFICATION_OBSERVED = "OBSERVED"
CLASSIFICATION_DERIVED = "DERIVED"
CLASSIFICATION_HEURISTIC = "HEURISTIC"
CLASSIFICATION_SIMULATED = "SIMULATED"


@dataclass
class SocketEndpoint:
    """One listening socket seen on this host (observed fact)."""

    protocol: str            # tcp4/tcp6/udp4/udp6
    address: str
    port: int
    pid: Optional[int]
    process_name: str        # or "ACCESS DENIED" / "UNKNOWN"
    pid_readable: bool       # False when psutil could not read the owner

    def to_dict(self) -> dict[str, Any]:
        return {
            "protocol": self.protocol,
            "address": self.address,
            "port": self.port,
            "pid": self.pid,
            "process_name": self.process_name,
            "pid_readable": self.pid_readable,
        }


@dataclass
class ConnectionEndpoint:
    """One active connection seen on this host (observed fact)."""

    protocol: str
    local_address: str
    local_port: int
    remote_address: str
    remote_port: int
    status: str
    pid: Optional[int]
    process_name: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "protocol": self.protocol,
            "local_address": self.local_address,
            "local_port": self.local_port,
            "remote_address": self.remote_address,
            "remote_port": self.remote_port,
            "status": self.status,
            "pid": self.pid,
            "process_name": self.process_name,
        }


@dataclass
class InterfaceFact:
    """One network interface with its observed configuration."""

    name: str
    is_up: bool
    addresses: list[str]
    mac: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "is_up": self.is_up,
            "addresses": self.addresses,
            "mac": self.mac,
        }


@dataclass
class SecurityEvent:
    """A timestamped timeline entry derived from polling diffs (DERIVED)."""

    timestamp: str
    kind: str                 # socket_opened / socket_closed / process_changed
    detail: str
    origin: str = CLASSIFICATION_DERIVED

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "kind": self.kind,
            "detail": self.detail,
            "origin": self.origin,
        }


@dataclass
class SecurityFinding:
    """
    A heuristic indicator. Never asserts malice by itself.

    classification is always CLASSIFICATION_HEURISTIC from the built-in
    rules; severity is informational/low/medium and confidence is capped
    at "medium" because these are host-local heuristics only.
    """

    finding_id: str
    timestamp: str
    category: str
    title: str
    description: str
    severity: str             # "info" | "low" | "medium"
    confidence: str           # "low" | "medium"
    evidence: list[dict[str, str]] = field(default_factory=list)
    explanation: str = ""
    status: str = "UNREVIEWED"   # display-only status; IRIS never auto-remediates

    def to_dict(self) -> dict[str, Any]:
        return {
            "finding_id": self.finding_id,
            "timestamp": self.timestamp,
            "category": self.category,
            "title": self.title,
            "description": self.description,
            "severity": self.severity,
            "confidence": self.confidence,
            "classification": CLASSIFICATION_HEURISTIC,
            "evidence": self.evidence,
            "explanation": self.explanation,
            "status": self.status,
        }

    @staticmethod
    def simulated_demo() -> "SecurityFinding":
        """
        A clearly-labeled SIMULATED demo finding. NEVER included in live
        result sets; used only by explicit demo paths in the UI.
        """
        return SecurityFinding(
            finding_id="DEMO-000",
            timestamp=_now(),
            category="demo",
            title="[SIMULATED] Example suspicious outbound pattern",
            description=(
                "Demo content only: an example of how a heuristic finding is "
                "presented. This finding is fabricated for illustration and is "
                "never counted as a live finding."
            ),
            severity="medium",
            confidence="low",
            evidence=[
                {
                    "source": "SIMULATED",
                    "detail": "synthetic example - not measured on this host",
                }
            ],
            explanation="This is sample/demo data, clearly separated from live "
            "observed facts and never merged with real telemetry counts.",
        )


@dataclass
class SecuritySnapshot:
    """Everything the security workspace needs for one refresh cycle."""

    timestamp: str
    interfaces: list[InterfaceFact]
    listening: list[SocketEndpoint]
    connections: list[ConnectionEndpoint]
    events: list[SecurityEvent]
    findings: list[SecurityFinding]
    data_origin: str = "LIVE"
    simulated_included: bool = False
    limitations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "data_origin": self.data_origin,
            "simulated_included": self.simulated_included,
            "interfaces": [i.to_dict() for i in self.interfaces],
            "listening": [s.to_dict() for s in self.listening],
            "connections": [c.to_dict() for c in self.connections],
            "events": [e.to_dict() for e in self.events],
            "findings": [f.to_dict() for f in self.findings],
            "limitations": self.limitations,
        }


class SecurityObservatory:
    """
    Read-only collector of local host security facts.

    - `poll()` reads current facts, derives timeline events from the diff
      against the previous poll, and evaluates heuristics.
    - All collection is read-only psutil introspection.
    - Owner reads may fail without elevated privileges; when that happens the
      endpoint is reported with process_name "ACCESS DENIED" and pid_readable
      False rather than guessed.
    """

    #: how many timeline events to retain
    EVENT_HISTORY = 200

    def __init__(self, event_history: int = EVENT_HISTORY):
        self._lock = threading.Lock()
        self._history = event_history
        self._events: deque[SecurityEvent] = deque(maxlen=max(1, event_history))
        self._last_listening: set[tuple] = set()
        self._last_poll_ts: Optional[float] = None
        self._finding_counter = 0

    # ------------------------------------------------------------- collection

    @staticmethod
    def _format_addr(addr) -> str:
        try:
            return f"{addr.address}"
        except Exception:
            return "UNAVAILABLE"

    @classmethod
    def get_interfaces(cls) -> list[InterfaceFact]:
        """Observed interface facts (addresses, up/down state)."""
        result: list[InterfaceFact] = []
        try:
            addrs = psutil.net_if_addrs()
            stats = psutil.net_if_stats()
        except Exception:
            return []
        for name, addr_list in addrs.items():
            addresses: list[str] = []
            mac = "UNAVAILABLE"
            for a in addr_list:
                fam = getattr(a, "family", None)
                if fam is None:
                    continue
                try:
                    fam_key = fam.value if hasattr(fam, "value") else int(fam)
                except Exception:
                    fam_key = None
                # AF_LINK/AF_PACKET (17/18 on linux, -1/18 darwin)
                if fam_key in (17, 18, -1):
                    mac = a.address or "UNAVAILABLE"
                else:
                    addresses.append(a.address or "UNAVAILABLE")
            is_up = bool(stats.get(name) and stats[name].isup)
            result.append(
                InterfaceFact(
                    name=name, is_up=is_up, addresses=addresses, mac=mac
                )
            )
        return result

    @staticmethod
    def _owner_of(pid: Optional[int]) -> tuple[str, bool]:
        """Map a pid to a process name. Returns (name, was_readable)."""
        if pid is None:
            return ("NO OWNER (kernel/host)", True)
        try:
            proc = psutil.Process(pid)
            return (proc.name(), True)
        except psutil.NoSuchProcess:
            return ("PROCESS EXITED", True)
        except psutil.AccessDenied:
            return ("ACCESS DENIED", False)
        except Exception:
            return ("ACCESS DENIED", False)

    @classmethod
    def get_listening(cls) -> list[SocketEndpoint]:
        """
        Observed listening sockets with process-to-connection correlation
        when the OS+privileges allow it.
        """
        endpoints: list[SocketEndpoint] = []
        try:
            conns = psutil.net_connections(kind="inet")
        except (psutil.AccessDenied, Exception):
            try:
                # Fall back to per-process enumeration if global list is blocked
                conns = cls._per_process_connections(kind="inet")
            except Exception:
                return []
        seen: set[tuple] = set()
        for conn in conns:
            if conn.status != psutil.CONN_LISTEN:
                continue
            proto = (
                "tcp6" if (conn.family == __import__("socket").AF_INET6) else "tcp4"
            ) if conn.type == __import__("socket").SOCK_STREAM else (
                "udp6" if conn.family == __import__("socket").AF_INET6 else "udp4"
            )
            laddr = conn.laddr[0] if conn.laddr else ""
            lport = conn.laddr[1] if conn.laddr else 0
            key = (proto, laddr, lport)
            if key in seen:
                continue
            seen.add(key)
            name, readable = cls._owner_of(conn.pid)
            endpoints.append(
                SocketEndpoint(
                    protocol=proto,
                    address=laddr,
                    port=int(lport),
                    pid=conn.pid,
                    process_name=name,
                    pid_readable=readable,
                )
            )
        endpoints.sort(key=lambda e: (e.port, e.protocol))
        return endpoints

    @staticmethod
    def _per_process_connections(kind: str = "inet") -> list:
        """Enumerate connections process-by-process (fallback collection)."""
        conns: list = []
        for proc in psutil.process_iter(["pid"]):
            try:
                conns.extend(proc.net_connections(kind=kind))
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
        return conns

    @classmethod
    def get_connections(cls, limit: int = 100) -> list[ConnectionEndpoint]:
        """Available active-connection facts (ESTABLISHED first)."""
        rows: list[ConnectionEndpoint] = []
        try:
            conns = psutil.net_connections(kind="tcp")
        except Exception:
            try:
                conns = cls._per_process_connections(kind="tcp")
            except Exception:
                return []
        for conn in conns:
            if conn.status == psutil.CONN_LISTEN:
                continue
            name, readable = cls._owner_of(conn.pid)
            laddr = conn.laddr[0] if conn.laddr else ""
            lport = conn.laddr[1] if conn.laddr else 0
            raddr = conn.raddr[0] if conn.raddr else ""
            rport = conn.raddr[1] if conn.raddr else 0
            rows.append(
                ConnectionEndpoint(
                    protocol="tcp",
                    local_address=laddr,
                    local_port=int(lport),
                    remote_address=raddr,
                    remote_port=int(rport),
                    status=str(conn.status),
                    pid=conn.pid,
                    process_name=name,
                )
            )
        rows.sort(key=lambda c: c.status != "ESTABLISHED")
        return rows[:limit]

    # ------------------------------------------------------------- timeline

    def _diff_listening(
        self, current: list[SocketEndpoint], now_ts: float
    ) -> list[SecurityEvent]:
        """DERIVED events from listening-socket diffs between polls."""
        events: list[SecurityEvent] = []
        if self._last_listening and self._last_poll_ts:
            elapsed = (
                f", {now_ts - self._last_poll_ts:.0f}s since previous check"
            )
        else:
            elapsed = ""
        current_keys = {
            (e.protocol, e.address, e.port, e.pid) for e in current
        }
        for e in current:
            key = (e.protocol, e.address, e.port, e.pid)
            if self._last_listening and key not in self._last_listening:
                events.append(
                    SecurityEvent(
                        timestamp=_now(),
                        kind="socket_opened",
                        detail=(
                            f"{e.protocol} listener on {e.address}:{e.port} "
                            f"({'pid ' + str(e.pid) if e.pid is not None else 'no pid'}, "
                            f"process: {e.process_name}){elapsed}"
                        ),
                    )
                )
        if self._last_listening:
            prev_by_key = {e: True for e in self._last_listening}
            for key in self._last_listening:
                if key not in current_keys:
                    events.append(
                        SecurityEvent(
                            timestamp=_now(),
                            kind="socket_closed",
                            detail=(
                                f"{key[0]} listener on {key[1]}:{key[2]} "
                                f"(pid {key[3]}) is no longer listening{elapsed}"
                            ),
                        )
                    )
        self._last_listening = current_keys
        self._last_poll_ts = now_ts
        return events

    # ------------------------------------------------------------- heuristics

    def evaluate_findings(
        self, listening: list[SocketEndpoint], connections: list[ConnectionEndpoint]
    ) -> list[SecurityFinding]:
        """
        Evaluate read-only heuristics over OBSERVED facts.

        Rules raise indicators with explicit reasoning; they do not and
        cannot assert that anything is malicious.
        """
        findings: list[SecurityFinding] = []

        # H1: non-loopback listener with unreadable owner - information needs
        # privileges, not evidence of malice.
        for ep in listening:
            if ep.pid_readable is False:
                findings.append(
                    SecurityFinding(
                        finding_id=self._next_id(),
                        timestamp=_now(),
                        category="privileges",
                        title=(
                            f"Owner of listener on {ep.address}:{ep.port} "
                            "could not be identified"
                        ),
                        description=(
                            f"A {ep.protocol} socket is listening on "
                            f"{ep.address}:{ep.port}, but this session lacks the OS "
                            "privileges to read the owning process. The process "
                            "name is unknown, not malicious."
                        ),
                        severity="info",
                        confidence="low",
                        evidence=[
                            {
                                "source": "psutil.net_connections",
                                "detail": (
                                    f"{ep.protocol} LISTEN {ep.address}:{ep.port}"
                                ),
                            },
                        ],
                        explanation=(
                            "Raised because psutil could not resolve the owning "
                            "pid (AccessDenied). Elevated collection would "
                            "resolve the owner. This indicator is informational "
                            "and does not imply suspicious activity."
                        ),
                    )
                )

        # H2: established connections bypassing loopback on unprivileged sessions
        external_count = sum(
            1
            for c in connections
            if c.status == "ESTABLISHED"
            and c.remote_address not in ("", "127.0.0.1", "::1")
            and (c.remote_address or "").lower().startswith("127.") is False
        )
        if external_count > 0:
            findings.append(
                SecurityFinding(
                    finding_id=self._next_id(),
                    timestamp=_now(),
                    category="activity",
                    title=(
                        f"{external_count} established non-loopback TCP "
                        "connection(s) observed"
                    ),
                    description=(
                        "This host currently has established TCP connections "
                        "with endpoints outside loopback. This is normal for a "
                        "networked computer and is presented as observed "
                        "activity, not as suspicious behavior."
                    ),
                    severity="info",
                    confidence="low",
                    evidence=[
                        {
                            "source": "psutil.net_connections",
                            "detail": f"{external_count} ESTABLISHED non-loopback",
                        }
                    ],
                    explanation=(
                        "Raised to surface network activity levels in the "
                        "workspace. Average legitimate traffic produces this "
                        "indicator; review targets only if you expected none."
                    ),
                )
            )

        return findings

    def _next_id(self) -> str:
        self._finding_counter += 1
        return f"H{self._finding_counter:04d}"

    # ------------------------------------------------------------- poll/api

    def poll(self) -> SecuritySnapshot:
        """
        One full read-only collection pass: facts + timeline + findings.
        """
        timestamp = _now()
        ts = time.monotonic()
        interfaces = self.get_interfaces()
        listening = self.get_listening()
        connections = self.get_connections()

        new_events = []
        with self._lock:
            new_events.extend(self._diff_listening(listening, ts))
            for evt in new_events:
                self._events.append(evt)
            events = list(self._events)

        findings = self.evaluate_findings(listening, connections)

        limitations = [
            "Process ownership may be incomplete without elevated privileges.",
            "Heuristic findings describe local indicators only; no external "
            "threat intelligence is consulted.",
            "Absence of findings is not evidence that this host is secure.",
        ]

        return SecuritySnapshot(
            timestamp=timestamp,
            interfaces=interfaces,
            listening=listening,
            connections=connections,
            events=events,
            findings=findings,
            data_origin="LIVE",
            simulated_included=False,
            limitations=limitations,
        )

    def get_searchable_findings(
        self,
        snapshot: SecuritySnapshot,
        query: str = "",
        severities: Optional[list[str]] = None,
    ) -> list[dict[str, Any]]:
        """Search-backed findings list with severity filtering."""
        results: list[dict[str, Any]] = []
        needle = query.strip().lower()
        severity_filter = set(severities) if severities else None
        for f in snapshot.findings:
            if severity_filter is not None and f.severity not in severity_filter:
                continue
            if needle:
                hay = " ".join(
                    [
                        f.title,
                        f.description,
                        f.explanation,
                        *(e.get("detail", "") for e in f.evidence),
                    ]
                ).lower()
                if needle not in hay:
                    continue
            results.append(f.to_dict())
        return results

    # ------------------------------------------------------------- export

    @staticmethod
    def export_report(snapshot: SecuritySnapshot, path: str, fmt: str = "md") -> str:
        """
        Export a timestamped security summary with evidence and limitations.

        Supported formats: "md" (markdown) and "json". Returns the path
        written or raises OSError on failure.
        """
        if fmt == "json":
            payload = snapshot.to_dict()
            payload["_report_note"] = (
                "Read-only IRIS security summary; SA findings are heuristics "
                "with LOW/MEDIUM confidence and do not assert maliciousness."
            )
            payload["_generated"] = _now()
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2)
            return path

        lines: list[str] = []
        lines.append("# IRIS Security Summary")
        lines.append("")
        lines.append(f"Generated: {snapshot.timestamp}")
        lines.append(
            ""
            "All content below is OBSERVED or DERIVED from this machine, plus "
            "HEURISTIC indicators (LOW/MEDIUM confidence, explicit rationale). "
            "No simulated data is included in live sections."
        )
        lines.append("")

        lines.append("## Interfaces (OBSERVED)")
        lines.append("")
        lines.append("| Interface | State | Addresses | MAC |")
        lines.append("|---|---|---|---|")
        for i in snapshot.interfaces:
            lines.append(
                f"| {i.name} | {'UP' if i.is_up else 'DOWN'} "
                f"| {', '.join(i.addresses) or 'none'} | {i.mac} |"
            )
        lines.append("")

        lines.append("## Listening sockets (OBSERVED)")
        lines.append("")
        lines.append("| Protocol | Address | Port | PID | Process |")
        lines.append("|---|---|---|---|---|")
        for s in snapshot.listening:
            lines.append(
                f"| {s.protocol} | {s.address} | {s.port} | "
                f"{s.pid if s.pid is not None else '-'} | {s.process_name} |"
            )
        lines.append("")

        lines.append("## Timeline (DERIVED)")
        lines.append("")
        if not snapshot.events:
            lines.append("No listener diff events recorded yet (needs two polls).")
            lines.append("")
        else:
            for e in snapshot.events[-50:]:
                lines.append(f"- `{e.timestamp}` **{e.kind}** - {e.detail}")
            lines.append("")

        lines.append("## Heuristic findings (HEURISTIC, LOW/MEDIUM confidence)")
        lines.append("")
        if not snapshot.findings:
            lines.append(
                "No heuristic indicators were raised by the current rule set. "
                "**This does not prove the host is secure** - it only means "
                "these local rules found nothing notable."
            )
            lines.append("")
        else:
            for f in snapshot.findings:
                lines.append(f"### {f.finding_id}: {f.title}")
                lines.append(f"- Severity: {f.severity} / Confidence: {f.confidence}")
                lines.append(f"- Explanation: {f.explanation}")
                lines.append("- Description: " + f.description)
                for ev in f.evidence:
                    lines.append(f"- Evidence ({ev['source']}): {ev['detail']}")
                lines.append("")

        lines.append("## Limitations")
        lines.append("")
        for l in snapshot.limitations:
            lines.append(f"- {l}")
        lines.append("")

        with open(path, "w", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")
        return path
