#!/usr/bin/env python3
"""Run the unchanged bounded consumer probe in a real, initialized Eclipse OSGi app."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import zipfile


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reference", type=Path)
    parser.add_argument("--java-home", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args()
    directory = Path(__file__).resolve().parent
    source = directory / "ConsumerContractProbe.java"
    wrapper = directory.parent / "runner/consumer-probe"
    reference, output = args.reference.resolve(), args.output.resolve()
    root = output.with_name(output.stem + "-run")
    if output.exists() or (root.exists() and any(root.iterdir())):
        raise SystemExit(f"Refusing to overwrite existing consumer evidence: {output} / {root}")
    root.mkdir(parents=True, exist_ok=True)
    build = wrapper / "build/classes"
    if build.exists():
        shutil.rmtree(build)
    build.mkdir(parents=True)
    jars = sorted((reference / "plugins").glob("*.jar"))
    classpath = os.pathsep.join(map(str, jars))
    sources = [source, *sorted((wrapper / "src").rglob("*.java"))]
    compile_command = [str(args.java_home / "bin/javac"), "--release", "21", "-encoding", "UTF-8",
                       "-classpath", classpath, "-d", str(build), *map(str, sources)]
    source_hash = sha256(source)
    compiled = subprocess.run(compile_command, text=True, capture_output=True, timeout=60)
    result = {"sourceSha256": source_hash,
              "reference": str(reference), "javaHome": str(args.java_home.resolve()),
              "compileExit": compiled.returncode, "compileStdout": compiled.stdout,
              "compileStderr": compiled.stderr,
              "compileCommand": compile_command,
              "wrapperSourceHashes": {str(p.relative_to(wrapper)): sha256(p)
                                      for p in sources if p != source},
              "launcherSha256": sha256(Path(__file__)),
              "scope": "Unchanged ConsumerContractProbe in a real OSGi IApplication; actual SDK expression conversion/evaluation and hasFolder consumer semantics; no startup timing",
              "passed": False}
    if compiled.returncode == 0:
        artifact = wrapper / "build/org.eclipse.pde.xmlstudy.consumer_1.0.0.jar"
        entries = {
            "META-INF/MANIFEST.MF": (wrapper / "META-INF/MANIFEST.MF").read_bytes()
                .replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"),
            "plugin.xml": (wrapper / "plugin.xml").read_bytes(),
        }
        entries.update((p.relative_to(build).as_posix(), p.read_bytes()) for p in build.rglob("*.class"))
        with zipfile.ZipFile(artifact, "w") as archive:
            for name, content in sorted(entries.items()):
                info = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o644 << 16
                archive.writestr(info, content)
        result["jarSha256"] = sha256(artifact)
        result["jar"] = str(artifact)
        install = root / "eclipse"
        (install / "plugins").mkdir(parents=True)
        for item in sorted((reference / "plugins").iterdir()):
            (install / "plugins" / item.name).symlink_to(item.resolve(), target_is_directory=item.is_dir())
        shutil.copy2(artifact, install / "plugins" / artifact.name)
        configuration = install / "configuration"
        (configuration / "org.eclipse.equinox.simpleconfigurator").mkdir(parents=True)
        shutil.copy2(reference / "configuration/config.ini", configuration / "config.ini")
        bundles = reference / "configuration/org.eclipse.equinox.simpleconfigurator/bundles.info"
        (configuration / "org.eclipse.equinox.simpleconfigurator/bundles.info").write_text(
            bundles.read_text().rstrip() + f"\norg.eclipse.pde.xmlstudy.consumer,1.0.0,plugins/{artifact.name},4,false\n")
        launchers = sorted((install / "plugins").glob("org.eclipse.equinox.launcher_*.jar"))
        if len(launchers) != 1:
            raise ValueError(f"Expected exactly one Equinox launcher: {launchers}")
        application_output = root / "application-result.json"
        command = [str((args.java_home / "bin/java").resolve()), "-Xms256m", "-Xmx1024m",
                   "--enable-native-access=ALL-UNNAMED", "-Dxml.study.enabled=false",
                   "-Dxml.consumer.source=" + str(source),
                   "-Dxml.consumer.sourceSha256=" + source_hash,
                   "-Dxml.consumer.output=" + str(application_output),
                   "-jar", str(launchers[0]), "-install", str(install),
                   "-configuration", str(configuration), "-data", str(root / "workspace"),
                   "-nosplash", "-consoleLog", "-application", "org.eclipse.pde.xmlstudy.consumer.check"]
        result["command"] = command
        result["timeoutSeconds"] = args.timeout
        result["applicationOutput"] = str(application_output)
        result["eclipseLog"] = str(root / "eclipse.log")
        result["sdkBundleHashes"] = {p.name: sha256(p) for p in jars
                                     if p.name.startswith(("org.eclipse.core.expressions_", "org.eclipse.ui.ide_"))}
        with (root / "eclipse.log").open("w") as log:
            try:
                run = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, timeout=args.timeout)
                result.update(exitCode=run.returncode, timedOut=False)
            except subprocess.TimeoutExpired:
                result.update(exitCode=None, timedOut=True)
        result["eclipseErrorEntries"] = len(re.findall(r"!ENTRY\s+\S+\s+4\s",
                                                      (root / "eclipse.log").read_text(errors="replace")))
        result["sourceUnchanged"] = sha256(source) == source_hash
        if application_output.exists():
            application_result = json.loads(application_output.read_text())
            result["applicationResult"] = application_result
            for key in ["passedChecks", "checks", "codeSources", "bundleVersions", "platformRunning"]:
                result[key] = application_result.get(key)
            result["passed"] = (application_result.get("passed") is True
                                and application_result.get("sourceSha256") == source_hash
                                and result["exitCode"] == 0 and not result["timedOut"]
                                and result["eclipseErrorEntries"] == 0 and result["sourceUnchanged"])
    output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: result.get(k) for k in ["passed", "passedChecks", "sourceSha256", "jarSha256",
                                               "exitCode", "eclipseErrorEntries", "sourceUnchanged", "codeSources"]}, indent=2))
    raise SystemExit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
