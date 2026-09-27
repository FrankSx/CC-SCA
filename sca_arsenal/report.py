"""
Audit trail generation — evidence JSON for authorized engagements.
"""
from __future__ import annotations

import json
import platform
import socket
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

from . import __version__


@dataclass
class AuditEntry:
    timestamp: float = field(default_factory=time.time)
    tool: str = "sca-arsenal"
    version: str = __version__
    host: str = field(default_factory=socket.gethostname)
    platform: str = field(default_factory=lambda: platform.platform())
    attack: str = ""
    parameters: Dict[str, Any] = field(default_factory=dict)
    results: Dict[str, Any] = field(default_factory=dict)
    mitigations: List[str] = field(default_factory=list)


class AuditLog:
    def __init__(self, engagement: str = "", operator: str = ""):
        self.engagement = engagement
        self.operator = operator
        self.entries: List[AuditEntry] = []

    def record(self, attack: str, parameters: dict, results: dict,
               mitigations: Optional[List[str]] = None) -> AuditEntry:
        e = AuditEntry(attack=attack, parameters=parameters, results=results,
                       mitigations=mitigations or [])
        self.entries.append(e)
        return e

    def to_dict(self) -> dict:
        return {
            "tool": "sca-arsenal",
            "version": __version__,
            "engagement": self.engagement,
            "operator": self.operator,
            "entries": [asdict(e) for e in self.entries],
        }

    def save(self, path: str):
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)
        return path
