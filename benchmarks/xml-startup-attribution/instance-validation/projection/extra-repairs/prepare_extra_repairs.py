#!/usr/bin/env python3
"""Copy a frozen corpus and apply evidenced cardinality/companion schema repairs."""

import argparse
import difflib
import hashlib
import json
from pathlib import Path
import shutil


TARGETS = {
    "default-handler-parameters": (
        "org.eclipse.ui/schema/commands.exsd",
        '<element ref="parameter"/>',
        '<element ref="parameter" minOccurs="0" maxOccurs="unbounded"/>'),
    "multiple-element-providers": (
        "org.eclipse.e4.ui.css.core/schema/org.eclipse.e4.ui.css.core.elementProvider.exsd",
        '<element ref="provider"/>',
        '<element ref="provider" maxOccurs="unbounded"/>'),
    "navigator-enablement-companion": (
        "org.eclipse.ui.navigator/schema/navigatorContent.exsd", None, None),
}
DEFAULT_INTERVENTIONS = ("default-handler-parameters", "multiple-element-providers")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def enablement_block(text):
    marker = '<element name="enablement">'
    if text.count(marker) != 1:
        raise ValueError("Expected one inspected enablement declaration")
    start = text.index(marker)
    end = text.index("</element>", start) + len("</element>")
    return text[start:end]


def repair(name, original):
    _, before, after = TARGETS[name]
    text = original.decode("utf-8")
    if name == "navigator-enablement-companion":
        block = enablement_block(text)
        opening = '<sequence minOccurs="0" maxOccurs="unbounded">'
        if block.count(opening) != 1 or block.count("</sequence>") != 1:
            raise ValueError("The inspected navigator enablement compositor changed")
        replacement = block.replace(opening, '<choice minOccurs="0" maxOccurs="unbounded">')
        return text.replace(block, replacement.replace("</sequence>", "</choice>")).encode("utf-8")
    if text.count(before) != 1:
        raise ValueError(f"The inspected cardinality declaration changed: {name}")
    return text.replace(before, after).encode("utf-8")


def prepare(source, destination, interventions=None):
    interventions = list(interventions or DEFAULT_INTERVENTIONS)
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if destination.exists():
        raise ValueError(f"Destination exists: {destination}")
    manifest_bytes = (source / "corpus-manifest.json").read_bytes()
    inventory = json.loads(manifest_bytes)
    for row in inventory["schemas"] + inventory["descriptors"]:
        if digest((source / row["projectRelativePath"]).read_bytes()) != row["sha256"]:
            raise ValueError(f"Frozen input changed: {row['projectRelativePath']}")
    if "navigator-enablement-companion" in interventions:
        core = (source / "projects/org.eclipse.core.expressions/schema/expressionLanguage.exsd").read_text()
        if '<choice minOccurs="0" maxOccurs="unbounded">' not in enablement_block(core):
            raise ValueError("The navigator companion requires the shared core enablement choice repair first")
    shutil.copytree(source, destination)
    patches = destination / "repairs"
    patches.mkdir(exist_ok=True)
    changes = []
    for name in interventions:
        relative, _, _ = TARGETS[name]
        path = destination / "projects" / relative
        before = path.read_bytes()
        after = repair(name, before)
        path.write_bytes(after)
        upstream = "bundles/" + relative
        patch = "".join(difflib.unified_diff(before.decode().splitlines(keepends=True),
            after.decode().splitlines(keepends=True), fromfile="a/" + upstream, tofile="b/" + upstream))
        (patches / (name + ".patch")).write_text(patch)
        changes.append({"intervention": name, "projectRelativePath": "projects/" + relative,
                        "upstreamPath": upstream, "beforeSha256": digest(before),
                        "afterSha256": digest(after), "beforeBytes": len(before), "afterBytes": len(after)})
    changed = {row["projectRelativePath"]: row for row in changes}
    for row in inventory["schemas"]:
        row["file"] = str(destination / row["projectRelativePath"])
        change = changed.get(row["projectRelativePath"])
        if change:
            row["originalSha256"] = row["sha256"]
            row.update(sha256=change["afterSha256"], bytes=change["afterBytes"], repair=change["intervention"])
    for row in inventory["declarations"] + inventory["contributions"]:
        change = changed.get(row.get("schemaProjectRelativePath"))
        if change:
            row["schemaSha256"] = change["afterSha256"]
    for row in inventory["projects"]:
        row["directory"] = str(destination / row["projectRelativePath"])
    for row in inventory["descriptors"]:
        if "file" in row:
            row["file"] = str(destination / row["projectRelativePath"])
        if digest((destination / row["projectRelativePath"]).read_bytes()) != row["sha256"]:
            raise ValueError("A repair changed an XML instance")
    inventory["outputDirectory"] = str(destination)
    inventory["summary"]["schemaBytes"] = sum(row["bytes"] for row in inventory["schemas"])
    identity = [{key: row[key] for key in ("bundleId", "bundleVersion", "relativePath", "sha256")}
                for row in inventory["schemas"]]
    inventory["schemaCorpusSha256"] = digest(json.dumps(identity, sort_keys=True, separators=(",", ":")).encode())
    previous = inventory.get("repairExperiment", {})
    inventory["repairExperiment"] = {
        "originalInventorySha256": previous.get("originalInventorySha256", digest(manifest_bytes)),
        "originalSchemaCorpusSha256": previous.get("originalSchemaCorpusSha256",
                                                    json.loads(manifest_bytes)["schemaCorpusSha256"]),
        "immediateSourceInventorySha256": digest(manifest_bytes),
        "descriptorBytesUnchanged": True, "changes": previous.get("changes", []) + changes}
    (destination / "corpus-manifest.json").write_text(json.dumps(inventory, indent=2) + "\n")
    (destination / "project-list.txt").write_text("".join(str(destination / p["projectRelativePath"]) + "\n"
                                                       for p in inventory["projects"]))
    return inventory["repairExperiment"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("corpus", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--only", choices=list(TARGETS), action="append")
    args = parser.parse_args()
    print(json.dumps(prepare(args.corpus, args.destination, args.only), indent=2))
