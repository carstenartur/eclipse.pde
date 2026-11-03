#!/usr/bin/env python3
"""Supplemental, bounded EXSD structural-grammar projection, never a PDE replacement.

Uses a frozen instance inventory. All transformations are in memory; the actual
XSD processor checks a projected grammar, not the original EXSD dialect. A skipped
or unbuildable projection is explicitly unchecked, never reported as valid.
"""

import argparse
from collections import Counter
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit

from lxml import etree


XS = "http://www.w3.org/2001/XMLSchema"
POLICY = {
    "meaning": "XSD 1.0 validation against a bounded projected structural grammar; not XMLSpy equivalence",
    "adaptations": ["drop EXSD annotations", "drop targetNamespace for unqualified extension instances",
                    "qualify string/boolean/anyURI type and base names as xs names",
                    "translate use=default,value to use=optional,default",
                    "inline locally resolved includes; deduplicate identical declarations"],
    "preserved": ["element names", "attribute names", "sequence order", "choice/all",
                  "minOccurs/maxOccurs", "required attributes", "enumerations", "text content constraints"],
    "unchecked": ["unsupported constructs or namespaces", "missing or external includes",
                  "conflicting declarations", "XSD compilation failures",
                  "PDE executable-extension child alternatives"],
    "sourceMutation": False,
    "networkResolution": False,
}
ATTRS = {
    "element": {"name", "ref", "type", "minOccurs", "maxOccurs"},
    "complexType": {"mixed"}, "simpleType": set(),
    "sequence": {"minOccurs", "maxOccurs"}, "choice": {"minOccurs", "maxOccurs"},
    "all": {"minOccurs", "maxOccurs"},
    "attribute": {"name", "type", "use", "value", "default", "fixed"},
    "restriction": {"base"}, "enumeration": {"value"},
}


class ProjectionError(Exception):
    def __init__(self, code, detail, diagnostics=None):
        super().__init__(detail)
        self.code = code
        self.diagnostics = diagnostics or []


def digest(data):
    return hashlib.sha256(data).hexdigest()


def local(node):
    return etree.QName(node).localname


def diagnostics(log):
    return [{"line": e.line, "column": e.column, "path": e.path,
             "type": e.type_name, "message": e.message} for e in log]


def project_node(node):
    if not isinstance(node.tag, str):
        return None
    name = local(node)
    if name == "annotation" and etree.QName(node).namespace in (None, XS):
        return None
    if etree.QName(node).namespace not in (None, XS) or name not in ATTRS:
        raise ProjectionError("unsupported_construct", f"Unsupported schema element {node.tag}")
    extra = set(node.attrib) - ATTRS[name]
    if extra:
        raise ProjectionError("unsupported_construct", f"Unsupported {name} attributes: {sorted(extra)}")
    attrs = dict(node.attrib)
    for key in ("type", "base"):
        if key in attrs:
            value = attrs[key]
            prefix, _, short = value.rpartition(":")
            if short not in {"string", "boolean", "anyURI"} or (prefix and node.nsmap.get(prefix) != XS):
                raise ProjectionError("unsupported_type", f"Unsupported {key}={value}")
            attrs[key] = "xs:" + short
    if ":" in attrs.get("ref", ""):
        raise ProjectionError("unsupported_reference", f"Qualified element reference: {attrs['ref']}")
    if name == "attribute" and attrs.get("use") == "default":
        if "value" not in attrs or "default" in attrs or "fixed" in attrs:
            raise ProjectionError("unsupported_default", "Ambiguous or absent legacy default value")
        attrs["use"] = "optional"
        attrs["default"] = attrs.pop("value")
    elif name == "attribute" and "value" in attrs:
        raise ProjectionError("unsupported_default", "value without legacy use=default")
    projected = etree.Element("{" + XS + "}" + name, attrs)
    for child in node:
        copy = project_node(child)
        if copy is not None:
            projected.append(copy)
    return projected


