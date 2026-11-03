import unittest

from xml_formatting import tabs_for_schema_indentation


class FormattingTests(unittest.TestCase):
    def test_shortens_structural_indentation(self):
        original = b"<schema>\n   <element name='x'>\n      <complexType/>\n   </element>\n</schema>"
        expected = b"<schema>\n\t<element name='x'>\n\t\t<complexType/>\n\t</element>\n</schema>"
        self.assertEqual(expected, tabs_for_schema_indentation(original))

    def test_preserves_documentation_examples_cdata_comments_and_attributes(self):
        protected = b'''<annotation><documentation>
   text
      &lt;example attr="   value"/&gt;
   <pre>   sample
      more</pre><![CDATA[
      cdata]]></documentation></annotation><!--
      copyright -->'''
        original = b"<schema attr='   value'>\n   " + protected + b"\n</schema>"
        self.assertEqual(b"<schema attr='   value'>\n\t" + protected + b"\n</schema>",
                         tabs_for_schema_indentation(original))

    def test_preserves_xml_space_and_unknown_or_mixed_text(self):
        original = b'''<schema><element xml:space="preserve">
      <complexType/>
   </element><unknown>
      <element/>
   </unknown><element>word
      more</element></schema>'''
        self.assertEqual(original, tabs_for_schema_indentation(original))

    def test_does_not_expand_dtd_or_external_entities(self):
        with self.assertRaises(ValueError):
            tabs_for_schema_indentation(b'<!DOCTYPE schema SYSTEM "https://example.invalid/a"><schema/>')

    def test_preserves_foreign_namespaces(self):
        original = b'<schema><e:element xmlns:e="urn:other">\n   <element/>\n</e:element><element xmlns="urn:other">\n   <element/>\n</element></schema>'
        self.assertEqual(original, tabs_for_schema_indentation(original))

    def test_preserves_mixed_content_across_cdata_and_child_boundaries(self):
        for original in (b'<schema><element><![CDATA[text]]>\n   <element name="x"/></element></schema>',
                         b'<schema><element>\n   <element name="x"/>\n   tail</element></schema>'):
            self.assertEqual(original, tabs_for_schema_indentation(original))


if __name__ == "__main__":
    unittest.main()
