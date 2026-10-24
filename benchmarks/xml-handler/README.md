# PDE XML text coalescing benchmark

> **Follow-up correction (24 October 2026):** the optional compact corpus below used the old cleanup, which removed whitespace-only documentation. Full PDE-model validation subsequently exposed a null dereference on the resulting empty documentation. Do not deploy that compact corpus. The original-file handler result is independent of the cleanup. See the [complete-model follow-up](../schema-load/README.md) for the corrected formatter, parser-reuse measurements, first-use results and reproduction bundle.

This branch publishes the measurement harness separately from the production pull request. The production change introduces no JMH, parser or other library dependency.

## Recorded result

CPU time per pass over all 49 `org.eclipse.ui` EXSD schemas, opened from an XML-only JAR. These are thread CPU times, not Eclipse startup times.

| Mode | Files | Before CPU | After CPU | CPU reduction | Before allocation | After allocation | Allocation reduction |
|---|---|---:|---:|---:|---:|---:|---:|
| full | original | 14.317 ms | 10.871 ms | 24.1% | 22.052 MiB | 5.231 MiB | 76.3% |
| full | compact | 12.392 ms | 9.421 ms | 24.0% | 17.786 MiB | 4.508 MiB | 74.7% |
| abbreviated | original | 8.733 ms | 8.773 ms | -0.5% | 3.990 MiB | 3.990 MiB | -0.0% |
| abbreviated | compact | 7.857 ms | 8.128 ms | -3.5% | 3.959 MiB | 3.959 MiB | 0.0% |

The **original-files** result measures the patch alone: 24.1% less CPU and 76.3% fewer allocated bytes in full mode. The compact variant is a separate combination experiment, using the existing sandbox XML cleanup. No XML-file changes are part of the PDE pull request.

The paired 95% intervals for full-mode CPU savings are 3.007–3.884 ms on original files and 2.358–3.582 ms on compact files. The abbreviated-mode intervals include zero; no speedup or equivalence claim is made for that path. Its character callbacks already skip text. Negative percentages in the table indicate a higher observed mean.

## Reproduce

Requirements: JDK 25, Python 3, network access to pinned GitHub sources and Maven Central. The branch contains the measured production patch. From its repository root:

```sh
export JAVA_HOME=/path/to/jdk-25
python3 benchmarks/xml-handler/run.py
# Optional on Linux, choose an available CPU:
python3 benchmarks/xml-handler/run.py --cpu 2
```

Use `--prepare-only` to download, verify, compile and check the inputs without running the benchmark. An explicit `--repo /path/to/pde` can point to the measured production checkout. Every downloaded input is pinned by URL and SHA-256 in `inputs.json`; the patch itself and all generated compact XML files are also hash-checked. Original sources retain their licenses. Dependencies are downloaded into ignored `target/`, not committed.

Fresh results appear in `target/results/jmh.json`, `jmh.log` and `summary.json`. The checked-in measurements remain in [recorded-results](recorded-results). The script performs the same 50-file cleanup content/idempotence checks and the benchmark verifies exact DOM equality before timing each fork.

## Method

- Baseline PDE commit: `feabce4240a1268adcb8d26733a02d028eadea02`. The old handler is mechanically renamed `BaselineXMLDefaultHandler` so both implementations can run in the same JVM. The proposed handler is compiled directly from the production checkout.
- Corpus: `bundles/org.eclipse.ui` at eclipse-platform/eclipse.platform.ui commit `1c2ae81706700d6744babb3db81d0a99cf4520ce`. The archive also contains plugin.xml to reproduce the previous corpus layout; timed processing uses the 49 EXSD files only.
- Unmodified XmlProcessorFactory from eclipse-platform/eclipse.platform commit `119d38bd6b19b4b455359f404dc2746160b0189a`. The same JDK SAX provider, parser creation policy, DOM provider and security settings are used for both handlers.
- Cleanup sources: carstenartur/sandbox commit `8c6b6ea67f691318e9ce36be74ca881da6e6d9fc`, with indentation disabled. They only prepare the optional compact corpus and never run inside a timed operation.
- OpenJDK 25.0.4 (Ubuntu), JMH 1.37, Linux on AMD EPYC 9V74, fixed CPU affinity 2. This was a shared VM; a Maven dependency-resolution/build process also ran during the experiment.
- Three fresh JVM forks for each of two modes, four 2-second warmup iterations and six 1-second measurement iterations. One thread, 512 MiB heap, Serial GC, ActiveProcessorCount=1.
- Each benchmark operation processes baseline/original, baseline/compact, patched/original and patched/compact. Position rotates and direction alternates across operations.
- Every document opens a new JarURLConnection with useCaches=false; both the stream and JarFile are closed. OS cache and JVM classes are warm.
- Thread CPU and allocated bytes are measured once per 49-file corpus. Other threads (including JIT and GC) are excluded from CPU; allocation is cumulative bytes, not retained heap.
- JMH AuxCounters getters return already-normalized values. **Do not use the aggregate EVENTS score**, which sums iteration values. `summarize.py` averages rawData within forks and then across forks. Intervals use paired fork differences and Student-t with two degrees of freedom; they are exploratory and not corrected for multiple comparisons.
- The final DOM is normalized through the same public getter in both implementations. Each fork performs 98 exact DOM comparisons for its mode before timing.

## Limits and validation

This isolates XML reading and DOM construction/normalization. It does not measure complete Eclipse startup, schema model traversal, include resolution, persistent registry-cache hits, or bundle activation. Six standalone JUnit tests pass before and after the production change; a negative control removing a necessary flush is detected. The patched tests also pass in the actual Tycho/OSGi runtime when run without the UI harness. The normal UI harness cannot start in the execution environment because Xvfb cannot establish local listening sockets; no UI-harness change is included in the production branch.

The production tests are registered in AllPDECoreTests, which is selected by AllPDETests. The existing SchemaLoaderPerfTest remains available for a broader in-Eclipse schema-loading comparison; this document does not claim that broader test has been measured.
