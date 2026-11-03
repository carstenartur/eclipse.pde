#!/usr/bin/env python3
# SPDX-License-Identifier: EPL-2.0
"""Measure real file:/jar: schema handles with baseline PDE source and real SDK jars.

Each protocol/input/abbreviation case runs in a fresh JVM. /proc/self/fd samples
are taken immediately after every operation. A positive control opens a real
fixture handle and proves the filter detects it. No forced GC or disposal is
used to reduce the measured counts. This is not an Eclipse startup benchmark.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import zipfile


BASELINE = "ba6a5d6f2f455ab7dfe972ce678d07d9f80de267"
CORE = "ui/org.eclipse.pde.core/src/org/eclipse/pde/internal/core/"
SOURCES = [CORE + path for path in (
    "schema/Schema.java", "schema/SchemaDescriptor.java", "util/SchemaUtil.java", "XMLDefaultHandler.java",
)]
FIXTURES = {
    "valid": "<schema><element name='root'/></schema>",
    "malformed_xml": "<schema><element name='root'></schema>",
    "missing_element_name": "<schema><element/></schema>",
}


def command(args):
    result = subprocess.run(args, text=True, capture_output=True, check=False)
    return {"exit_code": result.returncode, "stdout": result.stdout, "stderr": result.stderr}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--revision", default=BASELINE)
    parser.add_argument("--java-home", type=Path, required=True)
    parser.add_argument("--sdk-plugins", type=Path, required=True)
    parser.add_argument("--pde-core-jar", type=Path, required=True)
    parser.add_argument("--warmup", type=int, default=64)
    parser.add_argument("--rounds", type=int, default=5)
    parser.add_argument("--operations", type=int, default=128)
    parser.add_argument("--output", type=Path, default=Path("benchmarks/xml-startup-attribution/schema_handle-results.json"))
    args = parser.parse_args()
    if min(args.warmup, args.rounds, args.operations) < 1:
        parser.error("warmup, rounds, and operations must be positive")
    root = args.root.resolve()
    java = args.java_home.resolve() / "bin/java"
    javac = args.java_home.resolve() / "bin/javac"
    plugins = args.sdk_plugins.resolve()
    pde_jar = args.pde_core_jar.resolve()
    revision = subprocess.check_output(["git", "-C", str(root), "rev-parse", args.revision + "^{commit}"], text=True).strip()
    probe = root / "benchmarks/xml-startup-attribution/schema_handle_probe.java"
    sdk_jars = sorted(path for path in plugins.glob("*.jar") if not path.name.startswith("org.eclipse.pde.core_"))
    if not sdk_jars:
        parser.error("SDK plugins directory contains no jars")
    report = {
        "description": "Real-source file and JAR handle lifecycle probe with synthetic schema inputs.",
        "baseline_commit": revision,
        "java_version": command([str(java), "-version"]),
        "pde_sdk_sha256": hashlib.sha256(pde_jar.read_bytes()).hexdigest(),
        "sdk_plugins": str(plugins),
        "source_sha256": {},
        "probe_sha256": hashlib.sha256(probe.read_bytes()).hexdigest(),
        "fixture_inputs": FIXTURES,
        "warmup_operations_per_phase": args.warmup,
        "rounds_per_phase": args.rounds,
        "operations_per_round": args.operations,
        "forced_gc": False,
        "limitations": [
            "Classpath-only lifecycle measurement, not a full Eclipse/OSGi process or startup timing.",
            "Synthetic failure cases are not evidence of defective installed production schemas.",
            "Stable fixture handle counts do not rule out unrelated IDE handles or leaks on untested paths/providers/JDKs.",
            "Total FD changes may reflect class loading; fixture handles and target deltas are recorded separately.",
            "Probe-created /proc directory handles are reported and excluded from adjusted /proc totals.",
        ],
        "cases": [],
    }
    with tempfile.TemporaryDirectory(prefix="pde-schema-handles-") as directory:
        temporary = Path(directory)
        official = temporary / "official-pde-classes"
        with zipfile.ZipFile(pde_jar) as archive:
            archive.extractall(official)
        sources = []
        for relative in SOURCES:
            content = subprocess.check_output(["git", "-C", str(root), "show", f"{revision}:{relative}"])
            report["source_sha256"][relative] = hashlib.sha256(content).hexdigest()
            target = temporary / "baseline-source" / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
            sources.append(target)
        classes = temporary / "classes"
        classes.mkdir()
        classpath = os.pathsep.join(str(path) for path in [classes, official, *sdk_jars])
        report["compile"] = command([
            str(javac), "--release", "21", "-encoding", "UTF-8", "-cp", classpath,
            "-d", str(classes), *map(str, sources), str(probe),
        ])
        if report["compile"]["exit_code"] == 0:
            for protocol in ("file", "jar"):
                for fixture, xml in FIXTURES.items():
                    for abbreviated in (False, True):
                        location = temporary / "fixtures" / f"{protocol}-{fixture}-{abbreviated}"
                        location.mkdir(parents=True)
                        if protocol == "file":
                            backing = location / "fixture.exsd"
                            backing.write_text(xml, encoding="utf-8")
                        else:
                            backing = location / "fixture.jar"
                            with zipfile.ZipFile(backing, "w", compression=zipfile.ZIP_DEFLATED) as jar:
                                jar.writestr("schema/fixture.exsd", xml)
                        result = command([
                            str(java), "-cp", classpath, "SchemaHandleProbe", str(backing), protocol, fixture,
                            str(fixture == "valid").lower(), str(abbreviated).lower(),
                            str(args.warmup), str(args.rounds), str(args.operations),
                        ])
                        entry = {"protocol": protocol, "fixture": fixture, "abbreviated": abbreviated, "process": result}
                        if result["stdout"].strip():
                            try:
                                entry["observations"] = json.loads(result["stdout"])
                            except json.JSONDecodeError as error:
                                entry["output_error"] = str(error)
                        report["cases"].append(entry)
                        observed = entry.get("observations", {})
                        maxima = [phase["max_fixture_handles_after_operation"] for phase in observed.get("phases", [])]
                        print(f"{protocol} {fixture} abbreviated={abbreviated}: exit={result['exit_code']} max_fixture_handles={maxima}", flush=True)
        report["summary"] = {
            "cases_expected": 12,
            "cases_completed": len(report["cases"]),
            "cases_failed": sum(case["process"]["exit_code"] != 0 or "observations" not in case for case in report["cases"]),
            "startup_effect_demonstrated": False,
        }
    output = args.output if args.output.is_absolute() else root / args.output
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if report["compile"]["exit_code"] != 0:
        print(report["compile"]["stdout"] + report["compile"]["stderr"], end="")
        return report["compile"]["exit_code"]
    return 0 if report["summary"]["cases_completed"] == 12 and report["summary"]["cases_failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
