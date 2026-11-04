#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
: "${XML_TRACE_JAVA_HOME:?Point XML_TRACE_JAVA_HOME at a JDK 21 or newer}"
: "${XML_TRACE_ASM_DIR:?Point XML_TRACE_ASM_DIR at asm/asm-tree/asm-commons 9.9.1 or newer jars}"
install=$(realpath "${1:?Pass Eclipse installation}")
output=$(realpath -m "${2:?Pass a new output directory}")
mode=${3:-headless}
./build.sh
./build-probe.sh "$install"
mkdir -p controls/classes
"$XML_TRACE_JAVA_HOME/bin/javac" --release 21 -cp "$install/plugins/*" -d controls/classes controls/TraceControls.java controls/EclipseTraceControls.java
node run-eclipse-scenarios.mjs "$install" "$output" "$mode"
