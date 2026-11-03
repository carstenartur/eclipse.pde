"""Synthetic archive fixtures test copying/filtering, never startup performance."""

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile


SPEC = importlib.util.spec_from_file_location("prepare_schema_corpus", Path(__file__).resolve().parents[1] / "prepare_schema_corpus.py")
CORPUS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CORPUS)


def bundle(path, symbolic_name, version, files, source=None):
    manifest = f"Manifest-Version: 1.0\nBundle-SymbolicName: {symbolic_name}\nBundle-Version: {version}\n"
    if source:
        manifest += f'Eclipse-SourceBundle: {source};version="{version}";roots:="."\n'
    manifest += "\n"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("META-INF/MANIFEST.MF", manifest.encode())
        for name, content in files.items():
            archive.writestr(name, content)


class CorpusTest(unittest.TestCase):
    def test_real_archive_bytes_and_missing_references_are_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory) / "eclipse"
            plugins = home / "plugins"
            plugins.mkdir(parents=True)
            binary_schema = b'<schema><include schemaLocation="common.mxsd"/><element name="binary"/></schema>'
            plugin_xml = b'<plugin><extension-point id="ok" schema="schema/declared.exsd"/><extension-point id="missing" schema="schema/missing.exsd"/></plugin>'
            bundle(plugins / "provider.jar", "org.example.provider", "1.2.3.test", {
                "plugin.xml": plugin_xml, "plugin.properties": b"label=Original\n",
                "schema/declared.exsd": binary_schema,
            })
            bundle(plugins / "source.jar", "org.example.provider.source", "1.2.3.test", {
                "schema/declared.exsd": b"<schema>source must lose</schema>",
                "schema/common.mxsd": b"<schema/>", "schema/unused.exsd": b"<schema/>",
                "schema/broken.exsd": b"<schema>",
                "templates/example/schema/invalid.exsd": b"<malformed",
                "plugin.xml": b"<plugin>not the binary descriptor</plugin>",
            }, source="org.example.provider")
            bundle(plugins / "wrong-source.jar", "org.example.provider.source", "1.2.4.test", {
                "schema/wrong.exsd": b"<schema/>",
            }, source="org.example.provider")
            output = Path(directory) / "corpus"
            report = CORPUS.prepare_corpus(home, output)
            self.assertEqual(report.get("summary", {}).get("schemaFiles"), 4)
            self.assertEqual(report["summary"]["xmlSyntaxErrors"], 1)
            self.assertEqual(report["summary"]["missingDeclaredSchemas"], 1)
            self.assertEqual(report["summary"]["missingIncludes"], 0)
            project = output / "projects/org.example.provider"
            self.assertEqual((project / "schema/declared.exsd").read_bytes(), binary_schema)
            self.assertEqual((project / "plugin.xml").read_bytes(), plugin_xml)
            self.assertEqual((project / "schema/broken.exsd").read_bytes(), b"<schema>")
            self.assertFalse((project / "schema/wrong.exsd").exists())
            self.assertFalse((project / "templates").exists())
            self.assertEqual(ET.parse(project / ".project").findtext("name"), "org.example.provider")
            self.assertEqual([node.text for node in ET.parse(project / ".project").findall("buildSpec/buildCommand/name")],
                             ["org.eclipse.pde.SchemaBuilder"])
            self.assertEqual([node.attrib for node in ET.parse(project / ".classpath").findall("classpathentry")],
                             [{"kind": "output", "path": "bin"}])
            self.assertIn("compilers.s.create-docs=false", (project / ".settings/org.eclipse.pde.prefs").read_text())
            self.assertEqual((output / "project-list.txt").read_text().splitlines(), [str(project)])
            self.assertEqual(json.loads((output / "corpus-manifest.json").read_text())["summary"], report["summary"])
            self.assertTrue(any(item["path"] == "templates/example/schema/invalid.exsd" for item in report["filteredSchemaFiles"]))


if __name__ == "__main__":
    unittest.main()
