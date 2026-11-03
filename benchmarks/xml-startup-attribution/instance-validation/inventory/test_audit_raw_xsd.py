"""The raw-XSD audit must distinguish syntax, dialect and resolver failures."""

import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


SPEC = importlib.util.spec_from_file_location("audit_raw_xsd", Path(__file__).with_name("audit_raw_xsd.py"))
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)


def corpus(root, files):
    schemas = []
    for name, content in files.items():
        path = root / "projects/org.example/schema" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        schemas.append({"bundleId": "org.example", "bundleVersion": "1.0.0", "relativePath": "schema/" + name,
                        "file": str(path), "projectRelativePath": path.relative_to(root).as_posix(),
                        "sha256": hashlib.sha256(content).hexdigest()})
    path = root / "corpus-manifest.json"
    path.write_text(json.dumps({"schemas": schemas, "schemaCorpusSha256": "fixture"}), encoding="utf-8")
    return path


class RawXsdTest(unittest.TestCase):
    def test_well_formed_legacy_appinfo_is_not_standard_xsd(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            original = b'<schema xmlns="http://www.w3.org/2001/XMLSchema"><annotation><appInfo/></annotation></schema>'
            manifest = corpus(root, {"legacy.exsd": original,
                                     "valid.exsd": b'<schema xmlns="http://www.w3.org/2001/XMLSchema"/>'})
            result = AUDIT.audit(manifest)
            self.assertEqual(result.get("summary", {}).get("xsdCompilePassed"), 1)
            self.assertEqual(result["summary"]["xsdCompileFailed"], 1)
            legacy = next(item for item in result["files"] if item["relativePath"] == "schema/legacy.exsd")
            self.assertTrue(legacy["xmlWellFormed"])
            self.assertTrue(any(item["type"] == "SCHEMAP_S4S_ELEM_NOT_ALLOWED" for item in legacy["diagnostics"]))
            self.assertEqual((root / "projects/org.example/schema/legacy.exsd").read_bytes(), original)

    def test_schema_protocol_resolves_only_to_original_local_corpus_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            manifest = corpus(root, {
                "main.exsd": b'<schema xmlns="http://www.w3.org/2001/XMLSchema" targetNamespace="urn:example">'
                    b'<include schemaLocation="schema://org.example/schema/shared.exsd"/></schema>',
                "shared.exsd": b'<schema xmlns="http://www.w3.org/2001/XMLSchema" targetNamespace="urn:example">'
                    b'<element name="thing" type="string"/></schema>',
            })
            result = AUDIT.audit(manifest)
            self.assertEqual(result.get("summary", {}).get("xsdCompilePassed"), 2)
            self.assertEqual(result["summary"]["blockedOrMissingResources"], 0)
            main = next(item for item in result["files"] if item["relativePath"] == "schema/main.exsd")
            self.assertTrue(any(item["url"].startswith("schema://") and item["status"] == "resolved-local"
                                for item in main["resolution"]))

    def test_external_resource_is_blocked_and_reported_separately(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            manifest = corpus(root, {"external.exsd": b'<schema xmlns="http://www.w3.org/2001/XMLSchema">'
                b'<include schemaLocation="https://example.invalid/remote.xsd"/></schema>'})
            result = AUDIT.audit(manifest)
            self.assertEqual(result.get("summary", {}).get("blockedOrMissingResources"), 1)
            self.assertEqual(result["summary"]["xsdCompilePassed"], 0)
            self.assertTrue(any(item["status"] == "blocked-external" for item in result["files"][0]["resolution"]))


if __name__ == "__main__":
    unittest.main()
