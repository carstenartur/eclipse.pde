"""Output-contract regressions; these records are not Eclipse measurements."""

import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


SPEC = importlib.util.spec_from_file_location("verify_run", Path(__file__).resolve().parents[1] / "verify_run.py")
VERIFY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VERIFY)


class VerifyRunTest(unittest.TestCase):
    def setUp(self):
        self.records = [
            {"phase": "probe_started", "scenario": "startup", "jvmUptimeMs": 100, "processCpuNs": 10, "visibleWindows": 0},
            {"phase": "application_running", "scenario": "startup", "jvmUptimeMs": 500, "processCpuNs": 30, "visibleWindows": 0},
            {"phase": "workbench_ready", "scenario": "startup", "jvmUptimeMs": 600, "processCpuNs": 40, "visibleWindows": 1},
            {"phase": "validation_settled", "scenario": "startup", "jvmUptimeMs": 1600, "processCpuNs": 50,
             "visibleWindows": 1, "status": "ok", "quietWindowMs": 1000, "measurement": "startup observation",
             "jobs": {"blocking": 0, "failedSinceProbe": 0}},
        ]

    def verify(self, records):
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "stdout.log"
            log.write_text("ordinary Eclipse logging\n" + "\n".join("XML_STUDY_PHASE " + json.dumps(record) for record in records), encoding="utf-8")
            return VERIFY.verify(log, "startup")

    def test_visible_idle_startup_is_accepted(self):
        self.assertEqual(self.verify(self.records)["status"], "verified")

    def test_atomic_result_does_not_depend_on_console_line_boundaries(self):
        with tempfile.TemporaryDirectory() as directory:
            result = Path(directory) / "result.json"
            result.write_text(json.dumps({"status": "ok", "scenario": "startup", "phases": self.records}))
            self.assertEqual(VERIFY.verify(result, "startup")["status"], "verified")
            result.write_text(json.dumps({"status": "error", "scenario": "startup", "phases": self.records}))
            with self.assertRaises(ValueError):
                VERIFY.verify(result, "startup")

    def test_failed_background_work_is_not_a_successful_run(self):
        self.records[-1]["jobs"]["failedSinceProbe"] = 1
        with self.assertRaises(ValueError):
            self.verify(self.records)

    def test_hidden_window_is_not_ready(self):
        self.records[2]["visibleWindows"] = 0
        with self.assertRaises(ValueError):
            self.verify(self.records)

    def test_completion_cannot_cut_the_quiet_window_short(self):
        self.records[-1]["jvmUptimeMs"] = 1500
        with self.assertRaises(ValueError):
            self.verify(self.records)

    def test_duplicate_runs_are_not_merged(self):
        with self.assertRaises(ValueError):
            self.verify(self.records + copy.deepcopy(self.records))

    def test_startup_cannot_hide_an_explicit_workload(self):
        injected = copy.deepcopy(self.records[2])
        injected["phase"] = "validation_started"
        self.records.insert(3, injected)
        with self.assertRaises(ValueError):
            self.verify(self.records)


if __name__ == "__main__":
    unittest.main()
