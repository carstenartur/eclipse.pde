#!/usr/bin/env python3
# SPDX-License-Identifier: EPL-2.0
"""Run StorageSchemaDescriptorTest against real Eclipse/JUnit jars, without stubs.

Supply --revision for a baseline descriptor from Git; otherwise use the worktree.
The same worktree test runs in both cases. Exact compiler/test output is retained
under --label in --output. A failed regression test returns nonzero, as it should.
This is a classpath test of the storage loader, not an Eclipse startup benchmark.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import zipfile


PRODUCTION = "ui/org.eclipse.pde.core/src/org/eclipse/pde/internal/core/schema/StorageSchemaDescriptor.java"
TEST = "ui/org.eclipse.pde.ui.tests/src/org/eclipse/pde/core/tests/internal/schema/StorageSchemaDescriptorTest.java"
TEST_CLASS = "org.eclipse.pde.core.tests.internal.schema.StorageSchemaDescriptorTest"
RUNNER = """
import org.junit.platform.engine.discovery.DiscoverySelectors;
import org.junit.platform.launcher.core.LauncherDiscoveryRequestBuilder;
import org.junit.platform.launcher.core.LauncherFactory;
import org.junit.platform.launcher.listeners.SummaryGeneratingListener;

public class StorageStreamTestRunner {
    public static void main(String[] args) {
        var request = LauncherDiscoveryRequestBuilder.request()
                .selectors(DiscoverySelectors.selectClass(args[0])).build();
        var listener = new SummaryGeneratingListener();
        var launcher = LauncherFactory.create();
        launcher.registerTestExecutionListeners(listener);
        launcher.execute(request);
        var result = listener.getSummary();
        System.out.printf("tests_found=%d tests_started=%d tests_succeeded=%d tests_failed=%d tests_aborted=%d tests_skipped=%d%n",
                result.getTestsFoundCount(), result.getTestsStartedCount(), result.getTestsSucceededCount(),
                result.getTestsFailedCount(), result.getTestsAbortedCount(), result.getTestsSkippedCount());
        for (var failure : result.getFailures()) {
            System.out.println("FAIL " + failure.getTestIdentifier().getDisplayName());
            failure.getException().printStackTrace(System.out);
        }
        if (result.getTestsFoundCount() == 0 || result.getTestsFailedCount() != 0
                || result.getTestsAbortedCount() != 0 || result.getTestsSucceededCount() != result.getTestsFoundCount()) {
            System.exit(1);
        }
    }
}
"""


def run(command):
    result = subprocess.run(command, text=True, capture_output=True, check=False)
    return {"exit_code": result.returncode, "stdout": result.stdout, "stderr": result.stderr}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--java-home", type=Path, required=True)
    parser.add_argument("--sdk-plugins", type=Path, required=True)
    parser.add_argument("--pde-core-jar", type=Path, required=True)
    parser.add_argument("--revision", help="Git revision of the production descriptor; omit to test the worktree.")
    parser.add_argument("--label", required=True)
    parser.add_argument("--output", type=Path, default=Path("benchmarks/xml-startup-attribution/storage_stream-results.json"))
    args = parser.parse_args()
    root = args.root.resolve()
    java = args.java_home.resolve() / "bin" / "java"
    javac = args.java_home.resolve() / "bin" / "javac"
    plugins = args.sdk_plugins.resolve()
    pde_jar = args.pde_core_jar.resolve()
    if args.revision:
        source = subprocess.check_output(["git", "-C", str(root), "show", f"{args.revision}:{PRODUCTION}"])
    else:
        source = (root / PRODUCTION).read_bytes()
    dependency_jars = sorted(path for path in plugins.glob("*.jar") if not path.name.startswith("org.eclipse.pde.core_"))
    if not dependency_jars:
        raise SystemExit(f"No Eclipse/JUnit jars found in {plugins}")
    record = {
        "source_revision": args.revision or "worktree",
        "production_source_sha256": hashlib.sha256(source).hexdigest(),
        "test_source_sha256": hashlib.sha256((root / TEST).read_bytes()).hexdigest(),
        "java_version": run([str(java), "-version"]),
        "pde_dependency_jar": str(pde_jar),
        "pde_dependency_sha256": hashlib.sha256(pde_jar.read_bytes()).hexdigest(),
        "sdk_plugins": str(plugins),
        "mode": "Compile the actual descriptor and regression test; run against official PDE, Eclipse, and JUnit classes.",
        "scope_limit": "No OSGi/UI launch, full Tycho suite, startup timing, or guaranteed-leak claim.",
    }
    with tempfile.TemporaryDirectory(prefix="pde-storage-stream-") as directory:
        temporary = Path(directory)
        core_classes = temporary / "official-pde-classes"
        # Loading the official classes from a directory avoids signed-package
        # conflicts with the freshly compiled descriptor. The jar is not changed.
        with zipfile.ZipFile(pde_jar) as archive:
            archive.extractall(core_classes)
        classes = temporary / "classes"
        classes.mkdir()
        source_file = temporary / "StorageSchemaDescriptor.java"
        source_file.write_bytes(source)
        runner_file = temporary / "StorageStreamTestRunner.java"
        runner_file.write_text(RUNNER, encoding="utf-8")
        classpath = os.pathsep.join(str(path) for path in [classes, core_classes, *dependency_jars])
        record["compile"] = run([
            str(javac), "--release", "21", "-cp", classpath, "-d", str(classes),
            str(source_file), str(root / TEST), str(runner_file),
        ])
        if record["compile"]["exit_code"] == 0:
            record["tests"] = run([str(java), "-cp", classpath, "StorageStreamTestRunner", TEST_CLASS])
    output = args.output if args.output.is_absolute() else root / args.output
    report = json.loads(output.read_text(encoding="utf-8")) if output.exists() else {"runs": {}}
    report["runs"][args.label] = record
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    for stage in ("compile", "tests"):
        if stage in record:
            result = record[stage]
            print(f"{args.label} {stage}: exit={result['exit_code']}")
            print(result["stdout"], end="")
            print(result["stderr"], end="")
    return record.get("tests", record["compile"])["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
