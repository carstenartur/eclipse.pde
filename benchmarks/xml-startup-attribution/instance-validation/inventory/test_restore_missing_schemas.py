"""Restoring an authentic omitted resource must not silently rewrite inputs."""

import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

from test_prepare_instance_corpus import CORPUS, bundle, configure


SPEC = importlib.util.spec_from_file_location("restore_missing_schemas", Path(__file__).with_name("restore_missing_schemas.py"))
RESTORE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RESTORE)


class RestorationTest(unittest.TestCase):
    def fixture(self, root):
        home = root / "eclipse"
        provider = bundle(home, "org.example.provider", "1.0.0", {
            "plugin.xml": b'<plugin><extension-point id="p" schema="schema/p.exsd"/>'
                b'<extension-point id="other" schema="schema/other.exsd"/></plugin>'})
        consumer = bundle(home, "org.example.consumer", "1.0.0", {
            "plugin.xml": b'<plugin><extension point="org.example.provider.p"/>'
                b'<extension point="org.example.provider.other"/></plugin>'})
        configure(home, provider, consumer)
        original = root / "original"
        report = CORPUS.prepare_corpus(home, original)
        resource = root / "resources/org.example.provider/schema/p.exsd"
        resource.parent.mkdir(parents=True)
        content = b'<schema><element name="extension"/></schema>\n'
        resource.write_bytes(content)
        provenance = root / "resources/provenance.json"
        item = {"bundleId": "org.example.provider", "bundleVersion": "1.0.0", "relativePath": "schema/p.exsd",
                "resourceFile": "resources/org.example.provider/schema/p.exsd", "bytes": len(content),
                "sha256": hashlib.sha256(content).hexdigest(), "sourceCommit": "1" * 40,
                "sourcePath": "provider/schema/p.exsd", "sourceUrl": "https://example.invalid/pinned/schema/p.exsd",
                "binarySourceReference": ""}
        provenance.write_text(json.dumps({"resources": [item]}))
        return original, report, provenance, resource

    def test_restoration_updates_coverage_but_preserves_all_original_xml_bytes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            original, before, provenance, resource = self.fixture(root)
            original_manifest = (original / "corpus-manifest.json").read_bytes()
            after = RESTORE.restore(original, root / "restored", provenance)
            self.assertEqual(after.get("summary", {}).get("schemaFiles"), 1)
            self.assertEqual(after["summary"]["missingDeclaredSchemas"], 1)
            self.assertEqual(after["summary"]["contributionSchemaStatus"], {"present": 1, "missing-schema": 1})
            self.assertEqual(after["summary"]["restoredSchemaFiles"], 1)
            self.assertEqual((original / "corpus-manifest.json").read_bytes(), original_manifest)
            self.assertFalse((original / "projects/org.example.provider/schema/p.exsd").exists())
            self.assertEqual((root / "restored/projects/org.example.provider/schema/p.exsd").read_bytes(), resource.read_bytes())
            for descriptor in before["descriptors"]:
                self.assertEqual((original / descriptor["projectRelativePath"]).read_bytes(),
                                 (root / "restored" / descriptor["projectRelativePath"]).read_bytes())
            self.assertTrue(all(str(root / "restored") in line for line in (root / "restored/project-list.txt").read_text().splitlines()))

    def test_modified_vendored_resource_is_rejected_before_copy(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            original, _, provenance, resource = self.fixture(root)
            resource.write_bytes(b"<schema/>")
            with self.assertRaisesRegex(ValueError, "resource.*hash|Resource.*hash"):
                RESTORE.restore(original, root / "restored", provenance)
            self.assertFalse((root / "restored").exists())

    def test_different_binary_source_reference_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            original, _, provenance, _ = self.fixture(root)
            data = json.loads(provenance.read_text())
            data["resources"][0]["binarySourceReference"] = "scm:git:https://example.invalid/unrelated.git;commitId=" + "2" * 40
            provenance.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, "source reference|Source reference"):
                RESTORE.restore(original, root / "restored", provenance)


if __name__ == "__main__":
    unittest.main()
