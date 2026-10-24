Title: Reuse an idle parser when reading extension point schemas

`Schema.load(InputStream)` creates a securely configured SAX parser for every schema and include. Repeated schema-model loads can share the cost of that construction while retaining exclusive ownership of each active parser.

Keep at most one reset, idle parser in an atomic slot. A read removes the parser from the slot; concurrent or nested reads create their own parser when the slot is empty. A successful read clears the handlers before returning the parser. Failed parses and providers without reset support are not cached. Retire a parser after 100 successful reads because `SAXParser.reset()` need not clear provider-internal symbol tables. The existing secure Eclipse factory and DOCTYPE rejection are unchanged; there is no thread-local cache or global provider switch.

This revisits the concern in #632, which removed parser caching because SAX parsers are not guaranteed to be thread safe. The cache here never exposes an active parser to another read. The use limit bounds accumulated parse history, not the maximum memory required by one schema.

Measured through the complete non-abbreviated PDE schema-model path, including 49 real workbench schemas and 15 includes: reuse reduces allocated bytes from **28.00 to 25.80 MB per batch** against current upstream (7.8%). When combined with #2575, it reduces allocation from **8.19 to 5.99 MB** (26.8% additional reduction). Mean warm thread CPU changes from 15.88 to 15.08 ms against upstream, and from 13.56 to 12.02 ms when added to #2575. These are three-fork means from a shared VM; CPU ranges overlap.

Twenty fresh-JVM first-batch pairs do **not** establish a CPU improvement for reuse alone: the paired median difference is −7.09 ms, with a bootstrap 95% interval of −18.67 to +4.72 ms. This PR therefore claims reduced repeated-load allocation and reports observed warm timings, not a proven Eclipse startup improvement. The combined first-batch result also includes #2575 and must not be attributed to this PR alone.

[Harness, raw results and reproduction bundle](https://github.com/carstenartur/eclipse.pde/tree/perf/coalesce-xml-text-benchmark/benchmarks/schema-load).

Validation: focused `mvn clean verify` for `org.eclipse.pde.core` and `org.eclipse.pde.ui.tests` with `-Dtest=SchemaReaderTest`: **8 tests, no failures or errors**. Coverage includes sequential reuse and separate documents, full/abbreviated modes, released handlers, concurrent and nested reads, DOCTYPE and I/O failure recovery, unsupported reset and retirement. The local two-bundle run used the headless harness and temporarily omitted the binary PDE feature requirement so the tests resolved the built core bundle; no POM changes are included.

Additional full-model validation loads 49 real `org.eclipse.ui` schemas plus 15 includes and compares their complete model serialization with the unmodified implementation. All models match. Five DOCTYPE forms are rejected, a valid schema loads after each rejection, and malformed XML is rejected.

Related context: #2535 and eclipse-platform/eclipse.platform.ui#4518. This change is independent of #2575 and does not claim to fix the already resolved schema-distribution issue.

Assisted-by: OpenAI ChatGPT
