"""The sensitivity diagnostic must not silently redefine the baseline inputs."""

from pathlib import Path
import tempfile
import unittest

from lxml import etree

from project_grammar import build_projection
try:
    from classify_findings import analyze_contribution
except ImportError:
    analyze_contribution = None


class ClassificationTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(analyze_contribution, "Classification is not implemented")
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def projection(self, declarations):
        path = self.root / "point.exsd"
        path.write_text('<schema>' + declarations + '</schema>')
        return build_projection(path, {"example": self.root})

    def test_xml_whitespace_under_empty_content_is_distinguished_from_other_text(self):
        p = self.projection('<element name="extension"><complexType/></element>')
        for text, category in ((" \t\r\n ", "empty_content_xml_whitespace"), ("\u00a0", "empty_content_other_text")):
            node = etree.fromstring(f'<extension>{text}</extension>'.encode())
            result = analyze_contribution(p, node)
            self.assertEqual([category], [x["category"] for x in result["diagnostics"]])

    def test_identifier_enumeration_keeps_its_baseline_error(self):
        p = self.projection('''<element name="extension"><complexType>
          <attribute name="target"><annotation><appinfo><meta.attribute kind="identifier"/></appinfo></annotation>
          <simpleType><restriction base="string"><enumeration value="*"/></restriction></simpleType></attribute>
          <attribute name="mode"><simpleType><restriction base="string"><enumeration value="a"/></restriction></simpleType></attribute>
          </complexType></element>''')
        result = analyze_contribution(p, etree.fromstring(b'<extension target="real.id" mode="other"/>'))
        self.assertEqual({"identifier_enumeration", "closed_enumeration"}, {x["category"] for x in result["diagnostics"]})
        self.assertEqual("invalid", result["sensitivity"]["status"])
        self.assertEqual(2, len(result["sensitivity"]["diagnostics"]))

    def test_sensitivity_changes_only_a_copy_of_diagnosed_empty_content_whitespace(self):
        p = self.projection('''<element name="extension"><complexType><sequence><element ref="item"/></sequence>
          </complexType></element><element name="item"><complexType/></element>''')
        node = etree.fromstring(b'<extension> \n <item> \n </item> \n </extension>')
        original = etree.tostring(node)
        result = analyze_contribution(p, node)
        self.assertEqual("invalid", result["baselineStatus"])
        self.assertEqual("valid", result["sensitivity"]["status"])
        self.assertEqual(1, result["removedWhitespaceNodes"])
        self.assertEqual(original, etree.tostring(node))

    def test_sensitivity_retains_other_structural_errors(self):
        p = self.projection('<element name="extension"><complexType/></element>')
        node = etree.fromstring(b'<extension unsupported="yes"> \n </extension>')
        result = analyze_contribution(p, node)
        self.assertEqual("invalid", result["sensitivity"]["status"])
        self.assertTrue(any("unsupported" in x["message"] for x in result["sensitivity"]["diagnostics"]))


if __name__ == "__main__":
    unittest.main()
