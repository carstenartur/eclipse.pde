"""Exercise configured-bundle scope and original bytes, not PDE validation."""

import importlib.util
from pathlib import Path
import tempfile
import unittest
import zipfile


SPEC = importlib.util.spec_from_file_location(
    "prepare_instance_corpus", Path(__file__).with_name("prepare_instance_corpus.py"))
CORPUS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CORPUS)


def bundle(home, name, version, files, source=None, directory=False):
    path = home / "plugins" / (name + ("" if directory else ".jar"))
    path.parent.mkdir(parents=True, exist_ok=True)
    manifest = f"Manifest-Version: 1.0\nBundle-SymbolicName: {name}\nBundle-Version: {version}\n"
    if source:
        manifest += f'Eclipse-SourceBundle: {source};version="{version}";roots:="."\n'
    entries = {"META-INF/MANIFEST.MF": (manifest + "\n").encode(), **files}
    if directory:
        for entry, data in entries.items():
            target = path / entry
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
    else:
        with zipfile.ZipFile(path, "w") as archive:
            for entry, data in entries.items():
                archive.writestr(entry, data)
    return f"{name},{version},{path.relative_to(home).as_posix()},4,false\n"


def configure(home, *entries):
    path = home / "configuration/org.eclipse.equinox.simpleconfigurator/bundles.info"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#version=1\n" + "".join(entries), encoding="utf-8")


class CorpusTest(unittest.TestCase):
    def test_only_configured_binaries_and_matching_sources_preserve_original_bytes(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp) / "eclipse"
            original = b'<schema><element name="original"/></schema>'
            descriptor = b'<plugin>\n<extension-point id="p" schema="schema/p.exsd"/>\n</plugin>'
            provider = bundle(home, "org.example.provider", "1.0.0", {
                "plugin.xml": descriptor, "schema/p.exsd": original,
            }, directory=True)
            source = bundle(home, "org.example.provider.source", "1.0.0", {
                "schema/p.exsd": b"<schema>not binary bytes</schema>",
                "schema/shared.exsd": b"<schema/>",
            }, source="org.example.provider")
            mismatched = bundle(home, "org.example.wrong.source", "2.0.0", {
                "schema/wrong.exsd": b"<schema/>",
            }, source="org.example.provider")
            consumer_xml = b'<plugin>\n<extension point="org.example.provider.p"/>\n</plugin>'
            consumer = bundle(home, "org.example.consumer", "1.0.0", {
                "plugin.xml": consumer_xml, "plugin.properties": b"label=Original\n",
            })
            bundle(home, "org.example.unconfigured", "1.0.0", {
                "plugin.xml": b'<plugin><extension point="org.example.provider.p"/></plugin>',
                "schema/not-in-study.exsd": b"<schema/>",
            })
            configure(home, provider, source, mismatched, consumer)
            output = Path(temp) / "corpus"
            result = CORPUS.prepare_corpus(home, output)
            self.assertEqual(result["summary"]["configuredBinaryBundles"], 2)
            self.assertEqual(result["summary"]["configuredSourceBundles"], 2)
            self.assertEqual(result["summary"]["projects"], 2)
            self.assertEqual(result["summary"]["schemaFiles"], 2)
            self.assertEqual(result["summary"]["unmatchedSourceBundles"], 1)
            self.assertEqual((output / "projects/org.example.provider/schema/p.exsd").read_bytes(), original)
            self.assertEqual((output / "projects/org.example.provider/plugin.xml").read_bytes(), descriptor)
            self.assertEqual((output / "projects/org.example.consumer/plugin.xml").read_bytes(), consumer_xml)
            self.assertFalse((output / "projects/org.example.provider/schema/wrong.exsd").exists())
            self.assertFalse((output / "projects/org.example.unconfigured").exists())

    def test_contribution_mapping_retains_lines_and_distinguishes_missing_schema_from_missing_point(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp) / "eclipse"
            provider = bundle(home, "org.example.provider", "1.0.0", {
                "plugin.xml": b'<plugin>\n<extension-point id="p" schema="schema/p.exsd"/>\n'
                    b'<extension-point id="org.example.external.q" schema="schema/missing.exsd"/>\n</plugin>',
                "schema/p.exsd": b"<schema/>",
            })
            consumer = bundle(home, "org.example.consumer", "1.0.0", {
                "plugin.xml": b'<plugin>\n<extension point="org.example.provider.p" id="contribution"/>\n'
                    b'<extension point="org.example.external.q"/>\n'
                    b'<extension point="org.example.absent.p"/>\n</plugin>',
            })
            configure(home, provider, consumer)
            result = CORPUS.prepare_corpus(home, Path(temp) / "corpus")
            actual = result["contributions"]
            self.assertEqual([item["line"] for item in actual], [2, 3, 4])
            self.assertEqual([item["schemaStatus"] for item in actual], ["present", "missing-schema", "undeclared-point"])
            self.assertEqual(actual[0]["extensionId"], "contribution")
            self.assertEqual(actual[0]["schemaProjectRelativePath"], "projects/org.example.provider/schema/p.exsd")
            self.assertEqual(result["summary"]["missingDeclaredSchemas"], 1)

    def test_configured_identity_mismatch_fails_instead_of_using_another_version(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp) / "eclipse"
            entry = bundle(home, "org.example.provider", "1.0.0", {"plugin.xml": b"<plugin/>"})
            configure(home, entry.replace(",1.0.0,", ",2.0.0,"))
            with self.assertRaisesRegex(ValueError, "configured.*identity|Configured.*identity"):
                CORPUS.prepare_corpus(home, Path(temp) / "corpus")

    def test_osgi_omitted_zero_version_components_are_equivalent(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp) / "eclipse"
            entry = bundle(home, "org.example.provider", "1.85", {"plugin.xml": b"<plugin/>"})
            configure(home, entry.replace(",1.85,", ",1.85.0,"))
            try:
                report = CORPUS.prepare_corpus(home, Path(temp) / "corpus")
            except ValueError:
                self.fail("OSGi 1.85 and 1.85.0 must identify the same bundle version")
            self.assertEqual(report["summary"]["configuredBinaryBundles"], 1)
            self.assertEqual(report["configuredBundles"][0]["bundleVersion"], "1.85")
            self.assertEqual(report["configuredBundles"][0]["configuration"]["version"], "1.85.0")

    def test_non_provider_duplicate_versions_and_instrumentation_are_inventory_not_projects(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp) / "eclipse"
            older = bundle(home, "org.example.library", "1.0.0", {})
            (home / "plugins/org.example.library.jar").rename(home / "plugins/org.example.library-old.jar")
            older = older.replace("plugins/org.example.library.jar", "plugins/org.example.library-old.jar")
            newer = bundle(home, "org.example.library", "2.0.0", {})
            provider = bundle(home, "org.example.provider", "1.0.0", {"plugin.xml": b"<plugin/>"})
            observer = bundle(home, "org.eclipse.pde.xmlstudy.probe", "1.0.0", {"plugin.xml": b"<plugin/>"})
            configure(home, older, newer, provider, observer)
            try:
                report = CORPUS.prepare_corpus(home, Path(temp) / "corpus")
            except ValueError:
                self.fail("Configured library versions without XML must be recorded without choosing a version")
            self.assertEqual(report["summary"].get("configuredBinaryBundles"), 4)
            self.assertEqual(report["summary"].get("productionBinaryBundles"), 3)
            self.assertEqual(report["summary"].get("excludedInstrumentationBundles"), 1)
            self.assertEqual([item["bundleId"] for item in report["projects"]], ["org.example.provider"])


if __name__ == "__main__":
    unittest.main()
