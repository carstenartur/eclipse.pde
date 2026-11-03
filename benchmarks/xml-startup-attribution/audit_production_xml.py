#!/usr/bin/env python3
"""Audit a bounded subset of PDE's XML rules and one real documentation defect.

Run from any directory (Python 3, standard library only):
    python benchmarks/xml-startup-attribution/audit_production_xml.py \
        --output benchmarks/xml-startup-attribution/audit-results.json

Inputs are paths tracked in the pinned baseline, read from the worktree. Tests
and templates are excluded from production findings; all baseline EXSD files
are still inventoried and parsed. The experiment's own XML is not production.
This is NOT a complete PDE validator, a W3C XSD validator, or a startup benchmark.
The before-example is read from the real baseline commit, never synthesized.
Exit 0 means the checked production rules and the specific example fix pass.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import xml.etree.ElementTree as ET


BASELINE = "ba6a5d6f2f455ab7dfe972ce678d07d9f80de267"
EXAMPLE_PATH = "ui/org.eclipse.pde.ui/schema/targetLocationProvisioners.exsd"
MISSING_CLOSE = b'name=&quot;%targetLocationProvider.example.name&quot;'
FIXED_CLOSE = MISSING_CLOSE + b"&gt;"
CORE = "ui/org.eclipse.pde.core/src/org/eclipse/pde/internal/core/"


def git(root: Path, *args: str) -> bytes:
    return subprocess.check_output(["git", "-C", str(root), *args])


def role(path: str) -> str:
    parts = PurePosixPath(path).parts
    if any(part.endswith(".tests") or part == "tests" for part in parts):
        return "test_fixture_or_bundle"
    if "testdata" in parts:
        return "testdata_fixture"
    if any(part == "templates" or part.startswith("templates_") for part in parts):
        return "source_template"
    return "production"


def parse_xml(content: bytes) -> tuple[ET.Element | None, dict]:
    try:
        element = ET.fromstring(content)
    except ET.ParseError as error:
        return None, {
            "well_formed": False,
            "error": str(error),
            "line_1_based": error.position[0],
            "column_0_based": error.position[1],
        }
    # Repository EXSD uses either no namespace or a default XSD namespace.
    # This normalization does not turn EXSD into W3C XML Schema validation.
    for node in element.iter():
        node.tag = node.tag.rsplit("}", 1)[-1]
    return element, {"well_formed": True}


def add_finding(findings: list, path: str, rule: str, detail: str) -> None:
    findings.append({"path": path, "role": role(path), "rule": rule, "detail": detail})


def audit_exsd(path: str, root: ET.Element, findings: list) -> dict:
    declarations = root.findall("element")
    names = [node.get("name") for node in declarations]
    for name, count in Counter(names).items():
        if not name:
            add_finding(findings, path, "element_name", "Top-level element has no nonempty name.")
        elif count > 1:
            add_finding(findings, path, "duplicate_element", f"Element {name!r} is declared {count} times.")
    for node in root.iter("attribute"):
        name = node.get("name")
        if not name:
            add_finding(findings, path, "attribute_name", "Attribute has no nonempty name.")
        if node.get("use") == "default" and "value" not in node.attrib:
            add_finding(findings, path, "default_without_value", f"Attribute {name!r} needs a value attribute.")
        if "use" not in node.attrib and "value" in node.attrib:
            add_finding(findings, path, "value_without_use", f"Attribute {name!r} has value but no use attribute.")
    for node in root.iter():
        for key in ("minOccurs", "maxOccurs"):
            value = node.get(key)
            if not value or (key == "maxOccurs" and value == "unbounded"):
                continue
            valid = re.fullmatch(r"[+-]?[0-9]+", value) is not None
            if valid:
                valid = -(2**31) <= int(value) < 2**31
            if not valid:
                add_finding(findings, path, "occurrence_integer", f"{key}={value!r} is not a Java int.")
    # These two Schema.java documentation readers dereference firstChild in
    # non-abbreviated mode. Attribute documentation has its own null guard.
    for owner in [root, *declarations]:
        for doc in owner.findall("./annotation/documentation"):
            if doc.text is None and len(doc) == 0:
                add_finding(findings, path, "empty_documentation", "Schema/element documentation has no text child.")
    references = {node.get("ref") for node in root.iter("element") if node.get("ref")}
    nonlocal_references = sorted(references - set(names))
    includes = [node.get("schemaLocation") for node in root.findall("include")]
    if nonlocal_references and not includes:
        add_finding(findings, path, "undefined_local_reference", repr(nonlocal_references))
    return {
        "declarations": len(declarations),
        "includes": includes,
        "nonlocal_references": nonlocal_references,
        "external_resolution": "not_attempted" if includes else "not_needed",
    }


def schema_catalog(schemas: dict) -> dict:
    catalog = {}
    for path, schema in schemas.items():
        if role(path) != "production":
            continue
        meta = schema.find("./annotation/appInfo/meta.schema")
        if meta is None:
            meta = schema.find("./annotation/appinfo/meta.schema")
        if meta is None or not meta.get("plugin") or not meta.get("id"):
            continue
        point = meta.get("id")
        plugin = meta.get("plugin")
        if not point.startswith(plugin + "."):
            point = plugin + "." + point
        catalog[point] = (path, schema)
    return catalog


def attributes_and_children(definition: ET.Element) -> tuple[dict, set, set]:
    attributes = {node.get("name"): node for node in definition.findall("./complexType/attribute")}
    java_attributes = {
        name for name, node in attributes.items()
        if any(meta.get("kind") == "java" for meta in node.iter("meta.attribute"))
    }
    children = {node.get("ref") for node in definition.findall("./complexType//element") if node.get("ref")}
    return attributes, children | java_attributes, java_attributes


def audit_extension(path: str, extension: ET.Element, schema: ET.Element, findings: list) -> None:
    definitions = {node.get("name"): node for node in schema.findall("element")}
    point = extension.get("point")

    def visit(node: ET.Element, parent_definition: ET.Element | None) -> None:
        context = f"{point}: <{node.tag}>"
        if node.tag == "extension" and node is not extension:
            add_finding(findings, path, "nested_extension", context)
            return
        definition = definitions.get(node.tag)
        if parent_definition is not None:
            _, allowed, java_attributes = attributes_and_children(parent_definition)
            if node.tag not in allowed:
                add_finding(findings, path, "illegal_child", context)
                return
            if definition is None and node.tag in java_attributes:
                return  # PDE's executable-extension syntax; Java checking is out of scope.
        if definition is None:
            add_finding(findings, path, "undefined_extension_element", context)
            return
        attributes, allowed, java_attributes = attributes_and_children(definition)
        for name, attribute in attributes.items():
            # PDE tests attribute presence, not whether its value is nonempty.
            present = name in node.attrib
            if name in java_attributes:
                present = present or any(child.tag == name for child in node)
            if attribute.get("use") == "required" and not present:
                add_finding(findings, path, "missing_required_attribute", f"{context} requires {name!r}.")
        for name in node.attrib:
            if name not in attributes and name not in allowed:
                add_finding(findings, path, "unknown_attribute", f"{context} has {name!r}.")
        for child in node:
            visit(child, definition)

    visit(extension, None)


def extract_example(root: ET.Element) -> bytes:
    for annotation in root.findall("annotation"):
        if any(meta.get("type") == "examples" for meta in annotation.iter("meta.section")):
            doc = annotation.find("documentation")
            if doc is None:
                raise ValueError("Examples section has no documentation.")
            text = "".join(doc.itertext())
            start = text.index("<extension")
            end = text.index("</extension>", start) + len("</extension>")
            return text[start:end].encode("utf-8")
    raise ValueError("No examples section found.")


def example_reproducer(root: Path, baseline: str, current: bytes) -> dict:
    original = git(root, "show", f"{baseline}:{EXAMPLE_PATH}")
    result = {
        "path": EXAMPLE_PATH,
        "baseline_commit": baseline,
        "classification": "Malformed XML in escaped documentation, not malformed EXSD XML.",
        "correction": "Append &gt; after name=&quot;%targetLocationProvider.example.name&quot;.",
        "only_expected_file_change": original.count(MISSING_CLOSE) == 1
        and current == original.replace(MISSING_CLOSE, FIXED_CLOSE, 1),
        "startup_effect": {
            "demonstrated": False,
            "measured": False,
            "explanation": "The defect is escaped text. Both containing EXSD documents parse; "
            "this fix does not repair a schema parse failure or demonstrate fewer Schema.load calls. "
            "This audit runs no Eclipse startup or PDE marker benchmark.",
        },
    }
    for label, content in (("before", original), ("after", current)):
        document, status = parse_xml(content)
        evidence = {"containing_exsd": status}
        if document is not None:
            try:
                example = extract_example(document)
                _, example_status = parse_xml(example)
                evidence["extracted_example"] = example_status
                evidence["example_sha256"] = hashlib.sha256(example).hexdigest()
            except ValueError as error:
                evidence["extraction_error"] = str(error)
        result[label] = evidence
    result["verified_fix"] = (
        result["only_expected_file_change"]
        and result["before"]["containing_exsd"]["well_formed"]
        and result["after"]["containing_exsd"]["well_formed"]
        and result["before"].get("extracted_example", {}).get("well_formed") is False
        and result["after"].get("extracted_example", {}).get("well_formed") is True
    )
    return result


def audit(root: Path, baseline_ref: str) -> dict:
    baseline = git(root, "rev-parse", baseline_ref + "^{commit}").decode().strip()
    tracked = sorted(git(root, "ls-tree", "-r", "--name-only", "-z", baseline).decode().strip("\0").split("\0"))
    exsd_files = [path for path in tracked if path.endswith(".exsd")]
    xml_files = [path for path in tracked if path.endswith(".xml")]
    production_xml = [path for path in xml_files if role(path) == "production"]
    excluded_xml = [{"path": path, "reason": role(path)} for path in xml_files if role(path) != "production"]
    findings, inventory, schemas, xml_roots = [], [], {}, {}
    for path in sorted(exsd_files + production_xml):
        content = (root / path).read_bytes()
        document, status = parse_xml(content)
        entry = {"path": path, "role": role(path), "sha256": hashlib.sha256(content).hexdigest(), **status}
        if document is None:
            add_finding(findings, path, "xml_well_formedness", status["error"])
        elif path.endswith(".exsd"):
            schemas[path] = document
            entry["schema_rule_subset"] = audit_exsd(path, document, findings)
        else:
            xml_roots[path] = document
        inventory.append(entry)
    catalog = schema_catalog(schemas)
    schema_paths_checked = extensions_checked = 0
    skipped_points = Counter()
    for path, plugin in xml_roots.items():
        if PurePosixPath(path).name != "plugin.xml":
            continue
        for point in plugin.findall("extension-point"):
            location = point.get("schema")
            if location:
                schema_paths_checked += 1
                if not (root / path).parent.joinpath(location).is_file():
                    add_finding(findings, path, "missing_schema_file", location)
        for extension in plugin.findall("extension"):
            point = extension.get("point")
            selected = catalog.get(point)
            if selected is None or selected[1].find("include") is not None:
                skipped_points[point or "<missing point>"] += 1
                continue
            extensions_checked += 1
            audit_extension(path, extension, selected[1], findings)
    example = example_reproducer(root, baseline, (root / EXAMPLE_PATH).read_bytes())
    production_findings = [finding for finding in findings if finding["role"] == "production"]
    return {
        "report_version": 1,
        "method": {
            "complete_pde_validator": False,
            "pde_runtime_executed": False,
            "w3c_xsd_validation": False,
            "parser": "Python standard-library xml.etree.ElementTree",
            "rule_sources": {
                CORE + "builders/SchemaErrorReporter.java": [
                    "validate: duplicate element names", "validateUse: default/value pairs",
                    "validateElementReference: locally defined references",
                ],
                CORE + "schema/Schema.java": [
                    "getAttribute/processElementDeclaration/processAttribute: nonempty names",
                    "getMinOccurs/getMaxOccurs: Java integer parsing",
                    "processSchemaAnnotation/processElementAnnotation: documentation firstChild",
                ],
                CORE + "builders/ExtensionsErrorReporter.java": [
                    "validateElement/computeAllowedElements: child names and Java-attribute child syntax",
                    "validateRequiredExtensionAttributes: required attribute presence",
                    "validateExistingExtensionAttributes: known attribute names",
                ],
            },
            "limitations": [
                "EXSD is PDE's custom grammar; appInfo/appinfo, use=default, and default/no namespace are preserved.",
                "No target-platform lookup, schema:// resolution, XML Schema type checking, or arbitrary documentation markup validation.",
                "No extension cardinality, Java class, resource, identifier, localization, deprecation, or preference-severity checks.",
                "Extension checks cover plugin.xml contributions to local production schemas without includes only.",
                "Static parse results are not proof of Schema.isLoaded state, marker behavior, or startup performance.",
            ],
        },
        "repository": {
            "head_commit": git(root, "rev-parse", "HEAD").decode().strip(),
            "baseline_commit": baseline,
            "input_selection": "Paths tracked in the pinned baseline, read from the current worktree; experiment and generated files excluded.",
        },
        "scope": {
            "tracked_exsd": len(exsd_files),
            "production_exsd": sum(role(path) == "production" for path in exsd_files),
            "tracked_xml": len(xml_files),
            "non_fixture_xml_checked": len(production_xml),
            "excluded_xml_count": len(excluded_xml),
            "excluded_xml_counts_by_reason": dict(sorted(Counter(item["reason"] for item in excluded_xml).items())),
            "exclusion_rules": [
                "Any path component equal to tests or ending in .tests: test fixture/bundle.",
                "Any path component equal to testdata: testdata fixture.",
                "Any path component equal to templates or starting with templates_: source template.",
                "Excluded XML is not parsed. Nonproduction EXSD is parsed/inventoried, but cannot produce production findings.",
            ],
            "excluded_xml": excluded_xml,
        },
        "checked_files": inventory,
        "extension_checks": {
            "extension_point_schema_paths_checked": schema_paths_checked,
            "production_schemas_in_local_catalog": len(catalog),
            "extensions_checked": extensions_checked,
            "extensions_skipped_without_supported_local_schema": dict(sorted(skipped_points.items())),
        },
        "rule_findings": findings,
        "documentation_example": example,
        "summary": {
            "production_rule_findings": len(production_findings),
            "nonproduction_observations": len(findings) - len(production_findings),
            "example_fix_verified": example["verified_fix"],
            "result": "pass" if not production_findings and example["verified_fix"] else "fail",
            "startup_effect_demonstrated": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--baseline", default=BASELINE, help="Real Git revision for the unfixed documentation example.")
    parser.add_argument("--output", type=Path, help="Write JSON here (relative paths are relative to --root); otherwise print JSON.")
    args = parser.parse_args()
    root = args.root.resolve()
    try:
        report = audit(root, args.baseline)
    except (OSError, subprocess.CalledProcessError, ValueError) as error:
        print(f"Audit could not finish: {error}", file=sys.stderr)
        return 2
    serialized = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        output = args.output if args.output.is_absolute() else root / args.output
        output.write_text(serialized, encoding="utf-8")
        print(json.dumps({"scope": {key: report["scope"][key] for key in ("tracked_exsd", "non_fixture_xml_checked")}, **report["summary"]}))
    else:
        print(serialized, end="")
    return 0 if report["summary"]["result"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
