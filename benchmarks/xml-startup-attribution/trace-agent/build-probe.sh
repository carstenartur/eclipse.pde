#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
: "${XML_TRACE_JAVA_HOME:?Point XML_TRACE_JAVA_HOME at a JDK 21 or newer}"
install=$(realpath "${1:?Pass an Eclipse installation}")
rm -rf ../probe/build/classes ../probe/build/test-classes
mkdir -p ../probe/build/classes ../probe/build/test-classes
mapfile -t sources < <(rg --files ../probe/src -g '*.java' | sort)
"$XML_TRACE_JAVA_HOME/bin/javac" --release 21 -encoding UTF-8 -cp "$install/plugins/*" -d ../probe/build/classes "${sources[@]}"
mapfile -t tests < <(rg --files ../probe/tests -g '*.java' | sort)
"$XML_TRACE_JAVA_HOME/bin/javac" --release 21 -encoding UTF-8 -cp ../probe/build/classes -d ../probe/build/test-classes "${tests[@]}"
for test in ProbeLogicTest FdDiagnosticsTest; do
    "$XML_TRACE_JAVA_HOME/bin/java" -cp ../probe/build/classes:../probe/build/test-classes "org.eclipse.pde.xmlstudy.probe.$test"
done
"$XML_TRACE_JAVA_HOME/bin/jar" --create --date=2026-11-04T00:00:00Z --file ../probe/build/org.eclipse.pde.xmlstudy.probe_1.0.0.jar --manifest ../probe/META-INF/MANIFEST.MF -C ../probe/build/classes . -C ../probe plugin.xml
