#!/usr/bin/env python3
# SPDX-License-Identifier: EPL-2.0
"""Offline reproduction driver. Uses only Python's standard library and JDK 25."""
from pathlib import Path
import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parent
BUILD = ROOT / "build"
RESULTS = ROOT / "reproduced-results"
IMPLEMENTATIONS = ("upstream", "reuse", "coalesced", "combined", "woodstox")
CORPORA = ("original", "safe-indented", "safe-compact")
DEPS = json.loads((ROOT / "provenance/classpaths.json").read_text())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def files_for_manifest():
    return sorted(p for p in ROOT.rglob("*") if p.is_file()
                  and p.relative_to(ROOT).parts[0] not in {"build", "reproduced-results", "__pycache__"}
                  and p.name != "SHA256SUMS")


def manifest():
    files = files_for_manifest()
    (ROOT / "SHA256SUMS").write_text("".join(f"{digest(p)}  {p.relative_to(ROOT).as_posix()}\n" for p in files))
    print(f"Recorded {len(files)} files in SHA256SUMS")


def verify():
    entries = (ROOT / "SHA256SUMS").read_text().splitlines()
    for line in entries:
        expected, relative = line.split("  ", 1)
        path = ROOT / relative
        if not path.is_file() or digest(path) != expected:
            raise SystemExit(f"Missing or changed packaged file: {relative}")
    print(f"Verified {len(entries)} packaged file hashes")


def java_tools():
    home = os.environ.get("JAVA_HOME")
    if not home:
        raise SystemExit("Set JAVA_HOME to a JDK 25 installation.")
    suffix = ".exe" if os.name == "nt" else ""
    java, javac = (Path(home) / "bin" / (name + suffix) for name in ("java", "javac"))
    if not java.is_file() or not javac.is_file():
        raise SystemExit("JAVA_HOME must contain bin/java and bin/javac.")
    version = subprocess.check_output([str(javac), "-version"], stderr=subprocess.STDOUT, text=True)
    if not re.match(r"javac 25(?:\D|$)", version):
        raise SystemExit(f"This reproduction requires JDK 25, found: {version.strip()}")
    return str(java), str(javac)


def selected(name):
    return IMPLEMENTATIONS if name == "all" else (name,)


def dependencies(implementation):
    paths = [BUILD / "pde-core-snapshot"] + [ROOT / p for p in DEPS["eclipse"]]
    if implementation == "woodstox":
        paths.extend(ROOT / p for p in DEPS["woodstox"])
    paths.extend(ROOT / p for p in DEPS["benchmark"])
    return paths


def classpath(implementation):
    return os.pathsep.join(map(str, [BUILD / "bench", BUILD / implementation, *dependencies(implementation)]))


def build(names, javac):
    # Restore the original class-directory layout used in the recorded cold runs.
    snapshot = BUILD / "pde-core-snapshot"
    if snapshot.exists():
        shutil.rmtree(snapshot)
    snapshot.mkdir(parents=True)
    with zipfile.ZipFile(ROOT / DEPS["snapshot"]) as archive:
        archive.extractall(snapshot)
    for implementation in names:
        output = BUILD / implementation
        if output.exists():
            shutil.rmtree(output)
        output.mkdir(parents=True)
        sources = sorted((ROOT / "sources" / implementation).rglob("*.java"))
        cp = os.pathsep.join(map(str, dependencies(implementation)))
        subprocess.run([javac, "-proc:none", "--release", "17", "-cp", cp,
                        "-d", str(output), *map(str, sources)], check=True)
        print(f"Compiled {implementation}: {len(sources)} source files", flush=True)
    bench = BUILD / "bench"
    if bench.exists():
        shutil.rmtree(bench)
    bench.mkdir(parents=True)
    processors = os.pathsep.join(str(ROOT / "lib/benchmark" / p) for p in
                                ("jmh-core-1.37.jar", "jmh-generator-annprocess-1.37.jar"))
    subprocess.run([javac, "--release", "25", "-cp", classpath(names[0]),
                    "-processorpath", processors, "-processor", "org.openjdk.jmh.generators.BenchmarkProcessor",
                    "-d", str(bench), str(ROOT / "src/bench/SchemaLoadBenchmark.java")], check=True)


def command(java, implementation):
    if not (BUILD / implementation).is_dir() or not (BUILD / "bench/META-INF/BenchmarkList").is_file():
        raise SystemExit(f"Build {implementation} first: python3 reproduce.py build --implementation {implementation}")
    return [java, "-Devaluation=" + str(ROOT), "-Dcorpus=" + str(ROOT / "corpus"), "-cp", classpath(implementation)]


