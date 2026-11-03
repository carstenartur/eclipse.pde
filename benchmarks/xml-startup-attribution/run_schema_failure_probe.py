#!/usr/bin/env python3
"""Run the actual source Schema/handler against real Eclipse SDK dependencies."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import zipfile

p = argparse.ArgumentParser()
p.add_argument("--eclipse-home", required=True, type=Path)
p.add_argument("--java-home", required=True, type=Path)
p.add_argument("--extra-jar", action="append", type=Path, default=[])
p.add_argument("--output", required=True, type=Path)
a = p.parse_args()
here = Path(__file__).resolve().parent
repo = here.parents[1]
jars = list(dict.fromkeys(jar.resolve() for jar in
    sorted((a.eclipse_home / "plugins").glob("*.jar")) + a.extra_jar))
if not jars or any(not jar.is_file() for jar in jars):
    raise SystemExit("A real Eclipse plugins directory and readable jars are required")
sources = [
    repo / "ui/org.eclipse.pde.core/src/org/eclipse/pde/internal/core/schema/Schema.java",
    repo / "ui/org.eclipse.pde.core/src/org/eclipse/pde/internal/core/XMLDefaultHandler.java",
    here / "src/SchemaFailureProbe.java",
]
dependencies = {}
with tempfile.TemporaryDirectory(prefix="pde-schema-failure-") as tmp:
    runtime_jars = []
    for jar in jars:
        if jar.name.startswith("org.eclipse.pde.core-") or jar.name.startswith("org.eclipse.pde.core_"):
            # A classpath cannot mix signed SDK classes and recompiled classes
            # in one package. Strip signatures only in this disposable copy.
            dependencies[jar.name] = hashlib.sha256(jar.read_bytes()).hexdigest()
            unsigned = Path(tmp) / jar.name
            with zipfile.ZipFile(jar) as source, zipfile.ZipFile(unsigned, "w") as target:
                for member in source.infolist():
                    name = member.filename.upper()
                    signature = name.startswith("META-INF/") and (
                        name.endswith((".SF", ".RSA", ".DSA", ".EC"))
                        or name.split("/")[-1].startswith("SIG-"))
                    if not signature:
                        target.writestr(member, source.read(member))
            runtime_jars.append(unsigned)
        else:
            runtime_jars.append(jar)
    classpath = os.pathsep.join(str(jar) for jar in runtime_jars)
    classes = Path(tmp) / "classes"
    classes.mkdir()
    compile_args = Path(tmp) / "javac.args"
    compile_args.write_text("\n".join(json.dumps(str(x)) for x in [
        "-encoding", "UTF-8", "-cp", classpath, "-d", classes, *sources,
    ]))
    subprocess.run([str(a.java_home / "bin/javac"), "@" + str(compile_args)], check=True)
    result = subprocess.run([
        str(a.java_home / "bin/java"), "-cp", str(classes) + os.pathsep + classpath,
        "SchemaFailureProbe",
    ], check=True, text=True, stdout=subprocess.PIPE)
    observations = [json.loads(line) for line in result.stdout.splitlines()]
manifest = {
    "description": "Synthetic failure mechanism; not an Eclipse startup measurement",
    "sources": {str(s.relative_to(repo)): hashlib.sha256(s.read_bytes()).hexdigest() for s in sources},
    "original_pde_sdk_sha256": dependencies,
    "dependency_handling": "Only temporary PDE SDK copies have signature entries removed; original jars are unchanged",
    "observations": observations,
}
a.output.parent.mkdir(parents=True, exist_ok=True)
a.output.write_text(json.dumps(manifest, indent=2) + "\n")
print(result.stdout, end="")
print("Verified real-source load counts; result written to", a.output)
