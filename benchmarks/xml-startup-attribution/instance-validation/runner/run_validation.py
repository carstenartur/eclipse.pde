#!/usr/bin/env python3
"""Run the real PDE validator on a disposable copy of a recorded corpus."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

from build_runner import build


CONTROL_ID = "org.eclipse.pde.xmlstudy.validationcontrols"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def original_resources(projects: Path) -> dict:
    """PDE may persist project metadata; hash the original input resources separately."""
    return {str(path.relative_to(projects)): sha256(path) for path in sorted(projects.rglob("*"))
            if path.is_file() and (path.name in {"plugin.xml", "fragment.xml", "MANIFEST.MF"}
                                   or path.suffix in {".properties", ".exsd", ".mxsd"})}


def control_schema(point: str, content: str, definitions: str) -> str:
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<schema targetNamespace="{CONTROL_ID}">
  <annotation><appinfo><meta.schema plugin="{CONTROL_ID}" id="{point}" name="Validation control"/></appinfo></annotation>
  <element name="extension"><complexType>{content}<attribute name="point" type="string" use="required"/></complexType></element>
  {definitions}
</schema>
'''


def create_controls(root: Path) -> Path:
    project = root / CONTROL_ID
    (project / "META-INF").mkdir(parents=True)
    (project / "schema").mkdir()
    (project / "cases").mkdir()
    (project / ".project").write_text(f'''<?xml version="1.0" encoding="UTF-8"?>
<projectDescription><name>{CONTROL_ID}</name><comment>Disposable validator controls</comment><projects/><buildSpec/>
<natures><nature>org.eclipse.jdt.core.javanature</nature><nature>org.eclipse.pde.PluginNature</nature></natures></projectDescription>
''')
    (project / ".classpath").write_text('<?xml version="1.0" encoding="UTF-8"?><classpath><classpathentry kind="output" path="bin"/></classpath>\n')
    (project / "META-INF/MANIFEST.MF").write_text(
        f"Manifest-Version: 1.0\nBundle-ManifestVersion: 2\nBundle-SymbolicName: {CONTROL_ID};singleton:=true\nBundle-Version: 1.0.0\n\n")
    (project / "plugin.xml").write_text('''<?xml version="1.0" encoding="UTF-8"?>
<?eclipse version="3.4"?>
<plugin>
 <extension-point id="grammar" name="Grammar" schema="schema/grammar.exsd"/>
 <extension-point id="order" name="Order" schema="schema/order.exsd"/>
 <extension-point id="choice" name="Nested choice" schema="schema/choice.exsd"/>
 <extension-point id="choiceSequence" name="Choice containing sequence" schema="schema/choiceSequence.exsd"/>
 <extension-point id="missing" name="Missing schema" schema="schema/absent.exsd"/>
 <extension-point id="unspecified" name="No declared schema"/>
</plugin>
''')
    schemas = {
        "grammar": control_schema("grammar", '<sequence><element ref="entry" minOccurs="1" maxOccurs="1"/></sequence>', '''
<element name="entry"><complexType>
 <attribute name="name" type="string" use="required"/>
 <attribute name="flag" type="boolean"/>
 <attribute name="mode"><simpleType><restriction base="string"><enumeration value="alpha"/><enumeration value="beta"/></restriction></simpleType></attribute>
</complexType></element>'''),
        "order": control_schema("order", '<sequence><element ref="first"/><element ref="second"/></sequence>',
                                '<element name="first"><complexType/></element><element name="second"><complexType/></element>'),
        "choice": control_schema("choice", '<sequence><choice><element ref="first"/><element ref="second"/></choice><element ref="tail"/></sequence>',
                                 '<element name="first"><complexType/></element><element name="second"><complexType/></element><element name="tail"><complexType/></element>'),
        "choiceSequence": control_schema("choiceSequence", '<choice><sequence><element ref="first"/><element ref="second"/></sequence><element ref="tail"/></choice>',
                                         '<element name="first"><complexType/></element><element name="second"><complexType/></element><element name="tail"><complexType/></element>'),
    }
    for name, text in schemas.items():
        (project / "schema" / f"{name}.exsd").write_text(text)
    cases = [
        ("valid.xml", "accept", "grammar", '<entry name="ok" flag="true" mode="alpha"/>', "Valid grammar comparator"),
        ("unknown-attribute.xml", "reject", "grammar", '<entry name="ok" unknown="value"/>', "Unknown attribute on a known element"),
        ("required-attribute.xml", "reject", "grammar", '<entry/>', "Missing required name attribute"),
        ("unknown-child.xml", "reject", "grammar", '<entry name="ok"/><unknown/>', "Unknown child under extension"),
        ("cardinality-max.xml", "reject", "grammar", '<entry name="one"/><entry name="two"/>', "Two children where maximum is one"),
        ("cardinality-min.xml", "reject", "grammar", '', "Zero children where minimum is one"),
        ("enumeration.xml", "reject", "grammar", '<entry name="ok" mode="gamma"/>', "Invalid enumeration value"),
        ("unknown-point.xml", "reject-point", "absentPoint", '<entry name="ok"/>', "Undeclared extension point"),
        ("missing-schema.xml", "coverage-gap", "missing", '<whatever/>', "Declared point whose schema file is missing"),
        ("undeclared-schema.xml", "coverage-gap", "unspecified", '<whatever/>', "Declared point without a schema declaration"),
        ("boolean.xml", "observe-invalid", "grammar", '<entry name="ok" flag="not-a-boolean"/>', "Invalid lexical boolean value"),
        ("sequence-valid.xml", "accept", "order", '<first/><second/>', "Valid sequence order comparator"),
        ("sequence-reversed.xml", "observe-invalid", "order", '<second/><first/>', "Reversed children in declared sequence"),
        ("choice-valid.xml", "accept", "choice", '<first/><tail/>', "Valid nested choice comparator"),
        ("choice-both.xml", "observe-invalid", "choice", '<first/><second/><tail/>', "Both arms of a single nested choice"),
        ("choice-sequence-valid.xml", "accept", "choiceSequence", '<first/><second/>', "Valid sequence arm inside choice"),
        ("choice-sequence-tail.xml", "accept", "choiceSequence", '<tail/>', "Valid element arm beside sequence inside choice"),
        ("choice-sequence-missing.xml", "observe-invalid", "choiceSequence", '<first/>', "Incomplete sequence arm inside choice"),
        ("text-content.xml", "observe-invalid", "grammar", '<entry name="ok">unexpected text</entry>', "Character content in an attribute-only complex element"),
    ]
    rows = []
    for name, expectation, point, body, description in cases:
        xml = f'<?xml version="1.0" encoding="UTF-8"?>\n<?eclipse version="3.4"?>\n<plugin>\n <extension point="{CONTROL_ID}.{point}">\n  {body}\n </extension>\n</plugin>\n'
        ET.fromstring(xml)
        (project / "cases" / name).write_text(xml)
        rows.append(f"{name}\t{expectation}\t{description}")
    (root / "control-cases.tsv").write_text("\n".join(rows) + "\n")
    return project


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--java-home", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="New/empty run directory")
    parser.add_argument("--timeout", type=int, default=240)
    parser.add_argument("--repeat-load-probe", action="store_true", help="Separate actual-URL repeated-load and file-handle diagnostic")
    args = parser.parse_args()
    reference, corpus, root = args.reference.resolve(), args.corpus.resolve(), args.output.resolve()
    if root.exists() and any(root.iterdir()):
        raise SystemExit(f"Run directory is not empty; will not overwrite results: {root}")
    root.mkdir(parents=True, exist_ok=True)
    built = build(reference, args.java_home / "bin/javac")
    (root / "build.json").write_text(json.dumps(built, indent=2) + "\n")
    copied = root / "corpus"
    shutil.copytree(corpus, copied)
    directories = []
    for line in (corpus / "project-list.txt").read_text().splitlines():
        if line.strip() and not line.lstrip().startswith("#"):
            directories.append(copied / Path(line.strip()).relative_to(corpus))
    project_list = root / "project-list.txt"
    project_list.write_text("".join(f"{path}\n" for path in directories))
    before = original_resources(copied / "projects")
    expected_descriptors = sorted(key for key in before if key.endswith("/plugin.xml") or key.endswith("/fragment.xml"))
    expected_extensions = sum(len(ET.parse(copied / "projects" / key).getroot().findall("extension"))
                              for key in expected_descriptors)
    controls = create_controls(root / "controls")
    install = root / "eclipse"
    (install / "plugins").mkdir(parents=True)
    for item in sorted((reference / "plugins").iterdir()):
        (install / "plugins" / item.name).symlink_to(item.resolve(), target_is_directory=item.is_dir())
    runner_jar = Path(built["jar"])
    shutil.copy2(runner_jar, install / "plugins" / runner_jar.name)
    configuration = install / "configuration"
    (configuration / "org.eclipse.equinox.simpleconfigurator").mkdir(parents=True)
    shutil.copy2(reference / "configuration/config.ini", configuration / "config.ini")
    bundles = reference / "configuration/org.eclipse.equinox.simpleconfigurator/bundles.info"
    (configuration / "org.eclipse.equinox.simpleconfigurator/bundles.info").write_text(
        bundles.read_text().rstrip() + f"\norg.eclipse.pde.xmlstudy.instances,1.0.0,plugins/{runner_jar.name},4,false\n")
    launchers = sorted((install / "plugins").glob("org.eclipse.equinox.launcher_*.jar"))
    if len(launchers) != 1:
        raise ValueError(f"Expected one launcher, found {launchers}")
    output = root / "pde-validation.json"
    command = [str((args.java_home / "bin/java").resolve()), "-Xms256m", "-Xmx1024m",
               "--enable-native-access=ALL-UNNAMED", "-Dxml.study.enabled=false",
               "-Dxml.instances.repeatedLoadProbe=" + str(args.repeat_load_probe).lower(),
               "-Dxml.instances.projectList=" + str(project_list),
               "-Dxml.instances.controlDirectory=" + str(controls),
               "-Dxml.instances.controlCases=" + str(root / "controls/control-cases.tsv"),
               "-Dxml.instances.output=" + str(output),
               "-jar", str(launchers[0]), "-install", str(install),
               "-configuration", str(configuration), "-data", str(root / "workspace"),
               "-nosplash", "-consoleLog", "-application", "org.eclipse.pde.xmlstudy.instances.validate"]
    metadata = {"command": command, "timeoutSeconds": args.timeout, "reference": str(reference),
                "corpus": str(corpus), "projectCount": len(directories),
                "expectedDescriptorFiles": expected_descriptors, "expectedContributions": expected_extensions,
                "originalInputHashes": before, "runnerSha256": sha256(Path(__file__))}
    (root / "execution.json").write_text(json.dumps(metadata, indent=2) + "\n")
    start = time.monotonic()
    with (root / "eclipse.log").open("w") as log:
        try:
            completed = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, timeout=args.timeout)
            metadata["exitCode"] = completed.returncode
            metadata["timedOut"] = False
        except subprocess.TimeoutExpired:
            metadata["exitCode"] = None
            metadata["timedOut"] = True
    metadata["diagnosticProcessWallSeconds"] = time.monotonic() - start
    metadata["inputHashesUnchanged"] = before == original_resources(copied / "projects")
    metadata["eclipseErrorEntries"] = len(re.findall(r"!ENTRY\s+\S+\s+4\s", (root / "eclipse.log").read_text(errors="replace")))
    metadata["verification"] = "failed"
    if output.exists():
        result = json.loads(output.read_text())
        actual_descriptors = sorted(file["project"] + "/" + file["file"] for file in result.get("files", []))
        actual_extensions = result.get("summary", {}).get("extensionContributions")
        metadata["descriptorSetMatches"] = actual_descriptors == expected_descriptors
        metadata["contributionCountMatches"] = actual_extensions == expected_extensions
        metadata["summary"] = result.get("summary")
        metadata["controlsPassed"] = result.get("controlsPassed")
        if (metadata["exitCode"] == 0 and not metadata["timedOut"] and metadata["eclipseErrorEntries"] == 0 and metadata["inputHashesUnchanged"]
                and metadata["descriptorSetMatches"] and metadata["contributionCountMatches"]
                and result.get("status") == "completed" and result.get("controlsPassed")):
            metadata["verification"] = "passed"
    (root / "execution.json").write_text(json.dumps(metadata, indent=2) + "\n")
    print(json.dumps({key: value for key, value in metadata.items()
                      if key not in {"command", "originalInputHashes", "expectedDescriptorFiles"}}, indent=2))
    if metadata["verification"] != "passed":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