def validate(java, names, corpora):
    reference = None
    for implementation in names:
        output = subprocess.check_output(command(java, implementation) +
                                         ["bench.SchemaLoadBenchmark", "validate", *corpora], text=True)
        (RESULTS / f"{implementation}-models.log").write_text(output)
        models = {}
        for line in output.splitlines():
            if line.startswith("MODEL "):
                _, corpus, name, value = line.split()
                models.setdefault(corpus, {})[name] = value
        if set(models) != set(corpora):
            raise AssertionError((implementation, "missing corpus", sorted(models)))
        for corpus, values in models.items():
            if len(values) != 49:
                raise AssertionError((implementation, corpus, len(values)))
            if reference is None:
                reference = values
            if values != reference:
                raise AssertionError((implementation, corpus, "model mismatch"))
        print(f"Validated {implementation}: {len(corpora)} corpora × 49 identical model serializations", flush=True)


def jmh(java, args):
    label = f"{args.implementation}-{args.corpus}"
    with (RESULTS / (label + ".log")).open("w") as log:
        subprocess.run(command(java, args.implementation) +
                       ["org.openjdk.jmh.Main", "^bench.SchemaLoadBenchmark.loadSchemas$", "-p", "variant=" + args.corpus,
                        "-wi", str(args.warmup_iterations), "-w", f"{args.warmup_seconds}s",
                        "-i", str(args.iterations), "-r", f"{args.seconds}s", "-f", str(args.forks),
                        "-rf", "json", "-rff", str(RESULTS / (label + ".json"))],
                       stdout=log, stderr=subprocess.STDOUT, check=True)
    print(f"JMH results: reproduced-results/{label}.json")


def first(java, args):
    names = selected(args.implementation)
    path = RESULTS / f"first-{args.implementation}-{args.corpus}-{args.case}.csv"
    with path.open("w", newline="") as output:
        writer = csv.writer(output)
        writer.writerow(["provider", "trial", "variant", "case", "wall_ms", "cpu_ms", "allocated_bytes",
                         "loaded_classes", "schemas", "include_loads", "elements"])
        for trial in range(args.trials):
            order = names[trial % len(names):] + names[:trial % len(names)]
            for implementation in order:
                cmd = command(java, implementation)
                cmd[1:1] = ["-Xms512m", "-Xmx512m", "-XX:+UseSerialGC", "-XX:ActiveProcessorCount=1"]
                text = subprocess.check_output(cmd + ["bench.SchemaLoadBenchmark", "first", args.corpus, args.case], text=True)
                line, = [line for line in text.splitlines() if line.startswith("FIRST,")]
                writer.writerow([implementation, trial, *line.split(",")[1:]])
            output.flush()
    print(f"First-use results: {path.relative_to(ROOT)}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cpu", type=int, help="Pin this process and JVM children to one Linux CPU")
    modes = parser.add_subparsers(dest="mode", required=True)
    modes.add_parser("manifest", help="Refresh SHA256SUMS after adding final reports/results")
    modes.add_parser("verify", help="Verify packaged hashes without starting Java")
    p = modes.add_parser("build", help="Compile selected source variants and JMH harness offline")
    p.add_argument("--implementation", choices=(*IMPLEMENTATIONS, "all"), default="all")
    p = modes.add_parser("validate", help="Check real PDE model parity and security fixtures")
    p.add_argument("--implementation", choices=(*IMPLEMENTATIONS, "all"), default="all")
    p.add_argument("--corpus", choices=(*CORPORA, "all"), default="all")
    p = modes.add_parser("jmh", help="Measure one implementation/corpus with JMH")
    p.add_argument("--implementation", choices=IMPLEMENTATIONS, required=True)
    p.add_argument("--corpus", choices=CORPORA, default="original")
    for flag, default in [("warmup-iterations", 8), ("warmup-seconds", 2), ("iterations", 6), ("seconds", 1), ("forks", 3)]:
        p.add_argument("--" + flag, type=int, default=default)
    p = modes.add_parser("first", help="Fresh JVM first use; rotate implementations when selecting all")
    p.add_argument("--implementation", choices=(*IMPLEMENTATIONS, "all"), default="all")
    p.add_argument("--corpus", choices=CORPORA, default="original")
    p.add_argument("--case", choices=("views.exsd", "menus.exsd", "all"), default="all")
    p.add_argument("--trials", type=int, default=20)
    args = parser.parse_args()
    if args.mode == "manifest":
        manifest()
        return
    verify()
    if args.mode == "verify":
        return
    if args.cpu is not None:
        if not hasattr(os, "sched_setaffinity"):
            raise SystemExit("--cpu requires Linux; omit it on other systems.")
        os.sched_setaffinity(0, {args.cpu})
    java, javac = java_tools()
    RESULTS.mkdir(exist_ok=True)
    if args.mode == "build":
        build(selected(args.implementation), javac)
    elif args.mode == "validate":
        validate(java, selected(args.implementation), CORPORA if args.corpus == "all" else (args.corpus,))
    elif args.mode == "jmh":
        jmh(java, args)
    else:
        first(java, args)


if __name__ == "__main__":
    main()
