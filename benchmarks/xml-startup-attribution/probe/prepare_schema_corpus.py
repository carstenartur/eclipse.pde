#!/usr/bin/env python3
"""Copy actual installed schemas into disposable projects for the real PDE builder."""

import argparse
from collections import Counter
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path, PurePosixPath
import posixpath
import re
import shlex
import xml.etree.ElementTree as ET
import zipfile


def digest(data):
    return hashlib.sha256(data).hexdigest()


def headers(data):
    lines = data.decode("utf-8", "replace").replace("\r\n", "\n").replace("\n ", "")
    return {key.lower(): value.strip() for line in lines.split("\n\n", 1)[0].splitlines()
            if ":" in line for key, value in [line.split(":", 1)]}


def source_header(value):
    lexer = shlex.shlex(value, posix=True)
    lexer.whitespace = ";"
    lexer.whitespace_split = True
    lexer.commenters = ""
    pieces = list(lexer)
    attributes = {}
    for piece in pieces[1:]:
        key, separator, value = piece.replace(":=", "=", 1).partition("=")
        if separator:
            attributes[key.strip()] = value.strip()
    return pieces[0].strip(), attributes


def safe_path(name):
    path = PurePosixPath(name)
    return not path.is_absolute() and ".." not in path.parts and "\\" not in name


def schema_path(name, roots):
    if not safe_path(name):
        return None
    for root in roots:
        root = root.strip().strip("/")
        prefix = "" if root in ("", ".") else root + "/"
        if name.startswith(prefix):
            relative = name[len(prefix):]
            if relative.startswith("schema/") and relative.endswith((".exsd", ".mxsd")):
                return relative
    return None


def read_bundle(path):
    with ExitStack() as resources:
        if path.is_dir():
            names = {file.relative_to(path).as_posix() for file in path.rglob("*") if file.is_file()}
            read = lambda name: (path / name).read_bytes()
            artifact_type = "directory"
        else:
            archive = resources.enter_context(zipfile.ZipFile(path))
            names = set(archive.namelist())
            read = archive.read
            artifact_type = "jar"
        if "META-INF/MANIFEST.MF" not in names:
            return None
        raw_manifest = read("META-INF/MANIFEST.MF")
        metadata = headers(raw_manifest)
        if "bundle-symbolicname" not in metadata:
            return None
        bundle_id = metadata["bundle-symbolicname"].split(";", 1)[0].strip()
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", bundle_id) or bundle_id in (".", ".."):
            raise ValueError(f"Unsafe Bundle-SymbolicName: {bundle_id}")
        selected = {name: read(name) for name in sorted(names)
                    if safe_path(name) and (name in ("META-INF/MANIFEST.MF", "plugin.xml", "fragment.xml")
                    or name.endswith((".properties", ".exsd", ".mxsd")))}
        if artifact_type == "directory":
            tree = hashlib.sha256()
            for name in sorted(names):
                tree.update(name.encode("utf-8") + b"\0")
                tree.update(hashlib.sha256(read(name)).digest())
            artifact_hash = tree.hexdigest()
        else:
            artifact_hash = digest(path.read_bytes())
    result = {"bundleId": bundle_id, "bundleVersion": metadata.get("bundle-version", ""),
              "archive": str(path.absolute()), "artifactType": artifact_type,
              "archiveSha256": artifact_hash, "files": selected}
    if "eclipse-sourcebundle" in metadata:
        host, attributes = source_header(metadata["eclipse-sourcebundle"])
        result.update(sourceHost=host, sourceVersion=attributes.get("version", ""),
                      roots=attributes.get("roots", ".").split(","))
    return result


def xml_bytes(element):
    ET.indent(element, space="  ")
    return ET.tostring(element, encoding="utf-8", xml_declaration=True) + b"\n"


def project_files(bundle_id):
    project = ET.Element("projectDescription")
    ET.SubElement(project, "name").text = bundle_id
    ET.SubElement(project, "comment").text = "Disposable schema-only validation fixture; original bundle metadata retained."
    ET.SubElement(project, "projects")
    command = ET.SubElement(ET.SubElement(project, "buildSpec"), "buildCommand")
    ET.SubElement(command, "name").text = "org.eclipse.pde.SchemaBuilder"
    ET.SubElement(command, "arguments")
    natures = ET.SubElement(project, "natures")
    for nature in ("org.eclipse.jdt.core.javanature", "org.eclipse.pde.PluginNature"):
        ET.SubElement(natures, "nature").text = nature
    classpath = ET.Element("classpath")
    ET.SubElement(classpath, "classpathentry", kind="output", path="bin")
    return {".project": xml_bytes(project), ".classpath": xml_bytes(classpath),
            ".settings/org.eclipse.pde.prefs": b"eclipse.preferences.version=1\ncompilers.s.create-docs=false\n"}


