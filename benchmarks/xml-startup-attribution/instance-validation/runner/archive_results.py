#!/usr/bin/env python3
"""Archive verified native-validation evidence without copying IDEs or workspaces."""

import argparse
from collections import Counter
import hashlib
import io
import json
from pathlib import Path
import tarfile


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_json(path):
    return json.loads(path.read_text())


def markers(result):
    return Counter(json.dumps({"project": file["project"], "file": file["file"], **diagnostic},
                              sort_keys=True)
                   for file in result["files"] for diagnostic in file["diagnostics"])


def marker_rows(counter):
    return [{"count": count, **json.loads(marker)} for marker, count in sorted(counter.items())]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verification", required=True, type=Path)
    parser.add_argument("--runs", nargs="+", default=["pde-baseline-final", "pde-repaired",
                                                       "pde-restored", "pde-four-repaired", "pde-final-repaired"])
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parent / "results")
    args = parser.parse_args()
    here, root, output = Path(__file__).resolve().parent, args.verification.resolve(), args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    content = {}
    runs = {}
    baseline = read_json(root / "pde-baseline-final/pde-validation.json")
    baseline_markers = markers(baseline)
    expected_jar = None
    expected_runner = None
    for name in args.runs:
        directory = root / name
        result = read_json(directory / "pde-validation.json")
        execution = read_json(directory / "execution.json")
        build = read_json(directory / "build.json")
        assert execution["verification"] == "passed", name
        assert execution["exitCode"] == 0 and not execution["timedOut"], name
        assert execution["eclipseErrorEntries"] == 0 and execution["inputHashesUnchanged"], name
        assert execution["descriptorSetMatches"] and execution["contributionCountMatches"], name
        assert result["controlsPassed"] and all(c["harnessCheckPassed"] for c in result["controls"]), name
        expected_jar = expected_jar or build["sha256"]
        expected_runner = expected_runner or execution["runnerSha256"]
        assert build["sha256"] == expected_jar and execution["runnerSha256"] == expected_runner, name
        marker_counts = markers(result)
        repeats = []
        for case in result["repeatedLoadDiagnostic"]["cases"]:
            assert case["handlePositiveControl"]["passed"], (name, case["point"])
            repeats.append({**{key: value for key, value in case.items()
                                if key not in {"streamExceptions", "jarUseCachesValues"}},
                            "streamExceptionCount": len(case["streamExceptions"]),
                            "streamExceptionTypes": sorted({e["type"] for e in case["streamExceptions"]}),
                            "jarUseCachesValues": sorted(set(case["jarUseCachesValues"]))})
        runs[name] = {"verification": execution["verification"], "summary": result["summary"],
                      "registeredModelCount": result["registeredModelCount"],
                      "controlCount": len(result["controls"]), "controlsPassed": result["controlsPassed"],
                      "exitCode": execution["exitCode"], "eclipseErrorEntries": execution["eclipseErrorEntries"],
                      "inputHashesUnchanged": execution["inputHashesUnchanged"],
                      "removedDiagnosticsVersusBaseline": marker_rows(baseline_markers - marker_counts),
                      "addedDiagnosticsVersusBaseline": marker_rows(marker_counts - baseline_markers),
                      "repeatedLoadDiagnostic": repeats}
        for filename in ["pde-validation.json", "execution.json", "build.json", "eclipse.log"]:
            content[f"runs/{name}/{filename}"] = (directory / filename).read_bytes()
        content[f"runs/{name}/corpus-manifest.json"] = (directory / "corpus/corpus-manifest.json").read_bytes()
    native_jar = here / "build/org.eclipse.pde.xmlstudy.instances_1.0.0.jar"
    assert digest(native_jar.read_bytes()) == expected_jar
    assert digest((here / "run_validation.py").read_bytes()) == expected_runner
    content["artifacts/" + native_jar.name] = native_jar.read_bytes()
    consumer_path = root / "consumer-contract-checks-osgi.json"
    consumer = read_json(consumer_path)
    assert consumer["passed"] and consumer["passedChecks"] == 10 and consumer["platformRunning"]
    assert consumer["exitCode"] == 0 and consumer["eclipseErrorEntries"] == 0 and consumer["sourceUnchanged"]
    consumer_jar = Path(consumer["jar"])
    assert digest(consumer_jar.read_bytes()) == consumer["jarSha256"]
    content["artifacts/" + consumer_jar.name] = consumer_jar.read_bytes()
    content["consumer/consumer-contract-checks-osgi.json"] = consumer_path.read_bytes()
    content["consumer/application-result.json"] = Path(consumer["applicationOutput"]).read_bytes()
    content["consumer/eclipse.log"] = Path(consumer["eclipseLog"]).read_bytes()
    content["consumer/excluded-standalone.json"] = (root / "consumer-contract-checks-excluded-standalone.json").read_bytes()
    for path in sorted(here.rglob("*")):
        relative = path.relative_to(here)
        if path.is_file() and not ({"build", "results", "__pycache__"} & set(relative.parts)):
            content["harness/runner/" + relative.as_posix()] = path.read_bytes()
    for name in ["ConsumerContractProbe.java", "run_consumer_checks.py"]:
        content["harness/fixes/" + name] = (here.parent / "fixes" / name).read_bytes()
    if (output / "README.md").exists():
        content["README.md"] = (output / "README.md").read_bytes()
    summary = {
        "scope": "Actual installed PDE ExtensionsErrorReporter in headless Eclipse; all 83 corpus descriptors and 939 contributions; no startup timing claim.",
        "nativeJarSha256": expected_jar, "nativeRunnerSha256": expected_runner,
        "preferences": baseline["preferences"], "preferenceQualifier": baseline["preferenceQualifier"],
        "controls": [{key: control[key] for key in ["file", "description", "expectation", "harnessCheckPassed",
                                                     "diagnosticCount", "pdeReportedDiagnostic"]}
                     for control in baseline["controls"]],
        "runs": runs,
        "consumer": {key: consumer[key] for key in ["passed", "passedChecks", "checks", "sourceSha256", "jarSha256",
                                                      "codeSources", "bundleVersions", "platformRunning", "exitCode",
                                                      "eclipseErrorEntries", "sourceUnchanged"]},
        "interpretationLimits": [
            "Marker severities reflect explicitly enabled structural ERROR preferences, not default IDE severities.",
            "Native PDE validation accepts invalid boolean values, reversed sequences, unexpected character content, and incomplete sequence arms in a complex choice; passing controls does not imply complete XSD validation.",
            "Unknown extension points and unavailable schemas are coverage gaps, not validated inputs.",
            "The 24 subsequent accessor queries in each retry case are deliberately induced; attempt counts do not establish startup frequency or duration.",
            "There is no additional retained target handle across measured calls. The externaltools source JAR already has one retained handle; its ownership is not established.",
            "Restoration changes missing JAR-entry URLs to copied schema-file URLs; the zero file-handle counts do not show that a preexisting source-JAR handle was closed.",
            "The standalone consumer attempt is excluded setup evidence; only the real OSGi run supplies the 10 passing consumer checks.",
        ],
        "rawArtifacts": {name: {"bytes": len(data), "sha256": digest(data)}
                         for name, data in sorted(content.items())},
    }
    summary_bytes = (json.dumps(summary, indent=2) + "\n").encode()
    (output / "native-validation-summary.json").write_bytes(summary_bytes)
    content["native-validation-summary.json"] = summary_bytes
    archive = output / "native-validation-results.tar.xz"
    with tarfile.open(archive, "w:xz") as package:
        for name, data in sorted(content.items()):
            info = tarfile.TarInfo(name)
            info.size, info.mode, info.mtime = len(data), 0o644, 0
            package.addfile(info, io.BytesIO(data))
    with tarfile.open(archive, "r:xz") as package:
        assert set(package.getnames()) == set(content)
        for member in package.getmembers():
            assert package.extractfile(member).read() == content[member.name], member.name
    (output / "SHA256SUMS").write_text(
        f"{digest(summary_bytes)}  native-validation-summary.json\n"
        f"{digest(archive.read_bytes())}  native-validation-results.tar.xz\n")
    print(json.dumps({"runs": {name: item["summary"] for name, item in runs.items()},
                      "consumerPassedChecks": consumer["passedChecks"], "archive": str(archive),
                      "archiveBytes": archive.stat().st_size, "archiveEntries": len(content),
                      "archiveReadbackVerified": True}, indent=2))


if __name__ == "__main__":
    main()
