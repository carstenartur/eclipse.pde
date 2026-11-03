#!/usr/bin/env python3
"""Contract checks for the two investigated schema repairs, using real EXSD input.

Set XML_INSTANCE_CORPUS to an original or repaired disposable corpus. The positive
checks fail on the original schemas. These are minimal contract reproductions,
not a claim that the raw EXSD is a valid W3C schema or that startup is faster.
"""

import json
import os
from pathlib import Path
import sys
import unittest

from lxml import etree

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "projection"))
from project_grammar import build_projection


class SchemaRepairsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        corpus = Path(os.environ["XML_INSTANCE_CORPUS"])
        manifest = json.loads((corpus / "corpus-manifest.json").read_text())
        roots = {p["bundleId"]: corpus / p["projectRelativePath"] for p in manifest["projects"]}
        cls.expressions = build_projection(
            roots["org.eclipse.core.expressions"] / "schema/expressionLanguage.exsd", roots)
        cls.configurators = build_projection(
            roots["org.eclipse.ui.ide"] / "schema/projectConfigurators.exsd", roots)

    def check_xml(self, projection, xml, expected):
        result = projection.check(etree.fromstring(xml.encode()))
        self.assertEqual(expected, result["status"], result)

    def test_has_folder_with_path_is_a_supported_configurator_expression(self):
        self.check_xml(self.configurators,
            '<extension point="org.eclipse.ui.ide.projectConfigurators">'
            '<projectConfigurator class="org.eclipse.ui.internal.wizards.datatransfer.EclipseWorkspaceConfigurator" label="Workspace">'
            '<activeWhen><hasFolder path=".metadata"/></activeWhen>'
            '</projectConfigurator></extension>', "valid")

    def test_has_folder_still_requires_its_path(self):
        self.check_xml(self.configurators,
            '<extension point="org.eclipse.ui.ide.projectConfigurators">'
            '<projectConfigurator class="Example" label="Example">'
            '<activeWhen><hasFolder/></activeWhen></projectConfigurator></extension>', "invalid")

    def test_composites_accept_supported_children_in_arbitrary_combinations(self):
        cases = {"enablement": "", "and": "", "or": "", "with": ' variable="v"',
                 "resolve": ' variable="v"', "adapt": ' type="java.lang.String"',
                 "iterate": ' operator="and"'}
        for tag, attributes in cases.items():
            with self.subTest(tag=tag):
                self.check_xml(self.expressions,
                    f'<{tag}{attributes}><equals value="x"/><and><equals value="x"/></and>'
                    f'<equals value="x"/></{tag}>', "valid")

    def test_composites_still_reject_unknown_children(self):
        self.check_xml(self.expressions, '<and><unrecognized/></and>', "invalid")

    def test_not_still_requires_exactly_one_child(self):
        for xml in ('<not/>', '<not><equals value="x"/><equals value="x"/></not>'):
            with self.subTest(xml=xml):
                self.check_xml(self.expressions, xml, "invalid")


if __name__ == "__main__":
    unittest.main()
