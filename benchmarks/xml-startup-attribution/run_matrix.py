#!/usr/bin/env python3
"""Run fresh JVMs in randomized matched blocks; retain failed runs verbatim."""
import argparse
import importlib.util
import hashlib
import json
import os
from pathlib import Path
import platform
import random
import re
import shutil
import signal
import subprocess
import time

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("verify_run", HERE / "probe/verify_run.py")
verifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verifier)


def replace_directory(source, target):
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target, symlinks=True)


def execute(command, log, deadline=95):
    started = time.monotonic()
    with log.open("w") as stream:
        process = subprocess.Popen(command, stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            code = process.wait(timeout=deadline)
            timeout = False
        except subprocess.TimeoutExpired:
            timeout = True
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            code = process.returncode
    return {"exitCode": code, "externalTimeout": timeout, "launchToExitMs": round(1000 * (time.monotonic() - started), 3)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment", required=True, type=Path)
    parser.add_argument("--xvfb-wrapper", type=Path, help="Optional display wrapper; omit when DISPLAY is already usable")
    parser.add_argument("--launcher", required=True, type=Path)
    parser.add_argument("--java-home", required=True, type=Path)
    parser.add_argument("--blocks", type=int, default=5)
    parser.add_argument("--seed", type=int, default=20261103)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--skip-preparation", action="store_true")
    args = parser.parse_args()
    root = args.experiment.resolve()
    manifest = json.loads((root / "experiment-manifest.json").read_text())
    primary = [item for item in manifest["variants"] if not item["diagnostic"]]
    variants = {item["name"]: item for item in manifest["variants"]}
    raw = root / "runs"
    raw.mkdir(exist_ok=True)
    environment_file = root / "execution-environment.json"
    if not environment_file.exists():
        environment_file.write_text(json.dumps({
            "platform": platform.platform(), "machine": platform.machine(), "python": platform.python_version(),
            "cpuCount": os.cpu_count(), "cpuAffinity": sorted(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else None,
            "jvmOptions": ["-Xms256m", "-Xmx1024m", "--enable-native-access=ALL-UNNAMED"],
            "runnerSha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "verifierSha256": hashlib.sha256((HERE / "probe/verify_run.py").read_bytes()).hexdigest(),
            "xvfbWrapperSha256": hashlib.sha256(args.xvfb_wrapper.read_bytes()).hexdigest() if args.xvfb_wrapper else None,
        }, indent=2) + "\n")
    runs = []

    def command(variant, run_id, output, prepare=False):
        directory = root / variant["name"]
        install = directory / "eclipse"
        arguments = (["python3", str(args.xvfb_wrapper)] if args.xvfb_wrapper else []) + [str(args.java_home / "bin/java"),
                     "-Xms256m", "-Xmx1024m", "--enable-native-access=ALL-UNNAMED",
                     "-Dxml.study.runId=" + run_id]
        if prepare:
            arguments += ["-Dxml.study.enabled=false", "-Dxml.study.projectList=" + str(directory / "project-list.txt")]
        else:
            arguments += ["-Dxml.study.scenario=validation", "-Dxml.study.output=" + str(output),
                          "-Dxml.study.fdDiagnostics=" + str(variant["diagnostic"]).lower()]
        return arguments + ["-jar", str(args.launcher), "-install", str(install),
                            "-configuration", str(install / "configuration"), "-data", str(directory / "workspace"),
                            "-nosplash", "-consoleLog", "-application",
                            "org.eclipse.pde.xmlstudy.probe.prepareWorkspace" if prepare else "org.eclipse.ui.ide.workbench"]

    def run(variant, run_id, measured, block=None, restore=False):
        directory = root / variant["name"]
        if restore:
            replace_directory(directory / "seed-workspace", directory / "workspace")
            replace_directory(directory / "seed-configuration", directory / "eclipse/configuration")
        log = raw / (run_id + ".log")
        output = raw / (run_id + ".json")
        if log.exists() or output.exists():
            raise SystemExit(f"Run artifacts already exist and will not be overwritten: {run_id}")
        result = {"runId": run_id, "variant": variant["name"], "block": block, "measured": measured,
                  "diagnostic": variant["diagnostic"], "handler": variant["handler"], "whitespace": variant["whitespace"]}
        result.update(execute(command(variant, run_id, output), log))
        try:
            result["eclipseErrorEntries"] = len(re.findall(r"!ENTRY\s+\S+\s+4\s", log.read_text(errors="replace")))
            if result["eclipseErrorEntries"]:
                raise ValueError("Eclipse error log entries invalidate this environment run; inspect the retained log")
            # stdout and stderr can interleave within a physical line. The
            # probe's atomic JSON file retains every complete phase record.
            result["verification"] = verifier.verify(output, "validation")
            data = json.loads(output.read_text())
            phases = {phase["phase"]: phase for phase in data["phases"]}
            validation = phases["validation_finished"]["validation"]
            expected_projects = sorted(item["projectName"] for item in manifest["corpusManifest"]["projects"])
            if sorted(validation["projects"]) != expected_projects:
                raise ValueError("Validation project list does not match the entire declared corpus")
            if validation["schemaFiles"] != manifest["corpusManifest"]["summary"]["schemaFiles"]:
                raise ValueError("Validation schema count does not match the entire declared corpus")
            result.update(readyMs=phases["workbench_ready"]["jvmUptimeMs"],
                          applicationRunningMs=phases["application_running"]["jvmUptimeMs"],
                          readyCpuNs=phases["workbench_ready"]["processCpuNs"],
                          settledMs=phases["validation_settled"]["jvmUptimeMs"],
                          buildMs=phases["validation_finished"]["validation"]["buildWallMs"],
                          buildNs=phases["validation_finished"]["validation"]["buildWallNs"],
                          buildCpuNs=phases["validation_finished"]["validation"]["buildProcessCpuNs"],
                          schemaFiles=phases["validation_finished"]["validation"]["schemaFiles"],
                          markers=phases["validation_finished"]["validation"]["markers"])
            if result["exitCode"] != 0 or result["externalTimeout"] or result["verification"]["failedJobs"]:
                raise ValueError("Process failure, timeout or failed Eclipse job")
            result["cpuValid"] = result["readyCpuNs"] >= 0 and result["buildCpuNs"] >= 0
            result["status"] = "ok"
        except (ValueError, OSError, KeyError) as error:
            result.update(status="failed", error=str(error))
        runs.append(result)
        (root / "run-results.json").write_text(json.dumps(runs, indent=2) + "\n")
        print(json.dumps({key: value for key, value in result.items() if key not in ("verification", "markers")}), flush=True)
        return result

    if not args.skip_preparation:
        for variant in manifest["variants"]:
            directory = root / variant["name"]
            if (directory / "seed-workspace").exists():
                raise SystemExit("Prepared workspaces already exist; use --skip-preparation")
            name = "prepare-" + variant["name"]
            result = execute(command(variant, name, raw / (name + ".json"), prepare=True), raw / (name + ".log"))
            if result["exitCode"] or result["externalTimeout"]:
                raise SystemExit(f"Workspace preparation failed: {name}: {result}")
            result = run(variant, "warmup-" + variant["name"], False)
            if result["status"] != "ok":
                raise SystemExit("Warmup failed; primary matrix has not started")
            shutil.copytree(directory / "workspace", directory / "seed-workspace", symlinks=True)
            shutil.copytree(directory / "eclipse/configuration", directory / "seed-configuration", symlinks=True)
    else:
        if (root / "run-results.json").exists():
            runs.extend(json.loads((root / "run-results.json").read_text()))
    if args.prepare_only:
        return
    order = []
    rng = random.Random(args.seed)
    for block in range(1, args.blocks + 1):
        names = [item["name"] for item in primary]
        rng.shuffle(names)
        for name in names:
            order.append({"block": block, "variant": name})
    if order:
        (root / "schedule.json").write_text(json.dumps({"seed": args.seed, "order": order}, indent=2) + "\n")
    for item in order:
        run(variants[item["variant"]], f"block-{item['block']:02d}-{item['variant']}", True, item["block"], restore=True)
    for variant in manifest["variants"]:
        if variant["diagnostic"]:
            run(variant, "diagnostic-" + variant["name"], False, restore=True)
    if any(row["status"] != "ok" for row in runs):
        raise SystemExit("One or more runs failed; retain them and inspect the logs")


if __name__ == "__main__":
    main()
