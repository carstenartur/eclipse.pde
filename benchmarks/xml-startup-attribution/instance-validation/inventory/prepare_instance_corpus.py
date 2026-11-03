#!/usr/bin/env python3
"""Prepare original configured-bundle XML for real PDE instance validation.

This is an inventory/copy operation, not a replacement instance validator.
Only bundles explicitly listed in the reference bundles.info are considered.
Source resources require an exact Eclipse-SourceBundle host/version match.
Requires Python 3 and lxml (for source line numbers, not schema validation).
"""

import argparse
from collections import Counter
import csv
import importlib.util
import json
from pathlib import Path
import posixpath
import re
from urllib.parse import unquote, urlparse

from lxml import etree


HELPER_SPEC = importlib.util.spec_from_file_location(
    "prepare_schema_corpus", Path(__file__).resolve().parents[2] / "probe/prepare_schema_corpus.py")
HELPER = importlib.util.module_from_spec(HELPER_SPEC)
HELPER_SPEC.loader.exec_module(HELPER)
INSTRUMENTATION_BUNDLES = {"org.eclipse.pde.xmlstudy.probe"}


def osgi_version(value):
    match = re.fullmatch(r"([0-9]+)(?:\.([0-9]+))?(?:\.([0-9]+))?(?:\.([A-Za-z0-9_-]+))?", value)
    if not match:
        raise ValueError(f"Invalid OSGi bundle version: {value}")
    return tuple(int(match.group(i) or 0) for i in (1, 2, 3)) + (match.group(4) or "",)


def configured_bundles(eclipse_home):
    config = eclipse_home / "configuration/org.eclipse.equinox.simpleconfigurator/bundles.info"
    content = config.read_bytes()
    result = []
    seen = set()
    for line, row in enumerate(csv.reader(content.decode("utf-8").splitlines()), 1):
        if not row or row[0].startswith("#"):
            continue
        if len(row) != 5:
            raise ValueError(f"Expected five bundles.info columns on line {line}: {row}")
        bundle_id, version, location, start_level, autostart = row
        parsed = urlparse(location)
        if parsed.scheme not in ("", "file") or parsed.netloc not in ("", "localhost"):
            raise ValueError(f"Unsupported configured bundle location: {location}")
        path = Path(unquote(parsed.path))
        if not path.is_absolute():
            path = eclipse_home / path
        item = HELPER.read_bundle(path)
        if item is None or item["bundleId"] != bundle_id or osgi_version(item["bundleVersion"]) != osgi_version(version):
            raise ValueError(f"Configured bundle identity differs from its manifest: {bundle_id}@{version}: {path}")
        identity = (bundle_id, osgi_version(version))
        if identity in seen:
            raise ValueError(f"Repeated configured bundle identity: {bundle_id}@{version}")
        seen.add(identity)
        item["configuration"] = {"line": line, "version": version, "location": location, "startLevel": int(start_level),
                                 "autoStart": autostart == "true"}
        metadata = HELPER.headers(item["files"]["META-INF/MANIFEST.MF"])
        item["fragmentHost"] = metadata.get("fragment-host", "").split(";", 1)[0]
        result.append(item)
    return config, content, sorted(result, key=lambda item: (item["bundleId"], osgi_version(item["bundleVersion"])))


def qualified_point(bundle_id, identifier):
    # Extension-point identifiers containing a dot already specify a namespace.
    return identifier if "." in identifier else bundle_id + "." + identifier


def parse(content):
    return etree.fromstring(content, etree.XMLParser(no_network=True, resolve_entities=False))


def xml_inventory(binary, descriptor, content):
    common = {"bundleId": binary["bundleId"], "bundleVersion": binary["bundleVersion"],
              "descriptor": descriptor, "sha256": HELPER.digest(content), "bytes": len(content),
              "archive": binary["archive"], "archiveEntry": descriptor,
              "projectRelativePath": f"projects/{binary['bundleId']}/{descriptor}"}
    declarations, contributions = [], []
    try:
        root = parse(content)
    except etree.XMLSyntaxError as error:
        return {**common, "wellFormed": False, "error": str(error)}, declarations, contributions
    record = {**common, "wellFormed": True, "root": root.tag, "line": root.sourceline,
              "doctype": root.getroottree().docinfo.doctype}
    for child in root:
        if not isinstance(child.tag, str):
            continue
        name = etree.QName(child).localname
        source = {"bundleId": binary["bundleId"], "bundleVersion": binary["bundleVersion"],
                  "descriptor": descriptor, "line": child.sourceline,
                  "xmlPath": root.getroottree().getpath(child), "namespace": etree.QName(child).namespace}
        if name == "extension-point":
            identifier = child.get("id", "")
            declarations.append({**source, "id": identifier,
                                 "extensionPointId": qualified_point(binary["bundleId"], identifier),
                                 "schemaPath": child.get("schema", ""), "name": child.get("name", "")})
        elif name == "extension":
            contributions.append({**source, "extensionPointId": child.get("point", ""),
                                  "extensionId": child.get("id", ""), "name": child.get("name", ""),
                                  "childElements": [node.tag for node in child if isinstance(node.tag, str)],
                                  "elementCount": sum(1 for node in child.iter() if isinstance(node.tag, str))})
    record.update(extensionPointDeclarations=len(declarations), extensionContributions=len(contributions))
    return record, declarations, contributions


