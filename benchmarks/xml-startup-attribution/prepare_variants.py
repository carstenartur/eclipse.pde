#!/usr/bin/env python3
"""Prepare matched disposable SDKs for the H (handler) x W (indentation) study."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import zipfile

from xml_formatting import tabs_for_schema_indentation

BASE = "ba6a5d6f2f455ab7dfe972ce678d07d9f80de267"
PATCH = "de6efde7becdbcc5515c0a45c908d2592ccd465e"
HANDLER = "ui/org.eclipse.pde.core/src/org/eclipse/pde/internal/core/XMLDefaultHandler.java"
SCHEMA = "ui/org.eclipse.pde.core/src/org/eclipse/pde/internal/core/schema/Schema.java"
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def source(ref, path):
    return subprocess.check_output(["git", "show", ref + ":" + path], cwd=REPO)


def is_signature(name):
    name = name.upper()
    return name.startswith("META-INF/") and (name.endswith((".SF", ".RSA", ".DSA", ".EC")) or name.rsplit("/", 1)[-1].startswith("SIG-"))


def compile_classes(java_home, classpath, handler, diagnostic):
    with tempfile.TemporaryDirectory(prefix="pde-study-compile-") as temporary:
        folder = Path(temporary)
        handler_path = folder / "XMLDefaultHandler.java"
        if diagnostic:
            anchor = "public void startDocument() throws SAXException {"
            assert handler.count(anchor) == 1
            handler = handler.replace(anchor, anchor + '\n\t\tSystem.out.println("XML_STUDY_HANDLER\\t" + fAbbreviated);')
        handler_path.write_text(handler)
        sources = [handler_path]
        if diagnostic:
            schema = source(BASE, SCHEMA).decode()
            anchor = "public void load(InputStream stream) {"
            schema = schema.replace(anchor, anchor + "\n\t\tlong xmlStudyStarted = System.nanoTime();", 1)
            anchor = '\t\t} catch (Exception e) {\n\t\t\tPDECore.logException(e);\n\t\t}\n\t}\n\n\tprivate ISchemaAttribute processAttribute'
            assert schema.count(anchor) == 1
            schema = schema.replace(anchor,
                '\t\t} catch (Exception e) {\n\t\t\tPDECore.logException(e);\n'
                '\t\t} finally {\n\t\t\tSystem.out.println("XML_STUDY_SCHEMA\\t" + fAbbreviated + "\\t" + fLoaded + "\\t" + (System.nanoTime() - xmlStudyStarted) + "\\t" + fURL);\n'
                '\t\t}\n\t}\n\n\tprivate ISchemaAttribute processAttribute')
            schema_path = folder / "Schema.java"
            schema_path.write_text(schema)
            sources.append(schema_path)
        classes = folder / "classes"
        classes.mkdir()
        arguments = folder / "javac.args"
        arguments.write_text("\n".join(json.dumps(str(x)) for x in ["-encoding", "UTF-8", "-cp", classpath,
                             "-sourcepath", "", "-d", classes, *sources]))
        subprocess.run([str(java_home / "bin/javac"), "@" + str(arguments)], check=True)
        return {str(path.relative_to(classes)): path.read_bytes() for path in classes.rglob("*.class")}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference-install", required=True, type=Path)
    parser.add_argument("--corpus", required=True, type=Path)
    parser.add_argument("--java-home", required=True, type=Path)
    parser.add_argument("--probe-jar", required=True, type=Path)
    parser.add_argument("--output-directory", required=True, type=Path)
    args = parser.parse_args()
    reference = args.reference_install.resolve()
    output = args.output_directory.resolve()
    if output.exists():
        raise SystemExit("Use a new output directory; existing experiments are not overwritten")
    plugins = sorted((reference / "plugins").iterdir())
    core = [path for path in plugins if path.name.startswith("org.eclipse.pde.core_")]
    if len(core) != 1:
        raise SystemExit("Expected exactly one binary PDE Core bundle")
    schemas_by_bundle = {}
    input_manifest = []
    for path in plugins:
        if path.is_dir():
            schemas = [str(p.relative_to(path)) for p in path.rglob("*") if p.is_file() and p.suffix in (".exsd", ".mxsd")]
            hashes = {str(p.relative_to(path)): sha(p.read_bytes()) for p in sorted(path.rglob("*")) if p.is_file()}
            digest = sha(json.dumps(hashes, sort_keys=True).encode())
        else:
            with zipfile.ZipFile(path) as archive:
                schemas = [name for name in archive.namelist() if name.endswith((".exsd", ".mxsd"))]
            digest = sha(path.read_bytes())
        schemas_by_bundle[path.name] = schemas
        input_manifest.append({"path": path.name, "sha256": digest, "directory": path.is_dir(), "schemaFiles": len(schemas)})
    classpath = os.pathsep.join(str(p.resolve()) for p in plugins if ".source_" not in p.name)
    output.mkdir(parents=True)
    variants = []
    for handler, whitespace, diagnostic in [(0, 0, False), (1, 0, False), (0, 1, False), (1, 1, False), (0, 0, True)]:
        name = f"H{handler}W{whitespace}" + ("D1" if diagnostic else "")
        destination = output / name
        install = destination / "eclipse"
        (install / "plugins").mkdir(parents=True)
        classes = compile_classes(args.java_home, classpath, source(PATCH if handler else BASE, HANDLER).decode(), diagnostic)
        changed_schema_files = original_schema_bytes = formatted_schema_bytes = 0
        for path in plugins:
            target = install / "plugins" / path.name
            if path.name.startswith("org.eclipse.pde.xmlstudy.probe_"):
                shutil.copyfile(args.probe_jar, target)
                continue
            schemas = schemas_by_bundle[path.name]
            if not schemas and path != core[0]:
                target.symlink_to(path.resolve(), target_is_directory=path.is_dir())
                continue
            if path.is_dir():
                shutil.copytree(path, target)
                if path == core[0]:
                    for relative, data in classes.items():
                        member = target / relative
                        member.parent.mkdir(parents=True, exist_ok=True)
                        member.write_bytes(data)
                for relative in schemas:
                    member = target / relative
                    before = member.read_bytes()
                    after = tabs_for_schema_indentation(before) if whitespace else before
                    member.write_bytes(after)
                    original_schema_bytes += len(before)
                    formatted_schema_bytes += len(after)
                    changed_schema_files += before != after
            else:
                # All four cells rebuild this exact same set of archives and
                # strip signatures equally, including baseline controls.
                with zipfile.ZipFile(path) as original, zipfile.ZipFile(target, "w") as rebuilt:
                    for member in original.infolist():
                        if is_signature(member.filename):
                            continue
                        data = original.read(member)
                        if member.filename in schemas:
                            after = tabs_for_schema_indentation(data) if whitespace else data
                            original_schema_bytes += len(data)
                            formatted_schema_bytes += len(after)
                            changed_schema_files += data != after
                            data = after
                        if path == core[0] and member.filename in classes:
                            data = classes[member.filename]
                        rebuilt.writestr(member, data)
        configuration = install / "configuration"
        (configuration / "org.eclipse.equinox.simpleconfigurator").mkdir(parents=True)
        for relative in ("config.ini", "org.eclipse.equinox.simpleconfigurator/bundles.info"):
            contents = (reference / "configuration" / relative).read_text()
            (configuration / relative).write_text(contents.replace(str(reference), str(install)))
        for relative in (".eclipseproduct",):
            if (reference / relative).is_file():
                shutil.copyfile(reference / relative, install / relative)
        projects = destination / "projects"
        shutil.copytree(args.corpus / "projects", projects)
        for path in projects.rglob("*"):
            if path.is_file() and path.suffix in (".exsd", ".mxsd") and whitespace:
                path.write_bytes(tabs_for_schema_indentation(path.read_bytes()))
        project_paths = sorted(path.parent for path in projects.rglob(".project"))
        (destination / "project-list.txt").write_text("".join(str(path) + "\n" for path in project_paths))
        variants.append({"name": name, "handler": handler, "whitespace": whitespace, "diagnostic": diagnostic,
                         "install": str(install), "projects": len(project_paths),
                         "sdkSchemaFilesChanged": changed_schema_files, "sdkSchemaBytesBefore": original_schema_bytes,
                         "sdkSchemaBytesAfter": formatted_schema_bytes,
                         "handlerSourceSha256": sha(source(PATCH if handler else BASE, HANDLER)),
                         "classSha256": {path: sha(data) for path, data in classes.items()}})
        print(json.dumps(variants[-1]), flush=True)
    manifest = {"formatVersion": 1, "baseline": BASE, "patch": PATCH,
                "referenceInstall": str(reference), "javaHome": str(args.java_home.resolve()),
                "corpusManifest": json.loads((args.corpus / "corpus-manifest.json").read_text()),
                "inputs": input_manifest, "variants": variants,
                "controls": ["same rebuilt archives/signature stripping in every cell", "source schemas present",
                             "only targeted EXSD indentation changed; comments and documentation preserved",
                             "diagnostic classes and FD scans excluded from primary timing cells"]}
    (output / "experiment-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    main()
