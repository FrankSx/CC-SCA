import json, os, tempfile, unittest
from sca_arsenal import report


class TestReport(unittest.TestCase):
    def test_record_and_save(self):
        log = report.AuditLog(engagement="t", operator="me")
        log.record("flush_reload", {"iterations": 10}, {"hits": 7},
                   mitigations=["cache partitioning"])
        with tempfile.TemporaryDirectory() as d:
            p = log.save(os.path.join(d, "a.json"))
            data = json.load(open(p))
        self.assertEqual(len(data["entries"]), 1)
        self.assertEqual(data["entries"][0]["attack"], "flush_reload")


if __name__ == "__main__":
    unittest.main()