def selected_schemas(binary, sources, filtered):
    selected = {}
    for artifact, origin, roots in [(binary, "binary", ["."])] + [
            (source, "source", [".", *source["roots"]]) for source in sources]:
        for name, content in sorted(artifact["files"].items()):
            if not name.endswith((".exsd", ".mxsd")):
                continue
            relative = HELPER.schema_path(name, roots)
            if relative is None:
                filtered.append({"bundleId": binary["bundleId"], "archive": artifact["archive"],
                                 "path": name, "reason": "outside production schema/ root"})
            elif relative not in selected:
                selected[relative] = (artifact, origin, name, content)
    return selected


def schema_record(binary, relative, artifact, origin, entry, content, output):
    record = {"bundleId": binary["bundleId"], "bundleVersion": binary["bundleVersion"],
              "relativePath": relative, "projectRelativePath": f"projects/{binary['bundleId']}/{relative}",
              "file": str(output / "projects" / binary["bundleId"] / relative),
              "origin": origin, "archive": artifact["archive"], "archiveEntry": entry,
              "artifactType": artifact["artifactType"], "archiveSha256": artifact["archiveSha256"],
              "sha256": HELPER.digest(content), "bytes": len(content), "wellFormed": True}
    try:
        root = parse(content)
        record["root"] = root.tag
        record["targetNamespace"] = root.get("targetNamespace", "")
        record["includes"] = [{"schemaLocation": node.get("schemaLocation", ""), "line": node.sourceline}
                              for node in root if isinstance(node.tag, str)
                              and etree.QName(node).localname == "include"]
    except etree.XMLSyntaxError as error:
        record.update(wellFormed=False, error=str(error), includes=[])
    return record


def write_original(directory, relative, content):
    if not HELPER.safe_path(relative):
        raise ValueError(f"Unsafe bundle resource path: {relative}")
    target = directory / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    if target.read_bytes() != content:
        raise ValueError(f"Copied bytes differ: {target}")


