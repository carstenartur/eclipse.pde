#!/usr/bin/env python3
"""Compile against real Eclipse installation bundles and package the probe."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("eclipse_install", type=Path, help="Eclipse directory containing plugins/")
    parser.add_argument("--javac", type=Path, help="JDK 21+ javac; use the runtime's JDK")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    plugins = args.eclipse_install.resolve() / "plugins"
    if not plugins.is_dir():
        parser.error(f"Not an Eclipse installation: {plugins} is missing")
    javac = args.javac or (Path(os.environ["JAVA_HOME"]) / "bin/javac" if os.environ.get("JAVA_HOME") else None)
    javac = javac or (Path(shutil.which("javac")) if shutil.which("javac") else None)
    if javac is None or not javac.is_file():
        parser.error("A real JDK is required; pass --javac /path/to/jdk/bin/javac")
    javac = javac.resolve()
    java = javac.with_name("java")
    if not java.is_file():
        parser.error(f"java not found alongside javac: {java}")
    jars = sorted(plugins.glob("*.jar"))
    required = (
        "org/eclipse/osgi/service/runnable/StartupMonitor.class",
        "org/eclipse/core/resources/ResourcesPlugin.class",
        "org/eclipse/core/runtime/jobs/Job.class",
        "org/eclipse/equinox/app/IApplication.class",
        "org/eclipse/ui/PlatformUI.class",
        "org/eclipse/swt/widgets/Display.class",
    )
    available = set()
    for jar in jars:
        with zipfile.ZipFile(jar) as bundle:
            available.update(name for name in required if name in bundle.namelist())
    missing = sorted(set(required) - available)
    if missing:
        parser.error("Real Eclipse API classes are missing: " + ", ".join(missing))
    build = root / "build"
    classes = build / "classes"
    tests = build / "test-classes"
    for directory in (classes, tests):
        if directory.exists():
            shutil.rmtree(directory)
        directory.mkdir(parents=True)
    classpath = os.pathsep.join(str(jar) for jar in jars)
    sources = sorted((root / "src").rglob("*.java"))
    subprocess.run([str(javac), "--release", "21", "-encoding", "UTF-8", "-Xlint:all",
                    "-classpath", classpath, "-d", str(classes), *map(str, sources)], check=True)
    test_sources = sorted((root / "tests").rglob("*.java"))
    subprocess.run([str(javac), "--release", "21", "-encoding", "UTF-8", "-Xlint:all",
                    "-classpath", str(classes), "-d", str(tests), *map(str, test_sources)], check=True)
    subprocess.run([str(java), "-classpath", os.pathsep.join((str(classes), str(tests))),
                    "org.eclipse.pde.xmlstudy.probe.ProbeLogicTest"], check=True)
    subprocess.run([str(java), "-classpath", os.pathsep.join((str(classes), str(tests))),
                    "org.eclipse.pde.xmlstudy.probe.FdDiagnosticsTest"], check=True)
    subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", str(root / "tests"), "-p", "test_*.py"], check=True)
    artifact = build / "org.eclipse.pde.xmlstudy.probe_1.0.0.jar"
    entries = {"META-INF/MANIFEST.MF": (root / "META-INF/MANIFEST.MF").read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"),
               "plugin.xml": (root / "plugin.xml").read_bytes()}
    entries.update((file.relative_to(classes).as_posix(), file.read_bytes()) for file in classes.rglob("*.class"))
    with zipfile.ZipFile(artifact, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for name, content in sorted(entries.items()):
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            bundle.writestr(info, content)
    print(json.dumps({"jar": str(artifact), "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
                      "eclipseInstall": str(args.eclipse_install.resolve()), "javac": str(javac),
                      "classCount": len(entries) - 2}))


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as error:
        sys.exit(error.returncode)
