#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
: "${XML_TRACE_JAVA_HOME:?Point XML_TRACE_JAVA_HOME at a JDK 17 or newer}"
: "${XML_TRACE_ASM_DIR:?Point XML_TRACE_ASM_DIR at a directory containing asm, asm-commons and asm-tree jars}"
rm -rf build/bootstrap build/agent build/fat
mkdir -p build/bootstrap build/agent build/fat
asm_jars=("$XML_TRACE_ASM_DIR"/asm*.jar)
if (( ${#asm_jars[@]} != 3 )); then echo 'Expected exactly asm, asm-commons and asm-tree jars from the same recent release' >&2; exit 2; fi
classpath=$(IFS=:; echo "${asm_jars[*]}")
"$XML_TRACE_JAVA_HOME/bin/javac" --release 17 -d build/bootstrap bootstrap/org/eclipse/pde/xmlstudy/trace/bootstrap/TraceBridge.java
"$XML_TRACE_JAVA_HOME/bin/jar" --create --date=2026-11-04T00:00:00Z --file build/xml-trace-bootstrap.jar -C build/bootstrap .
"$XML_TRACE_JAVA_HOME/bin/javac" --release 17 -cp "build/xml-trace-bootstrap.jar:$classpath" -d build/agent src/org/eclipse/pde/xmlstudy/trace/TraceAgent.java
cp -a build/agent/. build/fat/
for jar in "${asm_jars[@]}"; do (cd build/fat && "$XML_TRACE_JAVA_HOME/bin/jar" --extract --file "$jar"); done
rm -f build/fat/module-info.class
cat > build/MANIFEST.MF <<'MANIFEST'
Manifest-Version: 1.0
Premain-Class: org.eclipse.pde.xmlstudy.trace.TraceAgent
Can-Retransform-Classes: true

MANIFEST
"$XML_TRACE_JAVA_HOME/bin/jar" --create --date=2026-11-04T00:00:00Z --file build/xml-trace-agent.jar --manifest build/MANIFEST.MF -C build/fat .
sha256sum build/xml-trace-agent.jar build/xml-trace-bootstrap.jar
