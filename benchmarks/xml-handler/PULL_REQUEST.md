# Coalesce XML text before constructing DOM nodes

SAX may split one text run across many `characters()` callbacks. `XMLDefaultHandler` currently creates a DOM Text node for every callback; the public getters then normalize these nodes, repeatedly concatenating their contents.

Accumulate the characters in a lazily allocated buffer and create a Text node at element boundaries. The normalized document, whitespace, mixed content and abbreviated mode are preserved. Parser selection and security settings stay unchanged; this adds no dependency or XML-file rewrite.

### Measured effect

A JMH comparison of the actual old and patched handlers over all 49 EXSD schemas from `org.eclipse.ui`, read from a JAR, produced:

| Full mode, original files | Before | After | Reduction |
| --- | ---: | ---: | ---: |
| Thread CPU per 49-file pass | 14.317 ms | 10.871 ms | 24.1% |
| Allocated bytes per pass | 22.052 MiB | 5.231 MiB | 76.3% |

Three JVM forks per mode, JDK 25, the same parser/DOM providers, and exact normalized-DOM comparisons before timing. The paired 95% interval for CPU savings was 3.007–3.884 ms per pass. This is a warm parsing/DOM microbenchmark on a shared VM, not a measurement of total Eclipse startup. Abbreviated mode showed no clear difference; its intervals include zero.

The [reproduction scripts, pinned inputs, full methodology and raw results](https://github.com/carstenartur/eclipse.pde/tree/32b88d9295db36fa9db3d207fc0aad6abfc9b1c5/benchmarks/xml-handler) are on a separate benchmark branch. That branch also records the optional XML-cleanup combination; the figures above measure this patch alone.

### Validation

- Six JUnit tests cover split callbacks, reused SAX buffers, split surrogate pairs, mixed/nested content, whitespace, processing instructions/comments, long fragmented text and abbreviated mode. They are registered in `AllPDECoreTests`.
- The tests pass against both the baseline and patched handler; removing a required flush makes two tests fail.
- `mvn verify -pl :org.eclipse.pde.core,:org.eclipse.pde.ui.tests -Dtest=XMLDefaultHandlerTest` compiles the changed bundles. All six tests also pass in the actual Tycho/OSGi runtime with the UI harness temporarily disabled locally.
- The regular UI harness cannot start in this execution environment because Xvfb cannot create display sockets. No harness/POM change is included; the full UI suite remains for CI.
