#!/usr/bin/env python3
"""Restore pinned original schema resources to a new disposable corpus.

The vendored resources come from the exact source commits embedded in the
frozen binary manifests. This reproduces already merged packaging repairs;
it does not invent a schema, update an installed bundle, or rewrite an XML
contribution. Resource bytes and binary source references are verified first.
"""

import argparse
from collections import Counter
import importlib.util
import json
from pathlib import Path
import shutil


SPEC = importlib.util.spec_from_file_location("prepare_instance_corpus", Path(__file__).with_name("prepare_instance_corpus.py"))
CORPUS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CORPUS)


def verify_files(directory, expected):
    for relative, sha in expected.items():
        path = directory / relative
        if not path.is_file() or CORPUS.HELPER.digest(path.read_bytes()) != sha:
            raise ValueError(f"Original corpus file differs from frozen hash: {path}")


def restore(original_directory, output_directory, provenance_path=None):
    original = Path(original_directory).resolve()
    output = Path(output_directory).resolve()
    if output == original or output.is_relative_to(original) or original.is_relative_to(output):
        raise ValueError("Restoration output must be independent of the original corpus")
    if output.exists():
        raise ValueError(f"Restoration output must not exist: {output}")
    provenance_path = Path(provenance_path or Path(__file__).parent / "resources/provenance.json").resolve()
    provenance_bytes = provenance_path.read_bytes()
    provenance = json.loads(provenance_bytes)
    manifest_path = original / "corpus-manifest.json"
    manifest_bytes = manifest_path.read_bytes()
    report = json.loads(manifest_bytes)
    projects = {project["bundleId"]: project for project in report["projects"]}
    originals = {item["projectRelativePath"]: item["sha256"] for item in report["schemas"] + report["descriptors"]}
    for project in report["projects"]:
        for item in project["metadataFiles"]:
            originals[project["projectRelativePath"] + "/" + item["relativePath"]] = item["sha256"]
    verify_files(original, originals)
    resources = []
    target_keys = set()
    for item in provenance["resources"]:
        relative = item["relativePath"]
        if not CORPUS.HELPER.safe_path(relative) or not CORPUS.HELPER.safe_path(item["resourceFile"]):
            raise ValueError(f"Unsafe restoration resource path: {item}")
        path = provenance_path.parent.parent / item["resourceFile"]
        data = path.read_bytes()
        if len(data) != item["bytes"] or CORPUS.HELPER.digest(data) != item["sha256"]:
            raise ValueError(f"Resource hash differs from pinned upstream content: {path}")
        project = projects.get(item["bundleId"])
        if project is None or project["bundleVersion"] != item["bundleVersion"]:
            raise ValueError(f"Restoration binary version differs from provenance: {item['bundleId']}")
        binary_manifest = original / project["projectRelativePath"] / "META-INF/MANIFEST.MF"
        source_reference = CORPUS.HELPER.headers(binary_manifest.read_bytes()).get("eclipse-sourcereferences", "")
        if source_reference != item["binarySourceReference"]:
            raise ValueError(f"Binary source reference differs from pinned upstream provenance: {item['bundleId']}")
        target = original / project["projectRelativePath"] / relative
        key = (item["bundleId"], relative)
        if target.exists() or key in target_keys:
            raise ValueError(f"Restoration would overwrite an existing schema: {target}")
        if not any((declaration["bundleId"], declaration["schemaPath"]) == key for declaration in report["declarations"]):
            raise ValueError(f"Restoration does not match an existing schema declaration: {key}")
        record = CORPUS.schema_record(
            {"bundleId": item["bundleId"], "bundleVersion": item["bundleVersion"]}, relative,
            {"archive": item["sourceUrl"], "artifactType": "upstream-git-file", "archiveSha256": item["sha256"]},
            "restored-upstream-source", item["sourcePath"], data, output)
        if not record["wellFormed"] or record["includes"]:
            raise ValueError("This bounded restoration expects well-formed, self-contained upstream schemas")
        record["upstreamProvenance"] = item
        resources.append((project, item, data, record))
        target_keys.add(key)
    shutil.copytree(original, output)
    report["outputDirectory"] = str(output)
    for project in report["projects"]:
        project["directory"] = str(output / project["projectRelativePath"])
    for schema in report["schemas"]:
        schema["file"] = str(output / schema["projectRelativePath"])
    for project, item, data, record in resources:
        target = output / project["projectRelativePath"] / item["relativePath"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        project["schemaPaths"] = sorted([*project["schemaPaths"], item["relativePath"]])
        report["schemas"].append(record)
    report["schemas"].sort(key=lambda item: (item["bundleId"], item["bundleVersion"], item["relativePath"]))
    by_point = {}
    lookup = {(item["bundleId"], item["relativePath"]): item for item in report["schemas"]}
    for declaration in report["declarations"]:
        key = (declaration["bundleId"], declaration["schemaPath"])
        if key in target_keys:
            schema = lookup[key]
            declaration.update(schemaStatus="present", schemaProjectRelativePath=schema["projectRelativePath"],
                               schemaSha256=schema["sha256"])
        by_point.setdefault(declaration["extensionPointId"], []).append(declaration)
    for contribution in report["contributions"]:
        matches = by_point.get(contribution["extensionPointId"], [])
        if len(matches) != 1:
            continue
        declaration = matches[0]
        if (declaration["bundleId"], declaration["schemaPath"]) in target_keys:
            contribution.update(schemaStatus="present", schemaProjectRelativePath=declaration["schemaProjectRelativePath"],
                                schemaSha256=declaration["schemaSha256"])
    report["missingReferences"] = [item for item in report["missingReferences"]
        if not (item["kind"] == "declared-schema" and (item["bundleId"], item["schemaPath"]) in target_keys)]
    report["summary"].update(
        schemaFiles=len(report["schemas"]), schemaBytes=sum(item["bytes"] for item in report["schemas"]),
        restoredSchemaFiles=len(resources),
        missingDeclaredSchemas=sum(item["kind"] == "declared-schema" for item in report["missingReferences"]),
        contributionSchemaStatus=dict(Counter(item["schemaStatus"] for item in report["contributions"])))
    identity = [{key: item[key] for key in ("bundleId", "bundleVersion", "relativePath", "sha256")} for item in report["schemas"]]
    report["schemaCorpusSha256"] = CORPUS.HELPER.digest(json.dumps(identity, sort_keys=True, separators=(",", ":")).encode())
    verify_files(output, originals)
    verify_files(original, originals)
    if manifest_path.read_bytes() != manifest_bytes:
        raise ValueError("Original corpus manifest changed during restoration")
    report["referenceRepair"] = {
        "purpose": "Apply existing upstream packaging repairs to the frozen reference corpus using exact original source bytes",
        "originalCorpus": str(original), "originalManifestSha256": CORPUS.HELPER.digest(manifest_bytes),
        "provenanceFile": str(provenance_path), "provenanceSha256": CORPUS.HELPER.digest(provenance_bytes),
        "resources": provenance["resources"], "originalCorpusUnchanged": True,
        "allDescriptorHashesUnchanged": True, "allOriginalSchemaHashesUnchanged": True,
        "runtimeCodeChanged": False}
    (output / "project-list.txt").write_text("".join(project["directory"] + "\n" for project in report["projects"]), encoding="utf-8")
    (output / "corpus-manifest.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original-corpus", type=Path, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument("--provenance", type=Path)
    args = parser.parse_args()
    report = restore(args.original_corpus, args.output_directory, args.provenance)
    print(json.dumps({"manifest": str(args.output_directory / "corpus-manifest.json"), **report["summary"]}))


if __name__ == "__main__":
    main()
