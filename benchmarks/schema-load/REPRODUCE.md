# PDE XML follow-up: standalone reproduction

This is evidence for a performance investigation, not a new PDE test framework. It runs the actual PDE `SchemaDescriptor` → `Schema.load` → DOM → schema-model path, including referenced schemas. It does not launch the IDE or measure OSGi bundle activation.

Use the **complete companion reproduction archive** for a faithful offline rerun. It is published as [part 1](reproduction.zip.part1) (7,500,000 bytes) and [part 2](reproduction.zip.part2) (7,867,548 bytes). Save both parts and [assemble-reproduction.py](assemble-reproduction.py) into one directory using GitHub's **Download raw file** action. The script checks each part and the complete ZIP against fixed SHA-256 hashes; [archive-parts.json](archive-parts.json) also records sizes, hashes and GitHub blob IDs.

```bash
python3 assemble-reproduction.py
python3 -m zipfile -e reproduction.zip reproduction
cd reproduction
```

The assembled ZIP is 15,367,548 bytes, with SHA-256 `9c558850d36959a7ed899dcdcf2375ae58a612aee60b550b744869e98cc12355`. Source files viewed separately in Git omit the binary dependency directories; the split archive includes the exact support-class snapshot and dependency JARs named in `SHA256SUMS`. `DEPENDENCIES.md` records their public origins; Eclipse integration-build download URLs may expire, so downloading newer replacements is not equivalent to using this archive.

Requirements: Python 3.9+ and **JDK 25**, selected by `JAVA_HOME`. No Maven, network connection, IDE installation or external Python package is needed after obtaining the complete ZIP. Linux permits optional CPU pinning; omit `--cpu` on other systems. Use an otherwise idle machine for timing.

```bash
export JAVA_HOME=/path/to/jdk-25
python3 reproduce.py verify
python3 reproduce.py build
python3 reproduce.py validate
```

`validate` runs all five implementations against all three corpus variants and checks equality of all 49 model serializations per case, plus the fixed mixed-content, DOCTYPE-rejection/recovery and malformed-XML fixtures. Results go to `reproduced-results/`; packaged recorded results remain separate.

| Implementation | Handler | Schema parser |
|---|---|---|
| `upstream` | Upstream text handling | Fresh JDK parser |
| `reuse` | Upstream text handling | Exclusive bounded parser reuse |
| `coalesced` | Coalesced text handling | Fresh JDK parser |
| `combined` | Coalesced text handling | Exclusive bounded parser reuse |
| `woodstox` | Coalesced text handling | Fresh locally selected Woodstox parser |

The corpora are `original`, `safe-indented` and `safe-compact`. Each directory contains 49 schemas and `plugin.xml`; this benchmark reads the 49 schemas, plus 15 required includes. It reads each corpus through its accompanying JAR. The corrected whitespace transformation preserves model contents across all three variants. The older unsafe compact corpus is intentionally absent.

Run one selected JMH case:

```bash
python3 reproduce.py --cpu 0 jmh --implementation coalesced --corpus original
python3 reproduce.py --cpu 0 jmh --implementation woodstox --corpus original
python3 reproduce.py --cpu 0 jmh --implementation combined --corpus safe-compact
```

Choose a CPU available on your machine. Defaults match the final comparison: 8 × 2 s warm-up, 6 × 1 s measurement, 3 forks, one thread, a 512 MiB heap, Serial GC and one active processor. JMH JSON and its full console log are written to `reproduced-results/<implementation>-<corpus>.*`. Options such as `--forks 1` and `--iterations 2` are available for smoke checks; those are not equivalent to the recorded performance run. Repeated comparisons should alternate or rotate implementation order. The recorded full series used the seven cases in the final report, rotating by two positions between forks and reversing the second round.

JMH's auxiliary counters contain per-operation CPU/allocation values in `secondaryMetrics.*.rawData`. In this configuration the secondary `score` sums them across iterations; calculate means from `rawData`, rather than interpreting `score` as milliseconds per operation. Primary wall-time metrics use the ordinary JMH convention.

Fresh-JVM first use is a separate mode:

```bash
python3 reproduce.py --cpu 0 first --implementation all --case views.exsd --trials 20
python3 reproduce.py --cpu 0 first --implementation woodstox --case all --trials 20
```

Each sample starts a fresh JVM. Timing excludes JVM process startup and URL preparation but includes first schema/model/provider use. It uses the operating-system file cache; it is not a cold-disk measurement. Selecting `all` rotates the five implementations between trials. CSVs include wall time, main-thread CPU, allocated bytes, class-loading count and model/include counts.

`lib/pde/pde-core-benchmark-snapshot.jar` archives the exact stable PDE support classes used for the investigation. `build` extracts its 674 files into a class directory, matching the recorded runtime layout, then compiles the selected source overlays ahead of it on the classpath. The corresponding PDE source JAR and class-file inventory are included. Source variants and all inputs are pinned in `provenance/`; there are no embedded machine-specific paths or credentials.

`experiments/platform-schema-cleanup.patch` is a data-transformation experiment for the platform schema corpus. It is **not a proposed upstream source-cleanup PR**. The Woodstox source is also an evaluation prototype; the production target-platform dependency change has not been completed.

The package preserves original copyright and license notices. See `LICENSES.md`, `licenses/` and the unchanged dependency JARs. The generated standalone driver is provided under EPL-2.0.

When adding final reports or recorded results before archiving, refresh the package manifest with `python3 reproduce.py manifest`, then run `python3 reproduce.py verify`. Generated `build/` and `reproduced-results/` files are intentionally excluded from the manifest and need not be distributed.