@dataclass
class Projection:
    validator: object
    xsd: bytes
    inputs: dict
    java_children: set
    identifier_attributes: set

    def check(self, element):
        for node in element.iter():
            if not isinstance(node.tag, str):
                continue
            if etree.QName(node).namespace is not None or any("}" in name for name in node.attrib):
                return {"status": "unchecked", "reason": "namespaced_instance"}
            for child in node:
                if isinstance(child.tag, str) and (node.tag, child.tag) in self.java_children:
                    return {"status": "unchecked", "reason": "executable_extension_child",
                            "detail": f"{node.tag}/{child.tag}"}
        valid = self.validator.validate(element)
        return {"status": "valid" if valid else "invalid",
                "diagnostics": diagnostics(self.validator.error_log)}


def build_projection(schema_path, bundle_roots, expected_hashes=None):
    roots = {k: Path(v).resolve() for k, v in bundle_roots.items()}
    inputs, declarations, java_children, identifiers = {}, {}, set(), set()
    schema = etree.Element("{" + XS + "}schema", nsmap={"xs": XS})

    def visit(path):
        path = Path(path).resolve()
        if not any(path.is_relative_to(root) for root in roots.values()):
            raise ProjectionError("include_outside_corpus", str(path))
        if path in inputs:
            return
        if not path.is_file():
            raise ProjectionError("missing_schema", str(path))
        if expected_hashes is not None and path not in expected_hashes:
            raise ProjectionError("unlisted_schema", str(path))
        data = path.read_bytes()
        if expected_hashes is not None and digest(data) != expected_hashes[path]:
            raise ValueError(f"Schema changed since inventory: {path}")
        inputs[path] = digest(data)
        tree = etree.fromstring(data, etree.XMLParser(no_network=True, resolve_entities=False))
        if tree.getroottree().docinfo.doctype or local(tree) != "schema" or etree.QName(tree).namespace not in (None, XS):
            raise ProjectionError("unsupported_schema_root", str(path))
        if set(tree.attrib) - {"targetNamespace"}:
            raise ProjectionError("unsupported_schema_root", f"Root attributes in {path}: {dict(tree.attrib)}")
        for node in tree:
            if not isinstance(node.tag, str):
                continue
            if etree.QName(node).namespace not in (None, XS):
                raise ProjectionError("unsupported_construct", f"Unsupported schema element {node.tag}")
            if local(node) == "annotation":
                continue
            if local(node) == "include":
                if set(node.attrib) != {"schemaLocation"}:
                    raise ProjectionError("unsupported_include", str(path))
                location = node.get("schemaLocation")
                parsed = urlsplit(location)
                if parsed.query or parsed.fragment:
                    raise ProjectionError("unsupported_include", location)
                if parsed.scheme == "schema":
                    if parsed.netloc not in roots:
                        raise ProjectionError("missing_schema", location)
                    included = roots[parsed.netloc] / parsed.path.lstrip("/")
                elif not parsed.scheme and not parsed.netloc:
                    included = path.parent / location
                else:
                    raise ProjectionError("external_include", location)
                visit(included)
                continue
            if local(node) != "element" or not node.get("name"):
                raise ProjectionError("unsupported_declaration", f"{path}: {node.tag}")
            copy = project_node(node)
            key = node.get("name")
            fingerprint = etree.tostring(copy, method="c14n")
            if key in declarations and declarations[key] != fingerprint:
                raise ProjectionError("conflicting_declaration", f"{key} in {path}")
            if key not in declarations:
                declarations[key] = fingerprint
                schema.append(copy)
            for attr in node.xpath("./*[local-name()='complexType']/*[local-name()='attribute']"):
                if attr.xpath("./*[local-name()='annotation']/*/*[local-name()='meta.attribute' and @kind='java']"):
                    java_children.add((key, attr.get("name")))
                if attr.xpath("./*[local-name()='annotation']/*/*[local-name()='meta.attribute' and @kind='identifier']"):
                    identifiers.add((key, attr.get("name")))

    try:
        visit(schema_path)
        xsd = etree.tostring(schema)
        validator = etree.XMLSchema(etree.fromstring(xsd), attribute_defaults=False)
    except etree.XMLSchemaParseError as failure:
        raise ProjectionError("schema_compile_failed", str(failure), diagnostics(failure.error_log)) from failure
    except etree.XMLSyntaxError as failure:
        raise ProjectionError("schema_xml_syntax", str(failure), diagnostics(failure.error_log)) from failure
    return Projection(validator, xsd, inputs, java_children, identifiers)


