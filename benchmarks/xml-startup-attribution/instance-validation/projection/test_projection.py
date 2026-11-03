"""Checks of the deliberately bounded, non-mutating EXSD grammar projection."""

from pathlib import Path
import hashlib
import json
import tempfile
import unittest

from lxml import etree

try:
    from project_grammar import ProjectionError, audit, build_projection
except ImportError:
    ProjectionError = None
    build_projection = None


class GrammarProjectionTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(build_projection, "The bounded projection is not implemented")
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.bundle = Path(self.directory.name) / "example.provider"
        (self.bundle / "schema").mkdir(parents=True)
        self.roots = {"example.provider": self.bundle}

    def schema(self, content, name="point.exsd"):
        path = self.bundle / "schema" / name
        path.write_text('<schema xmlns="http://www.w3.org/2001/XMLSchema" '
                        'targetNamespace="example.provider">' + content + '</schema>')
        return path

    def projection(self, content):
        return build_projection(self.schema(content), self.roots)

    @staticmethod
    def instance(text):
        return etree.fromstring(text.encode())

    def test_sequence_order_is_preserved(self):
        p = self.projection('''<element name="extension"><complexType><sequence>
          <element ref="first"/><element ref="second"/>
          </sequence></complexType></element>
          <element name="first"/><element name="second"/>''')
        self.assertEqual("valid", p.check(self.instance('<extension><first/><second/></extension>'))["status"])
        self.assertEqual("invalid", p.check(self.instance('<extension><second/><first/></extension>'))["status"])

    def test_nested_choice_minimum_and_maximum_are_preserved(self):
        p = self.projection('''<element name="extension"><complexType><choice minOccurs="1" maxOccurs="2">
          <sequence><element ref="a"/><element ref="b"/></sequence><element ref="c"/>
          </choice></complexType></element><element name="a"/><element name="b"/><element name="c"/>''')
        for xml in ('<extension><a/><b/></extension>', '<extension><c/><a/><b/></extension>'):
            self.assertEqual("valid", p.check(self.instance(xml))["status"])
        for xml in ('<extension/>', '<extension><a/></extension>', '<extension><c/><c/><c/></extension>'):
            self.assertEqual("invalid", p.check(self.instance(xml))["status"])

    def test_boolean_lexical_space_is_standard_xsd(self):
        p = self.projection('''<element name="extension"><complexType>
          <attribute name="enabled" type="boolean" use="required"/>
          </complexType></element>''')
        for value in ("true", "false", "1", "0"):
            self.assertEqual("valid", p.check(self.instance(f'<extension enabled="{value}"/>'))["status"])
        for value in ("TRUE", "not-a-boolean", ""):
            self.assertEqual("invalid", p.check(self.instance(f'<extension enabled="{value}"/>'))["status"])

    def test_non_whitespace_text_in_element_only_content_is_rejected(self):
        p = self.projection('<element name="extension"><complexType><sequence><element ref="item"/></sequence>'
                            '</complexType></element><element name="item"/>')
        self.assertEqual("valid", p.check(self.instance('<extension> \n <item/> </extension>'))["status"])
        self.assertEqual("invalid", p.check(self.instance('<extension>not allowed<item/></extension>'))["status"])

    def test_legacy_default_is_mapped_without_changing_inputs(self):
        path = self.schema('''<annotation><appInfo><meta.schema plugin="example.provider" id="point"/></appInfo></annotation>
          <element name="extension"><complexType><attribute name="enabled" type="boolean"
          use="default" value="false"/></complexType></element>''')
        before = path.read_bytes()
        p = build_projection(path, self.roots)
        instance = self.instance('<extension/>')
        original_instance = etree.tostring(instance)
        self.assertEqual("valid", p.check(instance)["status"])
        self.assertEqual(before, path.read_bytes())
        self.assertEqual(original_instance, etree.tostring(instance))
        self.assertIn('default="false"', p.xsd.decode())
        self.assertNotIn('use="default"', p.xsd.decode())
        self.assertNotIn('appInfo', p.xsd.decode())

    def test_includes_resolve_locally_with_provenance(self):
        shared = self.schema('<element name="item"/>', "shared.exsd")
        root = self.schema('''<include schemaLocation="schema://example.provider/schema/shared.exsd"/>
          <include schemaLocation="shared.exsd"/>
          <element name="extension"><complexType><sequence><element ref="item"/></sequence></complexType></element>''')
        p = build_projection(root, self.roots)
        self.assertEqual("valid", p.check(self.instance('<extension><item/></extension>'))["status"])
        self.assertEqual({root.resolve(), shared.resolve()}, set(p.inputs))

    def test_missing_include_and_unsupported_construct_are_unchecked(self):
        for xml, reason in ((
                '<include schemaLocation="absent.exsd"/>', "missing_schema"), (
                '<element name="extension"><complexType><sequence><any/></sequence></complexType></element>',
                "unsupported_construct")):
            with self.assertRaises(ProjectionError) as failure:
                self.projection(xml)
            self.assertEqual(reason, failure.exception.code)

    def test_conflicting_global_declarations_are_unchecked(self):
        self.schema('<element name="item" type="string"/>', "shared.exsd")
        with self.assertRaises(ProjectionError) as failure:
            self.projection('<include schemaLocation="shared.exsd"/><element name="item" type="boolean"/>')
        self.assertEqual("conflicting_declaration", failure.exception.code)

    def test_executable_extension_child_alternative_is_explicitly_unchecked(self):
        p = self.projection('''<element name="extension"><complexType><sequence><element ref="item"/></sequence>
          </complexType></element><element name="item"><complexType>
          <attribute name="class" type="string" use="required"><annotation><appInfo>
          <meta.attribute kind="java"/></appInfo></annotation></attribute></complexType></element>''')
        self.assertEqual("valid", p.check(self.instance('<extension><item class="example.Type"/></extension>'))["status"])
        result = p.check(self.instance('<extension><item><class class="example.Factory"/></item></extension>'))
        self.assertEqual("unchecked", result["status"])
        self.assertEqual("executable_extension_child", result["reason"])

    def test_identifier_metadata_does_not_relax_declared_enumeration(self):
        p = self.projection('''<element name="extension"><complexType><attribute name="id">
          <annotation><appinfo><meta.attribute kind="identifier"/></appinfo></annotation>
          <simpleType><restriction base="string"><enumeration value="*"/></restriction></simpleType>
          </attribute></complexType></element>''')
        self.assertEqual({("extension", "id")}, getattr(p, "identifier_attributes", None))
        self.assertEqual("invalid", p.check(self.instance('<extension id="real.identifier"/>'))["status"])

    def test_namespaced_instance_attributes_are_unchecked(self):
        p = self.projection('<element name="extension"/>')
        result = p.check(self.instance('<extension xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
                                       'xmlns:xs="http://www.w3.org/2001/XMLSchema" xsi:type="xs:string"/>'))
        self.assertEqual("unchecked", result["status"])

    def test_foreign_namespace_include_is_unchecked(self):
        self.schema('<element name="item"/>', "shared.exsd")
        with self.assertRaises(ProjectionError) as failure:
            self.projection('<other:include xmlns:other="urn:foreign" schemaLocation="shared.exsd"/>')
        self.assertEqual("unsupported_construct", failure.exception.code)

    def test_audit_rejects_changed_or_unlisted_include_against_frozen_inventory(self):
        shared = self.schema('<element name="item"><complexType><attribute name="must" type="string" '
                             'use="required"/></complexType></element>', "shared.exsd")
        root = self.schema('<include schemaLocation="shared.exsd"/><element name="extension"><complexType>'
                           '<sequence><element ref="item"/></sequence><attribute name="point" type="string"/>'
                           '</complexType></element>')
        descriptor = self.bundle / "plugin.xml"
        descriptor.write_text('<plugin><extension point="example.provider.point"><item/></extension></plugin>')
        corpus = Path(self.directory.name)
        sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
        schema_items = [{"projectRelativePath": str(p.relative_to(corpus)), "sha256": sha(p)} for p in (root, shared)]
        inventory = {
            "projects": [{"bundleId": "example.provider", "projectRelativePath": self.bundle.name}],
            "schemas": schema_items,
            "descriptors": [{"bundleId": "example.provider", "descriptor": "plugin.xml",
                             "projectRelativePath": str(descriptor.relative_to(corpus)), "sha256": sha(descriptor)}],
            "contributions": [{"bundleId": "example.provider", "descriptor": "plugin.xml", "line": 1,
                               "xmlPath": "/plugin/extension", "extensionPointId": "example.provider.point",
                               "schemaStatus": "present", "schemaProjectRelativePath": str(root.relative_to(corpus)),
                               "schemaSha256": sha(root)}],
        }
        manifest = corpus / "corpus-manifest.json"
        manifest.write_text(json.dumps(inventory))
        self.assertEqual({"invalid": 1}, audit(corpus)["summary"]["statuses"])
        original = shared.read_bytes()
        shared.write_bytes(original.replace(b' use="required"', b''))
        with self.assertRaisesRegex(ValueError, "Schema changed since inventory"):
            audit(corpus)
        shared.write_bytes(original)
        inventory["schemas"] = schema_items[:1]
        manifest.write_text(json.dumps(inventory))
        self.assertEqual({"unlisted_schema": 1}, audit(corpus)["summary"]["uncheckedReasons"])


if __name__ == "__main__":
    unittest.main()
