#!/usr/bin/env python3
"""Apply only the evidenced schema repairs to a new, fully recorded corpus copy."""

import argparse
import difflib
import hashlib
import json
from pathlib import Path
import shutil


TARGETS = {
    "has-folder": ("org.eclipse.ui.ide/schema/projectConfigurators.exsd",
                   "bundles/org.eclipse.ui.ide/schema/projectConfigurators.exsd"),
    "expression-choices": ("org.eclipse.core.expressions/schema/expressionLanguage.exsd",
                           "runtime/bundles/org.eclipse.core.expressions/schema/expressionLanguage.exsd"),
}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def repair(name, original):
    text = original.decode("utf-8")
    if name == "expression-choices":
        opening = '<sequence minOccurs="0" maxOccurs="unbounded">'
        if text.count(opening) != 7 or text.count("</sequence>") != 7:
            raise ValueError("The seven inspected expression compositors changed")
        return text.replace(opening, '<choice minOccurs="0" maxOccurs="unbounded">').replace(
            "</sequence>", "</choice>").encode("utf-8")
    reference = '            <element ref="hasFile"/>'
    declaration = '   <element name="hasFile">'
    if text.count(reference) != 1 or text.count(declaration) != 1 or 'name="hasFolder"' in text:
        raise ValueError("The inspected project configurator schema changed")
    text = text.replace(reference, '            <element ref="hasFolder"/>\n' + reference)
    folder = '''   <element name="hasFolder">
      <complexType>
         <attribute name="path" type="string" use="required">
            <annotation>
               <documentation>
                  Path of the folder to look for, relative to the contextual container.
               </documentation>
            </annotation>
         </attribute>
      </complexType>
   </element>

'''
    return text.replace(declaration, folder + declaration).encode("utf-8")


def prepare(source, destination, interventions):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if destination.exists():
        raise ValueError(f"Destination already exists: {destination}")
    manifest_data = (source / "corpus-manifest.json").read_bytes()
    manifest = json.loads(manifest_data)
    for row in manifest["schemas"] + manifest["descriptors"]:
        if digest((source / row["projectRelativePath"]).read_bytes()) != row["sha256"]:
            raise ValueError(f"Original input changed: {row['projectRelativePath']}")
    shutil.copytree(source, destination)
    patches = destination / "repairs"
    patches.mkdir()
    changes = []
    for name in interventions:
        relative, upstream_path = TARGETS[name]
        path = destination / "projects" / relative
        before = path.read_bytes()
        after = repair(name, before)
        path.write_bytes(after)
        patch = "".join(difflib.unified_diff(before.decode().splitlines(keepends=True),
            after.decode().splitlines(keepends=True), fromfile="a/" + upstream_path, tofile="b/" + upstream_path))
        (patches / (name + ".patch")).write_text(patch)
        changes.append({"intervention": name, "projectRelativePath": "projects/" + relative,
                        "upstreamPath": upstream_path, "beforeSha256": digest(before),
                        "afterSha256": digest(after), "beforeBytes": len(before), "afterBytes": len(after)})
    changed = {item["projectRelativePath"]: item for item in changes}
    for row in manifest["schemas"]:
        row["file"] = str(destination / row["projectRelativePath"])
        if row["projectRelativePath"] in changed:
            change = changed[row["projectRelativePath"]]
            row["originalSha256"] = row["sha256"]
            row["sha256"] = change["afterSha256"]
            row["bytes"] = change["afterBytes"]
            row["repair"] = change["intervention"]
    for row in manifest["declarations"] + manifest["contributions"]:
        key = row.get("schemaProjectRelativePath")
        if key in changed:
            row["schemaSha256"] = changed[key]["afterSha256"]
    for project in manifest["projects"]:
        project["directory"] = str(destination / project["projectRelativePath"])
    for descriptor in manifest["descriptors"]:
        if "file" in descriptor:
            descriptor["file"] = str(destination / descriptor["projectRelativePath"])
    manifest["outputDirectory"] = str(destination)
    manifest["summary"]["schemaBytes"] = sum(row["bytes"] for row in manifest["schemas"])
    identity = [{key: row[key] for key in ("bundleId", "bundleVersion", "relativePath", "sha256")}
                for row in manifest["schemas"]]
    manifest["schemaCorpusSha256"] = digest(json.dumps(identity, sort_keys=True, separators=(",", ":")).encode())
    manifest["repairExperiment"] = {"originalInventorySha256": digest(manifest_data),
                                    "originalSchemaCorpusSha256": json.loads(manifest_data)["schemaCorpusSha256"],
                                    "descriptorBytesUnchanged": True, "changes": changes}
    (destination / "corpus-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (destination / "project-list.txt").write_text("".join(
        str(destination / row["projectRelativePath"]) + "\n" for row in manifest["projects"]))
    for row in manifest["descriptors"]:
        if digest((destination / row["projectRelativePath"]).read_bytes()) != row["sha256"]:
            raise ValueError(f"Repair changed an XML instance: {row['projectRelativePath']}")
    return manifest["repairExperiment"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("corpus", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--only", choices=list(TARGETS), action="append")
    args = parser.parse_args()
    print(json.dumps(prepare(args.corpus, args.destination, args.only or list(TARGETS)), indent=2))
