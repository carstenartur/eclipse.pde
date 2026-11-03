#!/usr/bin/env python3
"""Classify projected-grammar diagnostics and run one labeled input sensitivity.

The baseline retains the original XML. The sensitivity validates an in-memory
copy after deleting only XML whitespace diagnosed under XSD-empty elements.
It changes neither source files nor schema constraints, defaults or enumerations.
"""

import argparse
from collections import Counter, defaultdict
from copy import deepcopy
import json
from pathlib import Path
import re

from lxml import etree

from project_grammar import audit, build_projection, digest


def locate(instance, path):
    prefix = "/" + instance.tag
    if path is None or not (path == prefix or path.startswith(prefix + "/")):
        return None
    nodes = instance.xpath("." + path[len(prefix):])
    return nodes[0] if len(nodes) == 1 and isinstance(nodes[0], etree._Element) else None


def analyze_contribution(projection, instance):
    original = etree.tostring(instance)
    baseline = projection.check(instance)
    classified, whitespace_paths = [], set()
    for diagnostic in baseline.get("diagnostics", []):
        entry = dict(diagnostic)
        node = locate(instance, entry.get("path"))
        category = "other_grammar"
        if node is None:
            category = "unclassified_location"
        elif entry["type"] == "SCHEMAV_CVC_COMPLEX_TYPE_2_1":
            own_text = (node.text or "") + "".join(child.tail or "" for child in node)
            category = "empty_content_xml_whitespace" if own_text and not own_text.strip(" \t\r\n") else "empty_content_other_text"
            if category == "empty_content_xml_whitespace":
                whitespace_paths.add(entry["path"])
                entry["textRepr"] = repr(own_text)
                entry["snippet"] = etree.tostring(node, encoding="unicode", with_tail=False)[:600]
        elif entry["type"] == "SCHEMAV_CVC_ENUMERATION_VALID":
            attribute = re.search(r"attribute '([^']+)'", entry["message"])
            key = (node.tag, attribute.group(1)) if attribute else None
            category = "identifier_enumeration" if key in projection.identifier_attributes else "closed_enumeration"
        entry["category"] = category
        classified.append(entry)
    copy = deepcopy(instance)
    removed = 0
    for path in sorted(whitespace_paths):
        node = locate(copy, path)
        removed += len(node.text or "") + sum(len(child.tail or "") for child in node)
        node.text = None
        for child in node:
            child.tail = None
    sensitivity = projection.check(copy)
    if etree.tostring(instance) != original:
        raise AssertionError("Classification mutated the original instance")
    return {"baselineStatus": baseline["status"], "diagnostics": classified,
            "onlyEmptyContentWhitespace": bool(classified) and all(
                x["category"] == "empty_content_xml_whitespace" for x in classified),
            "removedWhitespaceNodes": len(whitespace_paths), "removedWhitespaceCharacters": removed,
            "sensitivity": sensitivity}


def analyze(corpus_directory):
    corpus = Path(corpus_directory).resolve()
    baseline = audit(corpus)
    manifest = json.loads((corpus / "corpus-manifest.json").read_text())
    roots = {p["bundleId"]: corpus / p["projectRelativePath"] for p in manifest["projects"]}
    expected = {(corpus / x["projectRelativePath"]).resolve(): x["sha256"] for x in manifest["schemas"]}
    descriptors = {(x["bundleId"], x["descriptor"]): x for x in manifest["descriptors"]}
    trees, projections, records, examples = {}, {}, [], []
    categories, per_file = Counter(), defaultdict(Counter)
    sensitivity_statuses = Counter(baseline["summary"]["statuses"])
    for item in baseline["contributions"]:
        if item["status"] != "invalid":
            continue
        key = item["bundleId"], item["descriptor"]
        if key not in trees:
            descriptor = descriptors[key]
            data = (corpus / descriptor["projectRelativePath"]).read_bytes()
            if digest(data) != descriptor["sha256"]:
                raise ValueError("Descriptor changed since inventory")
            trees[key] = etree.fromstring(data, etree.XMLParser(no_network=True, resolve_entities=False)).getroottree()
        schema = item["schemaProjectRelativePath"]
        if schema not in projections:
            projections[schema] = build_projection(corpus / schema, roots, expected)
        instance = trees[key].xpath(item["xmlPath"])[0]
        details = analyze_contribution(projections[schema], instance)
        counts = Counter(d["category"] for d in details["diagnostics"])
        categories.update(counts)
        per_file[key].update(counts)
        for diagnostic in details["diagnostics"]:
            if "snippet" in diagnostic and len(examples) < 8:
                examples.append({"bundleId": key[0], "descriptor": key[1], "extensionPointId": item["extensionPointId"],
                                 **diagnostic})
        record = {k: item[k] for k in ("bundleId", "descriptor", "line", "xmlPath", "extensionPointId")}
        record.update(diagnosticCategories=dict(counts), onlyEmptyContentWhitespace=details["onlyEmptyContentWhitespace"],
                      removedWhitespaceNodes=details["removedWhitespaceNodes"],
                      removedWhitespaceCharacters=details["removedWhitespaceCharacters"], sensitivity=details["sensitivity"])
        records.append(record)
        sensitivity_statuses["invalid"] -= 1
        sensitivity_statuses[details["sensitivity"]["status"]] += 1
    only_whitespace_files = ["/".join(key) for key, count in per_file.items() if set(count) == {"empty_content_xml_whitespace"}]
    source_unchanged = all(digest(path.read_bytes()) == sha for path, sha in expected.items()) and all(
        digest((corpus / d["projectRelativePath"]).read_bytes()) == d["sha256"] for d in manifest["descriptors"])
    if not source_unchanged:
        raise ValueError("Inputs changed during classification")
    return {"policy": {"baseline": "Original XML against projected grammar, unchanged",
                       "sensitivity": "Transformed-input diagnostic: delete only XML whitespace directly diagnosed under XSD-empty elements from an in-memory copy",
                       "enumClassification": "identifier metadata explains native PDE's different checking path; enumeration restrictions remain in both projected validations",
                       "fileCountMeaning": "Files with reported diagnostics exclusively in this category, not a claim that unchecked contributions in those files are valid",
                       "sourceMutation": False},
            "inventorySha256": baseline["inventorySha256"], "versions": baseline["versions"],
            "baselineSummary": baseline["summary"], "sourceFilesUnchanged": source_unchanged,
            "summary": {"diagnosticsByCategory": dict(categories),
                        "contributionsWithOnlyEmptyContentWhitespace": sum(r["onlyEmptyContentWhitespace"] for r in records),
                        "filesWithOnlyEmptyContentWhitespaceDiagnostics": len(only_whitespace_files),
                        "sensitivityStatuses": dict(sensitivity_statuses),
                        "removedWhitespaceCharacters": sum(r["removedWhitespaceCharacters"] for r in records)},
            "onlyEmptyContentWhitespaceFiles": sorted(only_whitespace_files),
            "whitespaceExamples": examples, "classifiedContributions": records}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("corpus", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = analyze(args.corpus)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result["summary"], indent=2))
