#!/usr/bin/env python3
"""Compile unchanged EXSD documents as W3C XSD 1.0, without validating instances.

A failure here is not automatically a PDE error. PDE has supported legacy
syntax outside the standard XSD grammar. The resolver permits only original
schema files in the supplied corpus; schema:// URLs are mapped to those local
files. Missing resources and blocked external access are recorded separately.
"""

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import posixpath
from urllib.parse import unquote, urlparse

from lxml import etree


XSD = "http://www.w3.org/2001/XMLSchema"


class CorpusResolver(etree.Resolver):
    def __init__(self, schemas):
        self.paths = {Path(item["file"]).resolve() for item in schemas}
        self.by_schema_url = {(item["bundleId"], item["relativePath"]): Path(item["file"]).resolve() for item in schemas}
        self.events = []

    def resolve(self, url, public_id, context):
        parsed = urlparse(url)
        path = None
        if parsed.scheme == "schema":
            key = (parsed.netloc, posixpath.normpath(unquote(parsed.path).lstrip("/")))
            path = self.by_schema_url.get(key)
            if path is None:
                self.events.append({"url": url, "status": "missing-corpus-resource"})
                raise OSError(f"Schema URL is absent from the original corpus: {url}")
        elif parsed.scheme in ("", "file") and parsed.netloc in ("", "localhost"):
            candidate = Path(unquote(parsed.path)).resolve()
            if candidate in self.paths:
                path = candidate
            else:
                self.events.append({"url": url, "status": "blocked-outside-corpus"})
                raise OSError(f"Local schema path is outside the original corpus: {url}")
        else:
            self.events.append({"url": url, "status": "blocked-external"})
            raise OSError(f"External schema retrieval is disabled: {url}")
        self.events.append({"url": url, "status": "resolved-local", "path": str(path)})
        return self.resolve_filename(str(path), context)


def diagnostics(error):
    log = getattr(error, "error_log", [])
    return [{"domain": item.domain_name, "type": item.type_name, "level": item.level_name,
             "line": item.line, "column": item.column, "file": item.filename,
             "message": item.message} for item in log] or [
                 {"domain": "RESOURCE", "type": type(error).__name__, "level": "ERROR", "message": str(error)}]


def audit(manifest_path):
    manifest_path = Path(manifest_path).resolve()
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    schemas = manifest["schemas"]
    for item in schemas:
        if hashlib.sha256(Path(item["file"]).read_bytes()).hexdigest() != item["sha256"]:
            raise ValueError(f"Input no longer matches the original corpus hash: {item['file']}")
    result = {"formatVersion": 1, "corpusManifest": str(manifest_path),
              "corpusManifestSha256": hashlib.sha256(manifest_bytes).hexdigest(),
              "schemaCorpusSha256": manifest["schemaCorpusSha256"],
              "toolVersions": {"lxml": list(etree.LXML_VERSION), "libxml2": list(etree.LIBXML_VERSION)},
              "policy": {"operation": "W3C XSD 1.0 compilation of unchanged schema documents",
                         "instancesValidated": 0, "schemaNormalization": "none",
                         "resolver": "Only original corpus files; schema:// resolves locally; other network URLs blocked",
                         "interpretation": "Standard-XSD incompatibility is not a PDE load failure or a proven configuration error"},
              "files": []}
    for item in schemas:
        record = {key: item[key] for key in ("bundleId", "bundleVersion", "relativePath", "file", "sha256")}
        record.update(xmlWellFormed=False, xsdCompilePassed=False, diagnostics=[])
        resolver = CorpusResolver(schemas)
        parser = etree.XMLParser(no_network=True, resolve_entities=False)
        parser.resolvers.add(resolver)
        try:
            document = etree.parse(item["file"], parser)
            root = document.getroot()
            record.update(xmlWellFormed=True, root=root.tag,
                          legacyAppInfoElements=len(root.xpath('.//*[local-name()="appInfo"]')),
                          defaultUseAttributes=len(root.xpath('.//*[local-name()="attribute"][@use="default"]')),
                          xsdRootNamespace=etree.QName(root).namespace == XSD)
            etree.XMLSchema(document)
            record["xsdCompilePassed"] = True
        except (etree.XMLSyntaxError, etree.XMLSchemaParseError, OSError) as error:
            record["diagnostics"] = diagnostics(error)
        record["resolution"] = resolver.events
        record["blockedOrMissingResources"] = sum(event["status"] != "resolved-local" for event in resolver.events)
        result["files"].append(record)
    types = Counter(diagnostic["type"] for item in result["files"] for diagnostic in item["diagnostics"])
    result["summary"] = {
        "schemaFiles": len(schemas),
        "xmlWellFormed": sum(item["xmlWellFormed"] for item in result["files"]),
        "xsdCompilePassed": sum(item["xsdCompilePassed"] for item in result["files"]),
        "xsdCompileFailed": sum(not item["xsdCompilePassed"] for item in result["files"]),
        "blockedOrMissingResources": sum(item["blockedOrMissingResources"] for item in result["files"]),
        "filesWithBlockedOrMissingResources": sum(item["blockedOrMissingResources"] > 0 for item in result["files"]),
        "filesWithLegacyAppInfo": sum(item.get("legacyAppInfoElements", 0) > 0 for item in result["files"]),
        "filesWithDefaultUse": sum(item.get("defaultUseAttributes", 0) > 0 for item in result["files"]),
        "filesWithoutXsdRootNamespace": sum(not item.get("xsdRootNamespace", False) for item in result["files"]),
        "diagnosticTypes": dict(sorted(types.items())),
    }
    for item in schemas:
        if hashlib.sha256(Path(item["file"]).read_bytes()).hexdigest() != item["sha256"]:
            raise ValueError(f"Raw schema bytes changed during the audit: {item['file']}")
    result["originalSchemaHashesVerifiedBeforeAndAfter"] = True
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus-manifest", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = audit(args.corpus_manifest)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), **result["summary"]}))


if __name__ == "__main__":
    main()
