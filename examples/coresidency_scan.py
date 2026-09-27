#!/usr/bin/env python3
"""Detect co-residency + fingerprint the container runtime."""
import sys, json
sys.path.insert(0, "..")
from sca_arsenal import coresidency, report

r = coresidency.detect_coresidency(rounds=300)
print(json.dumps(r.as_dict(), indent=2, default=str))

log = report.AuditLog(engagement="lab-scan")
log.record("coresidency", {"rounds": 300}, r.as_dict())
print("audit ->", log.save("coresidency_audit.json"))
