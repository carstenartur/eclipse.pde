# PDE schema loading: implementation follow-up

Measured on 24 October 2026. These experiments execute real PDE schema-model construction. They are not measurements of a complete Eclipse startup.

## Changes and decisions

- [Parser reuse](https://github.com/carstenartur/eclipse.pde/tree/e379f66f954717c8f922f8321d4c09b96611b482): retain one idle, reset parser, checked out exclusively; discard failures and unsupported resets; retire after 100 successful reads to limit accumulated provider state. Production still uses Eclipse's secure XML factory. Independent source review and all eight lifecycle tests pass.
- [Empty documentation](https://github.com/carstenartur/eclipse.pde/tree/9cfd160392a6e49dd2ce2fa689cacc5957611ed4): fix a separate null dereference on valid empty overview, named-section and element documentation. Four regression tests pass. It is not included in the measured performance implementations.
- [Sandbox PR #1742](https://github.com/carstenartur/sandbox/pull/1742): preserve meaningful whitespace before applying cleanup to real descriptors. All seven selected Maven/Tycho modules pass.
- Woodstox remains an isolated experiment. Its first single-schema access costs more CPU/classes/allocation and its bundles are absent from the selected target. No production provider switch is proposed.
- The corrected formatter was applied to and built with 49 workbench schemas, but the 16,537-line source diff is not proposed upstream: the indented version saves only 2,223 compressed bytes (1.68%) in a matched schema-only ZIP. The experiment and patch are retained for inspection.

## Warm complete-model results

Each operation loads 49 `org.eclipse.ui` EXSD schemas from JAR entries, resolves 15 real include loads and constructs 229 top-level model elements. Three independent JVM forks per configuration; each has eight two-second warmup iterations followed by six one-second measurements. Configuration order rotates between rounds. Values below are means of the three fork means; the CPU range shows the actual fork variation, not a confidence interval.

| Implementation / files | CPU ms per batch | CPU fork range | Allocated MB per batch |
|---|---:|---:|---:|
| Upstream | 15.883 | 14.775–17.666 | 27.998 |
| Parser reuse | 15.080 | 14.384–16.418 | 25.803 |
| Text coalescing (PR #2575) | 13.560 | 12.549–14.906 | 8.186 |
| Coalescing + reuse | 12.020 | 10.797–13.589 | 5.991 |
| Combined + safe indented files | 11.115 | 10.740–11.811 | 5.909 |
| Combined + safe compact files | 10.453 | 10.172–10.841 | 5.268 |
| Coalescing + fresh Woodstox | 8.991 | 8.694–9.454 | 6.077 |

Parser reuse alone reduces mean CPU by **5.1%** and allocation by **7.8%** against upstream. Added to text coalescing, it reduces the observed mean CPU by **11.4%** and allocation by **26.8%**. Combined, the changes reduce CPU by **24.3%** and allocation by **78.6%** against upstream in this workload. Three forks on a shared VM do not establish a universal CPU percentage; fork ranges overlap. The approximately 2.2 MB allocation reduction from parser reuse is consistent across implementations.

The indented cleanup adds an observed 7.5% CPU / 1.4% allocation reduction to the combined implementation; compact output adds 13.0% / 12.1%. Neither cleaned-file variant was measured during a first-use or full-IDE-start scenario. Source readability, editor-generated layout and diff size remain costs of a source-only formatting PR.

## First batch in a fresh JVM

Twenty trials per implementation, rotating the order of upstream, reuse and combined implementations; 60 JVM processes. Only URLs and measurement instruments are prepared before the first schema read. JVM process launch is outside the timer and the operating-system file cache is warm.

| Implementation | Median CPU | Median allocated bytes | Additional loaded classes |
|---|---:|---:|---:|
| Upstream | 242.79 ms | 34.41 MB | 322 |
| Reuse | 236.00 ms | 32.06 MB | 330 |
| Coalescing + reuse | 220.44 ms | 12.11 MB | 330 |

For reuse alone, the median paired CPU difference is −7.09 ms, with a bootstrap 95% interval of **−18.67 to +4.72 ms**; it is faster in 12/20 pairs. A first-batch CPU benefit from reuse alone is **not established**. For the combined implementation, the median paired difference is −24.85 ms, interval **−39.13 to −17.79 ms**, and 19/20 pairs are faster. This comparison includes the existing coalescing PR and must not be attributed to parser reuse alone.

The separate Woodstox first-use study uses 20 alternating JDK/Woodstox pairs per case. Its first `views.exsd` and `menus.exsd` reads cost approximately **37 ms and 35 ms additional CPU**, respectively, with 133 additional classes and about 2.1 MB additional allocation on the first single-schema read. The first complete-batch interval crosses zero. See [Woodstox evaluation](WOODSTOX.md) and its raw cold data. Warm Woodstox uses about 8.99 ms CPU per batch, but that does not make it a default startup optimization.

## Safety and validation

| Check | Result |
|---|---|
| PDE parser lifecycle tests in actual local-core Tycho runtime | 8 tests, no failures/errors |
| PDE empty-documentation regression tests in actual local-core Tycho runtime | 4 tests, no failures/errors; 3 original-source failures demonstrated |
| Sandbox selected seven-module Maven/Tycho reactor | Success; 1,336 shared-core and 51 test-commons tests; XML: 103 tests, 0 failures/errors, 2 existing optional corpus skips |
| Sandbox helper and real corpus | 76 checks passed; both modes idempotent on all 50 files |
| Protected content | All 1,066 documentation elements, including 45 whitespace-only leaves, plus appinfo and extension payloads retain their parsed content |
| Actual PDE models | 49 serialization hashes identical across all five implementations and all three file variants, including 15 include loads per corpus |
| XML errors | Five DOCTYPE forms rejected, valid recovery after each, malformed XML rejected |
| Workbench bundle packaging | Focused `org.eclipse.ui` `clean verify` succeeds; all 49 packaged schemas byte-match the final indented corpus |

The PDE focused tests built `org.eclipse.pde.core` and `org.eclipse.pde.ui.tests` together. For this local two-bundle run the test POM temporarily selected the headless harness and omitted the binary PDE feature extra requirement; otherwise that feature pins an old remote core and shadows the newly built classes. The committed POMs are unchanged. Sandbox used a TCP-only Xvfb display because the environment does not expose X11 Unix sockets. Full project CI is a separate gate; these are focused local runs.

The safe formatter passes the full model comparison against unmodified PDE, including its existing empty-documentation behavior. It therefore does not rely on the separate null-handling fix to conceal changed content.

## Corpus and source provenance

- PDE upstream: `feabce4240a1268adcb8d26733a02d028eadea02`.
- Text coalescing: `081876347068847fff2f06e11f8a945a393d0a79`, [PR #2575](https://github.com/eclipse-pde/eclipse.pde/pull/2575).
- Reuse source: local `873bde74ae7d955014b42e2565c2a9fe8e516c74`; published single-commit tree `e379f66f954717c8f922f8321d4c09b96611b482`. Both have tree `6cbcfee2951a0b334e0e16d4052888e3aa1955b2`.
- Woodstox prototype: local `0353472`, Woodstox 7.3.0 and Stax2 API 4.3.2. The two dependency JARs total 1,822,244 bytes (1.74 MiB).
- Workbench corpus: eclipse-platform/eclipse.platform.ui `1c2ae81706700d6744babb3db81d0a99cf4520ce`.
- Safe cleanup: Sandbox local `8c32b87bf2b61906a5a622f6609fbdaf7bd9c427`; published `fd3ba813cb12093891eb61f2fc4eb8134ea48f36`, identical tree `993b017bdfeb16ff1c32e03004ffe342b90f5c6b`.
- Include files: actual core-expressions and relative workbench schemas, recorded in the reproduction bundle.

The corpus directories and measurement JARs retain the earlier 50-file layout: `plugin.xml` plus 49 schemas. Only the 49 schemas are timed. `schema-sizes.json` separately reports a matched ZIP containing just those 49 files: original 617,841 XML / 132,358 ZIP bytes; indented 563,380 / 130,135; compact 534,827 / 127,999. The candidate source patch deliberately leaves `plugin.xml` unchanged.

## Measurement and reproduction

OpenJDK 25.0.4, JMH 1.37, Linux shared VM, CPU affinity 0, one benchmark thread, `-Xms512m -Xmx512m -XX:+UseSerialGC -XX:ActiveProcessorCount=1`. No other agent builds or benchmarks ran during the timed series. Thread CPU and allocation counters cover the calling thread; they exclude GC/JIT worker CPU and are not retained-heap measurements. Wall time was also recorded, but CPU and allocation are the primary comparisons.

The driver calls real `SchemaDescriptor.getSchema(false)` / `Schema.load()` and supplies include resolution through the existing `SchemaProvider` interface. Schema target version is set to 3.4 only after loading for deterministic model serialization, outside timing. The abbreviated registry path and the OSGi bundle-start cost are not measured. Implementations are selected by classpath, without changing a process-wide JAXP provider property.

JMH `AuxCounters(EVENTS)` reports a summed `score` for these getter values; `summarize.py` uses the iteration `rawData` and computes means per independent fork. Treating the summed score as per-operation CPU or allocation would be incorrect. Raw JSON, logs, cold CSV and deterministic bootstrap summary are provided alongside this report.

Download [archive part 1](reproduction.zip.part1), [archive part 2](reproduction.zip.part2) and [the assembly script](assemble-reproduction.py) into one directory, using GitHub's **Download raw file** action to preserve their bytes. Run `python3 assemble-reproduction.py` to create the self-contained `reproduction.zip`; the script verifies each part and the complete archive against the [recorded sizes and SHA-256 hashes](archive-parts.json). The ZIP contains the exact dependency JARs, support-class snapshot, source variants, corpus, notices and a relative-path offline runner. Extract it into a new directory, then, with JDK 25, run `python3 reproduce.py build --implementation all` and `python3 reproduce.py validate --implementation all --corpus all` there. The packaged runner was freshly compiled and all 735 model comparisons passed before publication. See [the reproduction instructions](REPRODUCE.md) for extraction, JMH and fresh-JVM commands.

## Correction to earlier compact-corpus evidence

The earlier DOM/handler benchmark remains evidence about the handler's original-file path. Its optional compact corpus was produced by the old global-whitespace cleanup. That cleanup changes whitespace-only documentation to `<documentation/>`, which exposed PDE's null dereference during full model construction. DOM-only comparisons did not exercise that model path. **Do not deploy or use that earlier compact corpus as a safe Eclipse optimization.** This report uses newly generated, content-preserving variants and validates complete models before timing. The original-file coalescing result is independent of that cleanup defect.

Related discussion: [PDE #2535](https://github.com/eclipse-pde/eclipse.pde/issues/2535), [workbench #4518](https://github.com/eclipse-platform/eclipse.platform.ui/pull/4518), and the historical parser-cache removal in [PDE #632](https://github.com/eclipse-pde/eclipse.pde/pull/632). The schema-distribution issue is already resolved; the performance proposals do not claim to fix it again.

Assisted-by: OpenAI ChatGPT