def prepare_corpus(eclipse_home, output_directory, source_directory=None):
    eclipse_home = Path(eclipse_home).resolve()
    output_directory = Path(output_directory).resolve()
    if output_directory.exists() and any(output_directory.iterdir()):
        raise ValueError(f"Output directory must be new or empty: {output_directory}")
    plugins = eclipse_home / "plugins"
    if not plugins.is_dir():
        raise ValueError(f"Missing Eclipse plugins directory: {plugins}")
    paths = sorted(path for path in plugins.iterdir()
                   if (path.is_file() and path.suffix == ".jar") or (path.is_dir() and (path / "META-INF/MANIFEST.MF").is_file()))
    if source_directory:
        paths += sorted(Path(source_directory).resolve().glob("*.jar"))
    bundles = []
    seen = set()
    for path in paths:
        if path.resolve() in seen:
            continue
        seen.add(path.resolve())
        bundle = read_bundle(path)
        if bundle:
            bundles.append(bundle)
    binaries = [bundle for bundle in bundles if "sourceHost" not in bundle]
    sources = [bundle for bundle in bundles if "sourceHost" in bundle]
    report = {"formatVersion": 1, "eclipseHome": str(eclipse_home), "outputDirectory": str(output_directory),
              "policy": {"schemaRoots": "top-level schema/ resources, plus schema/ under declared Eclipse-SourceBundle roots",
                         "extensions": [".exsd", ".mxsd"], "duplicates": "prefer binary resources",
                         "sourceMatching": "exact Eclipse-SourceBundle host and version",
                         "builder": "org.eclipse.pde.SchemaBuilder", "javaSourceFolders": [],
                         "automaticBuilding": "disabled by PrepApplication",
                         "documentationGeneration": "explicitly disabled in .settings/org.eclipse.pde.prefs in all variants",
                         "metadata": "original binary MANIFEST.MF, plugin.xml, fragment.xml and .properties bytes",
                         "xmlSyntax": "check well-formedness only; preserve and report malformed production inputs",
                         "archiveScope": "JAR and unpacked directory bundles in the supplied reference installation",
                         "directoryHash": "SHA-256 of sorted relative UTF-8 filename, NUL, raw SHA-256 file digest for each file"},
              "projects": [], "schemas": [], "declaredSchemas": [], "missingReferences": [],
              "filteredSchemaFiles": [], "schemaSyntaxErrors": [], "descriptorSyntaxErrors": [],
              "unmatchedSourceBundles": []}
    output_directory.mkdir(parents=True, exist_ok=True)
    provider_ids = set()
    matched_sources = set()
    schema_contents = {}
    for binary in sorted(binaries, key=lambda item: (item["bundleId"], item["bundleVersion"])):
        bundle_id, version = binary["bundleId"], binary["bundleVersion"]
        matching = [source for source in sources if source["sourceHost"] == bundle_id and source["sourceVersion"] == version]
        selected = {}
        for artifact, origin, roots in [(binary, "binary", ["."])] + [(source, "source", [".", *source["roots"]]) for source in matching]:
            if origin == "source":
                matched_sources.add(artifact["archive"])
            for name, content in artifact["files"].items():
                if not name.endswith((".exsd", ".mxsd")):
                    continue
                relative = schema_path(name, roots)
                if relative is None:
                    report["filteredSchemaFiles"].append({"bundleId": bundle_id, "archive": artifact["archive"],
                                                         "path": name, "reason": "outside production schema/ root"})
                elif relative not in selected:
                    selected[relative] = (artifact, origin, name, content)
        declarations = []
        for descriptor in ("plugin.xml", "fragment.xml"):
            if descriptor not in binary["files"]:
                continue
            try:
                document = ET.fromstring(binary["files"][descriptor])
                for point in document:
                    if point.tag.rsplit("}", 1)[-1] == "extension-point" and point.get("schema"):
                        declarations.append({"bundleId": bundle_id, "bundleVersion": version, "descriptor": descriptor,
                                             "extensionPointId": point.get("id", ""), "schemaPath": point.get("schema")})
            except ET.ParseError as error:
                report["descriptorSyntaxErrors"].append({"bundleId": bundle_id, "path": descriptor, "error": str(error)})
        if not selected and not declarations:
            continue
        if bundle_id in provider_ids:
            raise ValueError(f"Multiple installed versions provide schemas for {bundle_id}; select one reference version explicitly")
        provider_ids.add(bundle_id)
        directory = output_directory / "projects" / bundle_id
        directory.mkdir(parents=True)
        metadata_files = []
        for name, content in binary["files"].items():
            if name in ("META-INF/MANIFEST.MF", "plugin.xml", "fragment.xml") or name.endswith(".properties"):
                target = directory / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
                metadata_files.append({"relativePath": name, "sha256": digest(content), "bytes": len(content)})
        for relative, (artifact, origin, archive_entry, content) in sorted(selected.items()):
            target = directory / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
            record = {"bundleId": bundle_id, "bundleVersion": version, "relativePath": relative,
                      "projectRelativePath": f"projects/{bundle_id}/{relative}", "file": str(target),
                      "origin": origin, "archive": artifact["archive"], "archiveEntry": archive_entry,
                      "artifactType": artifact["artifactType"],
                      "archiveSha256": artifact["archiveSha256"], "bytes": len(content), "sha256": digest(content),
                      "wellFormed": True}
            try:
                ET.fromstring(content)
            except ET.ParseError as error:
                record.update(wellFormed=False, xmlSyntaxError={"message": str(error), "line": error.position[0], "column": error.position[1]})
                report["schemaSyntaxErrors"].append({"bundleId": bundle_id, "path": relative, **record["xmlSyntaxError"]})
            report["schemas"].append(record)
            schema_contents[(bundle_id, relative)] = content
        for name, content in project_files(bundle_id).items():
            target = directory / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        (directory / "bin").mkdir()
        report["projects"].append({"bundleId": bundle_id, "bundleVersion": version, "projectName": bundle_id,
                                   "directory": str(directory), "projectRelativePath": f"projects/{bundle_id}",
                                   "binaryArchive": binary["archive"], "binaryArchiveSha256": binary["archiveSha256"],
                                   "binaryArtifactType": binary["artifactType"],
                                   "sourceArchives": [source["archive"] for source in matching],
                                   "schemaPaths": sorted(selected), "metadataFiles": metadata_files})
        for declaration in declarations:
            path = declaration["schemaPath"]
            found = selected.get(path)
            declaration["status"] = found[1] if found else "missing"
            report["declaredSchemas"].append(declaration)
            if not found:
                report["missingReferences"].append({"kind": "declared-schema", **declaration})
    for source in sources:
        if source["archive"] not in matched_sources:
            report["unmatchedSourceBundles"].append({key: source[key] for key in ("bundleId", "bundleVersion", "sourceHost", "sourceVersion", "archive")})
    # Read-only include inventory; no schema declarations or content are synthesized.
    includes = []
    for (bundle_id, relative), content in sorted(schema_contents.items()):
        try:
            document = ET.fromstring(content)
        except ET.ParseError:
            continue
        for node in document:
            if node.tag.rsplit("}", 1)[-1] != "include" or not node.get("schemaLocation"):
                continue
            location = node.get("schemaLocation")
            if location.startswith("schema://"):
                host, _, target_path = location[len("schema://"):].partition("/")
            elif "://" in location:
                includes.append({"bundleId": bundle_id, "schemaPath": relative, "location": location, "status": "external-not-fetched"})
                continue
            else:
                host, target_path = bundle_id, posixpath.normpath(posixpath.join(posixpath.dirname(relative), location))
            found = (host, target_path) in schema_contents
            reference = {"kind": "include", "bundleId": bundle_id, "schemaPath": relative, "location": location,
                         "targetBundleId": host, "targetPath": target_path, "status": "present" if found else "missing"}
            includes.append(reference)
            if not found:
                report["missingReferences"].append(reference)
    report["includes"] = includes
    origins = Counter(item["origin"] for item in report["schemas"])
    report["summary"] = {"binaryBundlesScanned": len(binaries), "sourceBundlesScanned": len(sources),
                         "projects": len(report["projects"]), "schemaFiles": len(report["schemas"]),
                         "exsdFiles": sum(item["relativePath"].endswith(".exsd") for item in report["schemas"]),
                         "mxsdFiles": sum(item["relativePath"].endswith(".mxsd") for item in report["schemas"]),
                         "binarySchemaFiles": origins["binary"], "sourceSchemaFiles": origins["source"],
                         "schemaBytes": sum(item["bytes"] for item in report["schemas"]),
                         "xmlSyntaxErrors": len(report["schemaSyntaxErrors"]), "declaredSchemaReferences": len(report["declaredSchemas"]),
                         "missingDeclaredSchemas": sum(item["kind"] == "declared-schema" for item in report["missingReferences"]),
                         "missingIncludes": sum(item["kind"] == "include" for item in report["missingReferences"]),
                         "filteredSchemaFiles": len(report["filteredSchemaFiles"])}
    if not report["schemas"]:
        raise ValueError("No production schema resources found in the reference bundles")
    identity = [{key: item[key] for key in ("bundleId", "bundleVersion", "relativePath", "sha256")} for item in report["schemas"]]
    report["schemaCorpusSha256"] = digest(json.dumps(identity, sort_keys=True, separators=(",", ":")).encode())
    # One consistency pass verifies the actual files emitted for the forthcoming PDE run.
    for item in report["schemas"]:
        copied = (output_directory / item["projectRelativePath"]).read_bytes()
        if len(copied) != item["bytes"] or digest(copied) != item["sha256"]:
            raise ValueError(f"Copied schema mismatch: {item['projectRelativePath']}")
    (output_directory / "project-list.txt").write_text("".join(project["directory"] + "\n" for project in report["projects"]), encoding="utf-8")
    (output_directory / "corpus-manifest.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--eclipse-home", required=True, type=Path)
    parser.add_argument("--output-directory", required=True, type=Path)
    parser.add_argument("--source-directory", type=Path, help="Optional extra directory of matching source JARs")
    args = parser.parse_args()
    report = prepare_corpus(args.eclipse_home, args.output_directory, args.source_directory)
    print(json.dumps({"outputDirectory": report["outputDirectory"], "manifest": str(Path(report["outputDirectory"]) / "corpus-manifest.json"),
                      "projectList": str(Path(report["outputDirectory"]) / "project-list.txt"), **report["summary"]}))


if __name__ == "__main__":
    main()
