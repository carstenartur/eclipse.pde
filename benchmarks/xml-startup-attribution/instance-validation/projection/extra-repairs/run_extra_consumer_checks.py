#!/usr/bin/env python3
"""Execute the two exact installed consumer contracts, outside startup timing."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reference", type=Path)
    parser.add_argument("--java-home", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source = Path(__file__).resolve().with_name("ExtraConsumerProbe.java")
    build = args.output.resolve().parent / "extra-consumer-build"
    build.mkdir(parents=True, exist_ok=True)
    classpath = os.pathsep.join(map(str, sorted((args.reference.resolve() / "plugins").glob("*.jar"))))
    result = {"scope": "Actual SDK standalone registry and CSS consumer with fixture contributions; no startup timing",
              "sourceSha256": hashlib.sha256(source.read_bytes()).hexdigest(),
              "reference": str(args.reference.resolve()), "javaHome": str(args.java_home.resolve())}
    compile_run = subprocess.run([str(args.java_home / "bin/javac"), "--release", "21", "-encoding", "UTF-8",
                                  "-classpath", classpath, "-d", str(build), str(source)],
                                 capture_output=True, text=True, timeout=60)
    result.update(compileExit=compile_run.returncode, compileStdout=compile_run.stdout, compileStderr=compile_run.stderr)
    if compile_run.returncode == 0:
        run = subprocess.run([str(args.java_home / "bin/java"), "-classpath",
                              str(build) + os.pathsep + classpath, "ExtraConsumerProbe"],
                             capture_output=True, text=True, timeout=60)
        result.update(exitCode=run.returncode, stdout=run.stdout, stderr=run.stderr,
                      passedChecks=sum(line.startswith("PASS ") for line in run.stdout.splitlines()))
    result["passed"] = result["compileExit"] == 0 and result.get("exitCode") == 0 and result.get("passedChecks") == 8
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
