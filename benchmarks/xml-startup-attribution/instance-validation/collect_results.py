#!/usr/bin/env python3
"""Collect checked, compact comparisons from this study's separately retained runs."""

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def collect(work):
    variants = ["pde-baseline-final", "pde-repaired", "pde-four-repaired",
                "pde-final-repaired", "pde-restored"]
    output = {"scope": "Instance validation and operation counts; no startup timing",
              "nativeComparisons": {}, "projectionComparisons": {}, "inputs": {}}
    reference_preferences = reference_runner = None
    reference_descriptors = None
    for name in variants:
        directory = work / name
        if not directory.exists():
            raise ValueError(f"Required comparison is missing: {directory}")
        result_path, execution_path = directory / "pde-validation.json", directory / "execution.json"
        result, execution = read(result_path), read(execution_path)
        assert result["status"] == "completed" and result["controlsPassed"]
        assert execution["verification"] == "passed" and execution["exitCode"] == 0
        assert execution["inputHashesUnchanged"] and execution["eclipseErrorEntries"] == 0
        assert len(result["controls"]) == 19
        assert result["summary"]["descriptorFiles"] == 83
        assert result["summary"]["extensionContributions"] == 939
        descriptors = {(f["project"], f["file"]): f["sha256"] for f in result["files"]}
        if reference_preferences is None:
            reference_preferences = result["preferences"]
            reference_runner = execution["runnerSha256"]
            reference_descriptors = descriptors
        assert result["preferences"] == reference_preferences
        assert execution["runnerSha256"] == reference_runner
        assert descriptors == reference_descriptors
        by_point = Counter()
        for file in result["files"]:
            assert file["completed"] and file["parseCompleted"]
            for extension in file["extensions"]:
                by_point[extension["point"]] += extension["diagnosticCount"]
        assert sum(by_point.values()) == result["summary"]["diagnostics"]
        repeated = []
        for case in result["repeatedLoadDiagnostic"]["cases"]:
            assert case["sameModelRetained"] and case["handlePositiveControl"]["passed"]
            repeated.append({key: case[key] for key in (
                "point", "abbreviated", "subsequentQueries", "loadedAfterQueries",
                "streamAttemptsAfterQueries", "successfulInputStreams", "closedSuccessfulStreams",
                "targetHandlesBefore", "targetHandlesAfter")})
            repeated[-1]["streamExceptionCount"] = len(case["streamExceptions"])
        output["nativeComparisons"][name] = {
            "summary": result["summary"], "diagnosticsByPoint": {k: v for k, v in sorted(by_point.items()) if v},
            "controls": len(result["controls"]), "verification": execution["verification"],
            "repeatedLoadCases": repeated}
        output["inputs"][str(result_path.relative_to(work))] = sha(result_path)
        output["inputs"][str(execution_path.relative_to(work))] = sha(execution_path)
    output["nativeRunnerSha256"] = reference_runner
    output["nativePreferencesIdentical"] = True
    output["allOriginalDescriptorBytesIdenticalAcrossNativeRuns"] = True
    for name in ["baseline", "repaired", "four-repaired", "final-repaired"]:
        path = work / f"projected-grammar-{name}.json"
        if path.exists():
            data = read(path)
            assert data["sourceFilesUnchanged"] and data["summary"]["contributions"] == 939
            assert sum(data["summary"]["statuses"].values()) == 939
            output["projectionComparisons"][name] = data["summary"]
            output["inputs"][path.name] = sha(path)
    for name in ["projected-findings-classification.json", "projected-findings-repaired.json",
                 "projected-findings-four-repaired.json", "projected-findings-final-repaired.json"]:
        path = work / name
        if path.exists():
            data = read(path)
            assert data["sourceFilesUnchanged"]
            output.setdefault("classificationComparisons", {})[name] = data["summary"]
            output["inputs"][name] = sha(path)
    for name in ["consumer-contract-checks-osgi.json", "extra-consumer-contract-checks.json"]:
        path = work / name
        if path.exists():
            data = read(path)
            assert data["passed"]
            output.setdefault("consumerChecks", {})[name] = {
                k: data[k] for k in ("sourceSha256", "scope", "compileExit", "exitCode", "passed",
                                    "passedChecks", "checks", "sourceUnchanged", "platformRunning",
                                    "sdkBundleHashes", "bundleVersions", "codeSources") if k in data}
            output["inputs"][name] = sha(path)
        else:
            raise ValueError(f"Required consumer comparison is missing: {path}")
    assert set(output["projectionComparisons"]) == {"baseline", "repaired", "four-repaired", "final-repaired"}
    assert len(output.get("classificationComparisons", {})) == 4
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work_directory", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = collect(args.work_directory.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"native": {k: v["summary"]["diagnostics"] for k, v in result["nativeComparisons"].items()},
                      "projection": {k: v["statuses"] for k, v in result["projectionComparisons"].items()}}, indent=2))
