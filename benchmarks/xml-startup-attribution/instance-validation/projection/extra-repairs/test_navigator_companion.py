#!/usr/bin/env python3
"""Dependent navigator declaration contract; run on four/final repaired corpus."""

import json
import os
from pathlib import Path
import sys
import unittest

from lxml import etree

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_grammar import audit, build_projection


class NavigatorCompanionTest(unittest.TestCase):
    def test_navigator_grammar_compiles_and_preserves_expression_constraints(self):
        corpus = Path(os.environ["XML_INSTANCE_CORPUS"])
        inventory = json.loads((corpus / "corpus-manifest.json").read_text())
        roots = {p["bundleId"]: corpus / p["projectRelativePath"] for p in inventory["projects"]}
        expected = {(corpus / p["projectRelativePath"]).resolve(): p["sha256"] for p in inventory["schemas"]}
        grammar = build_projection(roots["org.eclipse.ui.navigator"] / "schema/navigatorContent.exsd", roots, expected)
        cases = {
            '<enablement><equals value="x"/><and><equals value="x"/></and><equals value="x"/></enablement>': 'valid',
            '<enablement/>': 'valid',
            '<enablement><unknown/></enablement>': 'invalid',
            '<enablement><not/></enablement>': 'invalid',
            '<enablement><not><equals value="x"/><equals value="x"/></not></enablement>': 'invalid',
        }
        for xml, expected_status in cases.items():
            with self.subTest(xml=xml):
                self.assertEqual(expected_status, grammar.check(etree.fromstring(xml.encode()))["status"])

    def test_all_seven_original_navigator_contributions_are_checked(self):
        result = audit(Path(os.environ["XML_INSTANCE_CORPUS"]))
        rows = [row for row in result["contributions"]
                if row["extensionPointId"] == "org.eclipse.ui.navigator.navigatorContent"]
        self.assertEqual(7, len(rows))
        self.assertTrue(result["sourceFilesUnchanged"])
        for row in rows:
            with self.subTest(bundle=row["bundleId"], line=row["line"]):
                self.assertIn(row["status"], ("valid", "invalid"), row)


if __name__ == "__main__":
    unittest.main()
