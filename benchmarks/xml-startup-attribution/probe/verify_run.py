#!/usr/bin/env python3
"""Reject missing, failed, or ambiguous probe phases from a real IDE run."""

import argparse
import json
from pathlib import Path
import sys


def verify(path, scenario):
    if path.suffix == ".json":
        result = json.loads(path.read_text(encoding="utf-8"))
        if result["status"] != "ok" or result["scenario"] != scenario:
            raise ValueError("The atomic probe result reports failure or another scenario")
        records = result["phases"]
    else:
        records = [json.loads(line.removeprefix("XML_STUDY_PHASE "))
                   for line in path.read_text(encoding="utf-8", errors="replace").splitlines()
                   if line.startswith("XML_STUDY_PHASE ")]
    phases = [record["phase"] for record in records]
    for name in ("probe_started", "application_running", "workbench_ready", "validation_settled"):
        if phases.count(name) != 1:
            raise ValueError(f"Expected exactly one {name}, got {phases.count(name)}; phases={phases}")
    if any(name in phases for name in ("timeout", "probe_error")):
        raise ValueError(f"Run failed: phases={phases}")
    for left, right in zip(records, records[1:]):
        if right["jvmUptimeMs"] < left["jvmUptimeMs"]:
            raise ValueError("Nonmonotonic JVM uptime")
        if left["processCpuNs"] >= 0 and right["processCpuNs"] < left["processCpuNs"]:
            raise ValueError("Nonmonotonic process CPU time")
    by_phase = {record["phase"]: record for record in records}
    ready = by_phase["workbench_ready"]
    settled = by_phase["validation_settled"]
    if any(record["scenario"] != scenario for record in records):
        raise ValueError("Scenario mismatch")
    if ready["visibleWindows"] < 1 or settled["visibleWindows"] < 1:
        raise ValueError("A visible workbench was not verified")
    if settled["status"] != "ok" or settled["jobs"]["blocking"] != 0:
        raise ValueError("Completion did not satisfy the Job quiet condition")
    if settled["jobs"]["failedSinceProbe"]:
        raise ValueError("Background jobs failed; their completed work is not a successful comparison run")
    if phases.index("application_running") > phases.index("workbench_ready"):
        raise ValueError("Workbench readiness preceded applicationRunning")
    quiet_start = ready["jvmUptimeMs"]
    if scenario == "validation":
        if phases.count("validation_started") != 1 or phases.count("validation_finished") != 1:
            raise ValueError("The explicit validation workload did not finish exactly once")
        if not phases.index("workbench_ready") < phases.index("validation_started") < phases.index("validation_finished") < phases.index("validation_settled"):
            raise ValueError("Explicit validation was not strictly after workbench readiness")
        result = by_phase["validation_finished"]["validation"]
        if not result["completed"] or result["schemaFiles"] <= 0 or not result["projects"]:
            raise ValueError("No schema validation workload completed")
        if settled["measurement"] != "post-start validation":
            raise ValueError("Explicit validation was mislabeled as startup")
        quiet_start = by_phase["validation_finished"]["jvmUptimeMs"]
    elif "validation_started" in phases or "validation_finished" in phases:
        raise ValueError("Default startup unexpectedly ran explicit validation")
    if settled["jvmUptimeMs"] - quiet_start < settled["quietWindowMs"] - 1:
        raise ValueError("The declared quiet window was not observed")
    return {"status": "verified", "scenario": scenario, "phases": phases,
            "workbenchReadyJvmUptimeMs": ready["jvmUptimeMs"],
            "settledJvmUptimeMs": settled["jvmUptimeMs"],
            "failedJobs": settled["jobs"]["failedSinceProbe"],
            "validation": settled.get("validation", {})}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stdout_log", type=Path)
    parser.add_argument("--scenario", choices=("startup", "validation"), default="startup")
    args = parser.parse_args()
    try:
        print(json.dumps(verify(args.stdout_log, args.scenario)))
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"PROBE VERIFICATION FAILED: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
