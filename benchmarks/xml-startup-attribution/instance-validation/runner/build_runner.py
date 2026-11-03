#!/usr/bin/env python3
"""Compile the diagnostic application against an existing, real Eclipse SDK."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import zipfile


def build(reference: Path, javac: Path) -> dict:
    here = Path(__file__).resolve().parent
    jars = sorted((reference.resolve() / "plugins").glob("*.jar"))
    required = {
        "org/eclipse/pde/internal/core/builders/ExtensionsErrorReporter.class",
        "org/eclipse/pde/internal/core/schema/SchemaRegistry.class",
        "org/eclipse/core/resources/ResourcesPlugin.class",
        "org/eclipse/equinox/app/IApplication.class",
    }
    available = set()
    for jar in jars:
        with zipfile.ZipFile(jar) as archive:
            available.update(required.intersection(archive.namelist()))
    if available != required:
        raise ValueError(f"Real SDK classes unavailable: {sorted(required - available)}")
    classes = here / "build/classes"
    if classes.exists():
        shutil.rmtree(classes)
    classes.mkdir(parents=True)
    sources = sorted((here / "src").rglob("*.java"))
    subprocess.run([
        str(javac.resolve()), "--release", "21", "-encoding", "UTF-8", "-Xlint:all",
        "-classpath", os.pathsep.join(map(str, jars)), "-d", str(classes), *map(str, sources),
    ], check=True)
    artifact = here / "build/org.eclipse.pde.xmlstudy.instances_1.0.0.jar"
    entries = {
        "META-INF/MANIFEST.MF": (here / "META-INF/MANIFEST.MF").read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"),
        "plugin.xml": (here / "plugin.xml").read_bytes(),
    }
    entries.update((path.relative_to(classes).as_posix(), path.read_bytes()) for path in classes.rglob("*.class"))
    with zipfile.ZipFile(artifact, "w") as archive:
        for name, content in sorted(entries.items()):
            info = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, content)
    return {"jar": str(artifact), "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
            "reference": str(reference.resolve()), "javac": str(javac.resolve()),
            "classCount": len(entries) - 2,
            "sourceHashes": {str(path.relative_to(here)): hashlib.sha256(path.read_bytes()).hexdigest() for path in sources}}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reference", type=Path)
    parser.add_argument("--javac", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.reference, args.javac), indent=2))
