#!/usr/bin/env bash
set -euo pipefail
PREAMBLE_AUDIT_DIR=$(cd "$(dirname "$0")" && pwd)
PREAMBLE_CORPUS_ROOT=$(cd "$PREAMBLE_AUDIT_DIR/.." && pwd)
PDE_JAVA_HOME=${PDE_JAVA_HOME:-/workspace/scratch/567cb6a530cb/wizard-test-runtime/jdk-25.0.5+8}
PREAMBLE_MAVEN=${PREAMBLE_MAVEN:-/root/.m2/wrapper/dists/apache-maven-3.9.16/9c464432/bin/mvn}
"$PDE_JAVA_HOME/bin/javac" --release 25 -encoding UTF-8 -d "$PREAMBLE_AUDIT_DIR/base/classes" "$PREAMBLE_AUDIT_DIR/base/src/org/sandbox/jdt/internal/corext/fix/helper/SchemaTransformationUtils.java"
JAVA_HOME="$PDE_JAVA_HOME" PATH="$PDE_JAVA_HOME/bin:$PATH" "$PREAMBLE_MAVEN" -o -f "$PREAMBLE_AUDIT_DIR/head/pom.xml" -Daudit.root="$PREAMBLE_CORPUS_ROOT" test
