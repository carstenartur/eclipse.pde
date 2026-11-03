#!/usr/bin/env bash
set -euo pipefail

# Supply an actual Eclipse Platform runtime jar; no test substitute is generated.
: "${JAVA_HOME:?Set JAVA_HOME to a JDK 25 or newer}"
: "${ECLIPSE_RUNTIME_JAR:?Set ECLIPSE_RUNTIME_JAR to org.eclipse.core.runtime 3.35.0 or compatible}"

comparison_root=$(cd "$(dirname "$0")/../.." && pwd)
comparison_classes=$(mktemp -d)
trap 'rm -rf "$comparison_classes"' EXIT

"$JAVA_HOME/bin/javac" -Xlint:all,-dangling-doc-comments \
  -cp "$ECLIPSE_RUNTIME_JAR" -d "$comparison_classes" \
  "$comparison_root/ui/org.eclipse.pde.core/src/org/eclipse/pde/internal/core/XMLDefaultHandler.java" \
  "$comparison_root/ui/org.eclipse.pde.core/src/org/eclipse/pde/internal/core/schema/SchemaDocumentParser.java" \
  "$comparison_root/benchmarks/direct-dom-comparison/src/org/eclipse/pde/internal/core/schema/SchemaDocumentParserComparison.java" \
  "$comparison_root/benchmarks/direct-dom-comparison/src/org/eclipse/pde/internal/core/schema/SchemaDocumentParserBenchmark.java"

comparison_classpath="$comparison_classes:$ECLIPSE_RUNTIME_JAR"
"$JAVA_HOME/bin/java" -cp "$comparison_classpath" \
  org.eclipse.pde.internal.core.schema.SchemaDocumentParserComparison "$comparison_root"
if [[ "${1:-}" != --check ]]; then
  "$JAVA_HOME/bin/java" -Xms256m -Xmx256m -cp "$comparison_classpath" \
    org.eclipse.pde.internal.core.schema.SchemaDocumentParserBenchmark "$comparison_root" "${1:-100}"
fi