def prepare_corpus(eclipse_home, output_directory):
    home, output = Path(eclipse_home).resolve(), Path(output_directory).resolve()
    if output.exists() and any(output.iterdir()):
        raise ValueError(f"Output directory must be new or empty: {output}")
    config, config_content, bundles = configured_bundles(home)
    binaries = [bundle for bundle in bundles if "sourceHost" not in bundle]
    production_binaries = [bundle for bundle in binaries if bundle["bundleId"] not in INSTRUMENTATION_BUNDLES]
    sources = [bundle for bundle in bundles if "sourceHost" in bundle]
    report = {"formatVersion": 1, "eclipseHome": str(home), "outputDirectory": str(output),
              "configuration": {"path": str(config), "sha256": HELPER.digest(config_content)},
              "policy": {"scope": "only bundles listed in the supplied bundles.info, not every plugins/ artifact",
                         "sourceMatching": "exact configured Eclipse-SourceBundle host and version; binary schema bytes win",
                         "schemaRoots": "production schema/ roots, as in the original schema corpus helper",
                         "originals": "binary manifests, plugin.xml, fragment.xml, properties and selected schemas copied byte-for-byte",
                         "projectFixtures": "Java/PDE natures, SchemaBuilder only, output-only classpath, no Java source folders",
                         "automaticBuilding": "must be disabled by the importing headless application before project import",
                         "validation": "inventory only; instance validation is performed separately by the real PDE reporter",
                         "pointMapping": "qualified IDs retained; simple declaration IDs prefixed by declaring bundle ID; real PDE lookup remains authoritative",
                         "externalResolution": "no network access or invented declarations"},
              "toolVersions": {"lxml": list(etree.LXML_VERSION), "libxml2": list(etree.LIBXML_VERSION)},
              "configuredBundles": [], "projects": [], "schemas": [], "descriptors": [],
              "declarations": [], "contributions": [], "missingReferences": [],
              "filteredSchemaFiles": [], "unmatchedSourceBundles": [], "includes": [],
              "excludedInstrumentationBundles": []}
    output.mkdir(parents=True, exist_ok=True)
    matched_sources = set()
    for bundle in bundles:
        record = {key: bundle[key] for key in ("bundleId", "bundleVersion", "archive", "archiveSha256",
                                               "artifactType", "fragmentHost", "configuration")}
        record["role"] = "source" if "sourceHost" in bundle else "binary"
        if bundle["bundleId"] in INSTRUMENTATION_BUNDLES:
            record["productionScope"] = "excluded-instrumentation"
            report["excludedInstrumentationBundles"].append({"bundleId": bundle["bundleId"],
                "bundleVersion": bundle["bundleVersion"], "reason": "Previous study observer, not an Eclipse production contribution"})
        else:
            record["productionScope"] = "source-support" if "sourceHost" in bundle else "included-binary"
        for key in ("sourceHost", "sourceVersion", "roots"):
            if key in bundle:
                record[key] = bundle[key]
        report["configuredBundles"].append(record)
    project_ids = set()
    for binary in production_binaries:
        bid, version = binary["bundleId"], binary["bundleVersion"]
        matching = [source for source in sources if source["sourceHost"] == bid
                    and osgi_version(source["sourceVersion"]) == osgi_version(version)]
        matched_sources.update(source["archive"] for source in matching)
        schemas = selected_schemas(binary, matching, report["filteredSchemaFiles"])
        descriptors = [name for name in ("plugin.xml", "fragment.xml") if name in binary["files"]]
        if not schemas and not descriptors:
            continue
        if bid in project_ids:
            raise ValueError(f"Multiple configured XML/schema providers named {bid}; real target version selection is required")
        project_ids.add(bid)
        directory = output / "projects" / bid
        directory.mkdir(parents=True)
        metadata_files = []
        for relative, content in sorted(binary["files"].items()):
            if relative in ("META-INF/MANIFEST.MF", *descriptors) or relative.endswith(".properties"):
                write_original(directory, relative, content)
                metadata_files.append({"relativePath": relative, "sha256": HELPER.digest(content), "bytes": len(content)})
        for relative, (artifact, origin, entry, content) in sorted(schemas.items()):
            write_original(directory, relative, content)
            report["schemas"].append(schema_record(binary, relative, artifact, origin, entry, content, output))
        for name, content in HELPER.project_files(bid).items():
            write_original(directory, name, content)
        (directory / "bin").mkdir()
        report["projects"].append({"bundleId": bid, "bundleVersion": version, "fragmentHost": binary["fragmentHost"],
                                   "projectName": bid, "directory": str(directory), "projectRelativePath": f"projects/{bid}",
                                   "binaryArchive": binary["archive"], "binaryArchiveSha256": binary["archiveSha256"],
                                   "binaryArtifactType": binary["artifactType"], "descriptors": descriptors,
                                   "sourceArchives": [source["archive"] for source in matching],
                                   "schemaPaths": sorted(schemas), "metadataFiles": metadata_files})
        for descriptor in descriptors:
            item, declarations, contributions = xml_inventory(binary, descriptor, binary["files"][descriptor])
            report["descriptors"].append(item)
            report["declarations"].extend(declarations)
            report["contributions"].extend(contributions)
    report["unmatchedSourceBundles"] = [{key: source[key] for key in ("bundleId", "bundleVersion", "sourceHost", "sourceVersion", "archive")}
                                         for source in sources if source["archive"] not in matched_sources]
    schema_lookup = {(schema["bundleId"], schema["relativePath"]): schema for schema in report["schemas"]}
    declared_lookup = {}
    for declaration in report["declarations"]:
        path = declaration["schemaPath"]
        normalized = posixpath.normpath(path) if path else ""
        schema = schema_lookup.get((declaration["bundleId"], normalized))
        declaration["schemaStatus"] = "present" if schema else "missing-schema" if path else "no-schema-declared"
        if schema:
            declaration["schemaProjectRelativePath"] = schema["projectRelativePath"]
            declaration["schemaSha256"] = schema["sha256"]
        elif path:
            report["missingReferences"].append({"kind": "declared-schema", **declaration})
        declared_lookup.setdefault(declaration["extensionPointId"], []).append(declaration)
    for contribution in report["contributions"]:
        matches = declared_lookup.get(contribution["extensionPointId"], [])
        contribution["declarationCount"] = len(matches)
        if len(matches) == 1:
            declaration = matches[0]
            contribution["schemaStatus"] = declaration["schemaStatus"]
            contribution["providerBundleId"] = declaration["bundleId"]
            contribution["providerDescriptor"] = declaration["descriptor"]
            contribution["providerLine"] = declaration["line"]
            contribution["schemaPath"] = declaration["schemaPath"]
            if "schemaProjectRelativePath" in declaration:
                contribution["schemaProjectRelativePath"] = declaration["schemaProjectRelativePath"]
                contribution["schemaSha256"] = declaration["schemaSha256"]
        else:
            contribution["schemaStatus"] = "undeclared-point" if not matches else "ambiguous-point"
    for schema in report["schemas"]:
        for item in schema["includes"]:
            location = item["schemaLocation"]
            if location.startswith("schema://"):
                host, _, path = location[len("schema://"):].partition("/")
            elif ":" in location:
                report["includes"].append({"bundleId": schema["bundleId"], "schemaPath": schema["relativePath"],
                                           **item, "status": "external-not-fetched"})
                continue
            else:
                host, path = schema["bundleId"], posixpath.normpath(posixpath.join(posixpath.dirname(schema["relativePath"]), location))
            record = {"bundleId": schema["bundleId"], "schemaPath": schema["relativePath"], **item,
                      "targetBundleId": host, "targetPath": path,
                      "status": "present" if (host, path) in schema_lookup else "missing"}
            report["includes"].append(record)
            if record["status"] == "missing":
                report["missingReferences"].append({"kind": "include", **record})
    origins = Counter(schema["origin"] for schema in report["schemas"])
    statuses = Counter(item["schemaStatus"] for item in report["contributions"])
    report["summary"] = {"configuredBundles": len(bundles), "configuredBinaryBundles": len(binaries),
                         "productionBinaryBundles": len(production_binaries),
                         "excludedInstrumentationBundles": len(report["excludedInstrumentationBundles"]),
                         "configuredSourceBundles": len(sources), "projects": len(report["projects"]),
                         "descriptorFiles": len(report["descriptors"]),
                         "pluginXmlFiles": sum(item["descriptor"] == "plugin.xml" for item in report["descriptors"]),
                         "fragmentXmlFiles": sum(item["descriptor"] == "fragment.xml" for item in report["descriptors"]),
                         "schemaFiles": len(report["schemas"]), "schemaBytes": sum(item["bytes"] for item in report["schemas"]),
                         "binarySchemaFiles": origins["binary"], "sourceSchemaFiles": origins["source"],
                         "extensionPointDeclarations": len(report["declarations"]), "extensionContributions": len(report["contributions"]),
                         "contributionSchemaStatus": dict(sorted(statuses.items())),
                         "missingDeclaredSchemas": sum(item["kind"] == "declared-schema" for item in report["missingReferences"]),
                         "missingIncludes": sum(item["kind"] == "include" for item in report["missingReferences"]),
                         "descriptorSyntaxErrors": sum(not item["wellFormed"] for item in report["descriptors"]),
                         "schemaSyntaxErrors": sum(not item["wellFormed"] for item in report["schemas"]),
                         "unmatchedSourceBundles": len(report["unmatchedSourceBundles"])}
    identity = [{key: schema[key] for key in ("bundleId", "bundleVersion", "relativePath", "sha256")} for schema in report["schemas"]]
    report["schemaCorpusSha256"] = HELPER.digest(json.dumps(identity, sort_keys=True, separators=(",", ":")).encode())
    xml_identity = [{key: item[key] for key in ("bundleId", "bundleVersion", "descriptor", "sha256")} for item in report["descriptors"]]
    report["descriptorCorpusSha256"] = HELPER.digest(json.dumps(xml_identity, sort_keys=True, separators=(",", ":")).encode())
    (output / "project-list.txt").write_text("".join(item["directory"] + "\n" for item in report["projects"]), encoding="utf-8")
    (output / "corpus-manifest.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--eclipse-home", required=True, type=Path)
    parser.add_argument("--output-directory", required=True, type=Path)
    args = parser.parse_args()
    report = prepare_corpus(args.eclipse_home, args.output_directory)
    print(json.dumps({"manifest": str(args.output_directory / "corpus-manifest.json"), **report["summary"]}))


if __name__ == "__main__":
    main()