def audit(corpus_directory):
    corpus = Path(corpus_directory).resolve()
    manifest_path = corpus / "corpus-manifest.json"
    manifest_data = manifest_path.read_bytes()
    inventory = json.loads(manifest_data)
    roots = {p["bundleId"]: corpus / p["projectRelativePath"] for p in inventory["projects"]}
    descriptors, schemas, results = {}, {}, []
    input_hashes = {manifest_path: digest(manifest_data)}
    expected_schemas = {(corpus / item["projectRelativePath"]).resolve(): item["sha256"] for item in inventory["schemas"]}
    for path, expected in expected_schemas.items():
        if digest(path.read_bytes()) != expected:
            raise ValueError(f"Schema changed since inventory: {path}")
    input_hashes.update(expected_schemas)
    for item in inventory["descriptors"]:
        path = corpus / item["projectRelativePath"]
        data = path.read_bytes()
        if digest(data) != item["sha256"]:
            raise ValueError(f"Descriptor changed since inventory: {path}")
        input_hashes[path] = digest(data)
        descriptors[item["bundleId"], item["descriptor"]] = etree.fromstring(
            data, etree.XMLParser(no_network=True, resolve_entities=False)).getroottree()
    for contribution in inventory["contributions"]:
        result = {k: contribution.get(k) for k in ("bundleId", "descriptor", "line", "xmlPath",
                  "extensionPointId", "schemaStatus", "schemaProjectRelativePath")}
        schema_key = contribution.get("schemaProjectRelativePath")
        if contribution["schemaStatus"] != "present":
            result.update(status="unchecked", reason=contribution["schemaStatus"])
        else:
            if schema_key not in schemas:
                path = corpus / schema_key
                if digest(path.read_bytes()) != contribution["schemaSha256"]:
                    raise ValueError(f"Schema changed since inventory: {path}")
                try:
                    schemas[schema_key] = build_projection(path, roots, expected_schemas)
                    input_hashes.update(schemas[schema_key].inputs)
                except ProjectionError as failure:
                    schemas[schema_key] = {"status": "unchecked", "reason": failure.code,
                                          "detail": str(failure), "diagnostics": failure.diagnostics}
            projection = schemas[schema_key]
            if isinstance(projection, dict):
                result.update(projection)
            else:
                nodes = descriptors[contribution["bundleId"], contribution["descriptor"]].xpath(contribution["xmlPath"])
                if len(nodes) != 1 or nodes[0].get("point") != contribution["extensionPointId"]:
                    raise ValueError(f"Contribution mapping changed: {result}")
                result.update(projection.check(nodes[0]))
        results.append(result)
    unchanged = all(digest(path.read_bytes()) == sha for path, sha in input_hashes.items())
    if not unchanged:
        raise ValueError("Inputs changed during projection audit")
    compiled = [{"schema": key, "xsdSha256": digest(p.xsd),
                 "inputs": [{"path": str(path.relative_to(corpus)), "sha256": sha} for path, sha in p.inputs.items()]}
                for key, p in schemas.items() if isinstance(p, Projection)]
    failures = [{"schema": key, **p} for key, p in schemas.items() if isinstance(p, dict)]
    return {"policy": POLICY, "versions": {"lxml": etree.LXML_VERSION, "libxml2": etree.LIBXML_VERSION},
            "inventorySha256": digest(manifest_data), "sourceFilesUnchanged": unchanged,
            "summary": {"contributions": len(results), "statuses": dict(Counter(r["status"] for r in results)),
                        "uncheckedReasons": dict(Counter(r.get("reason") for r in results if r["status"] == "unchecked")),
                        "compiledSchemas": len(compiled), "uncompiledSchemas": len(failures)},
            "compiledSchemas": compiled, "uncompiledSchemas": failures, "contributions": results}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("corpus", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.corpus)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result["summary"], indent=2))


if __name__ == "__main__":
    main()
