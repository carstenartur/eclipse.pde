#!/usr/bin/env python3
"""Contract tests against the two actual EXSD files, baseline or repaired copy.

Set XML_INSTANCE_CORPUS to the chosen corpus. defaultHandler is checked as its
global element so the projection's deliberate Java-child skip cannot hide its
declared parameter cardinality. These tests do not claim full XMLSpy equivalence.
"""

import json
import os
from pathlib import Path
import sys
import unittest

from lxml import etree

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_grammar import build_projection


class ExtraSchemaRepairsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        corpus = Path(os.environ["XML_INSTANCE_CORPUS"])
        inventory = json.loads((corpus / "corpus-manifest.json").read_text())
        roots = {p["bundleId"]: corpus / p["projectRelativePath"] for p in inventory["projects"]}
        expected = {(corpus / p["projectRelativePath"]).resolve(): p["sha256"]
                    for p in inventory["schemas"]}
        cls.commands = build_projection(roots["org.eclipse.ui"] / "schema/commands.exsd", roots, expected)
        cls.providers = build_projection(roots["org.eclipse.e4.ui.css.core"] /
            "schema/org.eclipse.e4.ui.css.core.elementProvider.exsd", roots, expected)

    def check_xml(self, schema, xml, expected):
        result = schema.check(etree.fromstring(xml.encode()))
        self.assertEqual(expected, result["status"], result)

    def test_default_handler_accepts_zero_one_and_multiple_parameters(self):
        for count in (0, 1, 2):
            with self.subTest(parameters=count):
                parameters = "".join(f'<parameter name="p{i}" value="v{i}"/>' for i in range(count))
                self.check_xml(self.commands, f'<defaultHandler class="Example">{parameters}</defaultHandler>', "valid")

    def test_default_handler_requires_class(self):
        self.check_xml(self.commands, '<defaultHandler><parameter name="p" value="v"/></defaultHandler>', "invalid")

    def test_parameters_require_name_and_value(self):
        for parameter in ('<parameter name="p"/>', '<parameter value="v"/>'):
            with self.subTest(parameter=parameter):
                self.check_xml(self.commands, f'<defaultHandler class="Example">{parameter}</defaultHandler>', "invalid")

    def test_default_handler_rejects_unknown_children(self):
        self.check_xml(self.commands, '<defaultHandler class="Example"><wrong/></defaultHandler>', "invalid")

    def test_one_extension_accepts_multiple_element_providers(self):
        providers = "".join(f'<provider class="Provider{i}"><widget class="Widget{i}"/></provider>' for i in range(3))
        self.check_xml(self.providers, '<extension point="org.eclipse.e4.ui.css.core.elementProvider">' +
                       providers + '</extension>', "valid")

    def test_provider_extension_keeps_minimum_one(self):
        self.check_xml(self.providers, '<extension point="org.eclipse.e4.ui.css.core.elementProvider"/>', "invalid")

    def test_provider_still_requires_a_widget_with_class(self):
        for provider in ('<provider class="Example"/>', '<provider class="Example"><widget/></provider>'):
            with self.subTest(provider=provider):
                self.check_xml(self.providers, '<extension point="org.eclipse.e4.ui.css.core.elementProvider">' +
                               provider + '</extension>', "invalid")


if __name__ == "__main__":
    unittest.main()
