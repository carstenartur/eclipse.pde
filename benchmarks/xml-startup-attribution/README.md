# XML/schema correctness, handles and Eclipse startup

Study date: 2026-11-03. This branch contains two small, independently usable
repairs and an experiment. It does not change the reviewed text-coalescing PR.

**Follow-up:** [Actual extension-instance validation](instance-validation/README.md)
now covers 939 contributions in all 83 configured production XML descriptors.
It records schema/runtime inconsistencies, targeted schema patches, and actual
missing production resources whose repeated-load diagnostic drops from 25
attempts to one after authentic resource restoration. These findings extend
the original schema-only checks below; they are not new startup timing data.

## Findings

- A malformed or incompletely loadable schema can be parsed repeatedly even
  though its descriptor retains the same Schema object. The real-source probe
  opens a valid input once, but each invalid input 25 times for 24 subsequent
  model queries. This is a synthetic mechanism demonstration, not a production
  startup measurement.
- `StorageSchemaDescriptor` really opened `IStorage.getContents()` twice. The
  one-line repair uses the already opened stream. Two regression tests fail on
  the baseline; all three pass with the repair. Both original streams closed in
  this JDK's tests, so the observation is a redundant open, not a demonstrated
  leak or startup improvement.
- A documentation example in `targetLocationProvisioners.exsd` lacked an escaped
  closing `>`. The containing EXSD was already well formed. Repairing that
  example is not an explanation for slow schema loading.
- The reference contains 298 production schemas from 57 providers, including
  Platform, Equinox, JDT, PDE and EMF. All are well formed, all local/schema
  includes resolve, and the selected PDE SchemaBuilder reports no markers.
  This does not validate every extension contribution or reproduce the user's
  unspecified errors, installation or workspace.
- Twelve real-source file/JAR lifetime cases, with 16,896 operations and positive
  controls, found no retained fixture handles after an operation. No forced GC
  was used. This applies to the exercised Linux/JDK 25 paths.
- The 20 valid GUI comparison runs do not establish a reliable startup gain.
  The handler-only validation point estimates are lower, but every descriptive
  savings interval includes zero. Do not assign guaranteed percentages or
  seconds saved to these measures from this experiment.

## Reference and corpus

The reference is an assembled Eclipse IDE, not an untouched SDK distribution.
Its Equinox configuration contains 243 bundles including 50 matching source
bundles. PDE Core is `3.21.400.v20260810-0751`; the original `Schema.java` and
`XMLDefaultHandler.java` in its official source artifact are byte-identical to
the sources at the PR's baseline `ba6a5d6f2f455ab7dfe972ce678d07d9f80de267`.
JDK: Temurin 25.0.5+8; Linux x86_64; nine visible CPUs. Heap settings are
`-Xms256m -Xmx1024m`. An isolated authenticated Xvfb supplies the actual SWT
display. Exact bundle versions, hashes and configuration are in `results/`.

The corpus includes 39 binary-package schemas and 259 schemas from matching
source packages: 298 EXSD files, 2,337,930 uncompressed bytes. Both JAR bundles
and unpacked directory bundles are inventoried. Resources under production
`schema/` roots include reusable schemas even when they are not extension-point
declarations. Test/template resources are not turned into production fixes.

Of 293 declared schema paths, two are absent even from the matching source
artifacts:

| Provider | Missing resource |
| --- | --- |
| `org.eclipse.equinox.p2.repository.tools` | `schema/org.eclipse.equinox.p2.repository.tools.verifier.exsd` |
| `org.eclipse.ui.externaltools` | `schema/configurationDuplicationMaps.exsd` |

These are missing-resource findings, not malformed XML. No replacement schema
was invented. The corpus has no missing local/schema includes.

Each provider is represented by a disposable schema-only project retaining its
real bundle ID, manifest, extension descriptors, properties and schema bytes.
The project has Java/PDE natures and only the SchemaBuilder. Automatic building
is disabled during preparation; schema-document generation is disabled equally
in all cells. This workspace is a controlled validation fixture, not a full
source checkout or the user's usual startup configuration.

## Four-cell experiment

| Cell | Handler H | Formatting W |
| --- | --- | --- |
| H0W0 | baseline source | original inputs |
| H1W0 | PR #2575 at `de6efde7becdbcc5515c0a45c908d2592ccd465e` | original inputs |
| H0W1 | baseline source | tabs for structural EXSD indentation |
| H1W1 | PR handler | tabs for structural EXSD indentation |

The formatting tool replaces groups of three indentation spaces with tabs in
supported whitespace-only structural content. It retains attribute values,
documentation, examples, comments, CDATA, processing instructions, mixed
content, unknown/prefixed elements and `xml:space="preserve"` subtrees.
It changes all 298 corpus files, reducing their uncompressed size from
2,337,930 to 2,153,712 bytes: **184,218 bytes, or 7.88%**. It is not a general
XML minifier, nor a claim that all XML whitespace is insignificant.

The same set of schema/Core archives is rebuilt and signature entries are
removed in every cell, including controls. Other artifacts are untouched
symlinks. No shared Maven-cache artifact is edited. The two source handlers
are compiled with the same JDK. The separate storage-stream and documentation
repairs are not silently combined with H or W.

Five randomized matched blocks launch a new JVM for each of the four cells
(seed 20261103). Each run restores its cell's prepared workspace and Equinox
configuration at the same absolute paths. Seeds follow a full warmup validation,
so these are prepared restarts with warm OS caches, not cold installation starts.
The primary timing cells use identical observers, with FD scans and parser
instrumentation disabled.

Endpoints:

1. **Workbench ready:** JVM uptime when an SWT dispatch sees a visible workbench
   window with `isStarting() == false`. `applicationRunning` is recorded too;
   the observer immediately schedules a check and retains a 100 ms fallback.
   Native-launcher time is outside this endpoint.
2. **Explicit schema validation:** after workbench readiness, run a full
   `org.eclipse.pde.SchemaBuilder` build for all 57 projects. The measured build
   interval is separate from startup, marker collection and the quiet window.
3. **Settled:** the completed workload and relevant Jobs remain quiet for one
   second. This endpoint includes the confirmation window and is not presented
   as the pure parsing time.

The runner checks the exact project list and schema count, process exit, atomic
phase results, visible window, failed Jobs and Eclipse error-log entries.
CPU time is process-wide and can exceed wall time on multiple CPUs; it is not
exclusive parser CPU. Missing CPU counters are explicitly invalid.

## Valid GUI results

Twenty of twenty primary runs passed all gates. Every run processed the same
298 input candidates and reported zero error, warning and information markers.
Each cell has five observations. Values below are **means**, with observed
minimum and maximum in parentheses, rounded to milliseconds.

| Cell | Workbench ready, ms | Explicit SchemaBuilder, ms |
| --- | ---: | ---: |
| H0W0 | 4,440 (4,073–4,835) | 1,605 (1,241–2,118) |
| H1W0 | 4,271 (4,054–4,588) | 1,296 (1,172–1,447) |
| H0W1 | 4,480 (4,203–4,681) | 1,453 (1,171–1,685) |
| H1W1 | 4,527 (4,196–5,025) | 1,435 (1,352–1,498) |

The block-paired savings estimates, positive when faster, are:

| Endpoint | Change | Mean savings, ms | Descriptive 95% t interval, ms |
| --- | --- | ---: | ---: |
| Workbench ready | H only | +170 | −192 to +532 |
| Workbench ready | W only | −40 | −295 to +215 |
| Workbench ready | H + W | −86 | −258 to +86 |
| Explicit validation | H only | +310 | −231 to +851 |
| Explicit validation | W only | +152 | −443 to +748 |
| Explicit validation | H + W | +171 | −304 to +646 |

Every interval includes zero. These exploratory intervals use five paired block
differences, Student-t df=4, and no multiple-comparison adjustment. They neither
prove absence of an effect nor establish a transferable speed guarantee.
Interactions are reported in `analysis.json`; individual point estimates must
not be forced into percentages of an alleged overall saving.

The separate diagnostic JVM observed **350 full handler passes and 350 successful
Schema model loads for 298 distinct schema URLs**, all after the explicit
validation began. No abbreviated handler passes, handler starts or completed
Schema loads were observed before workbench readiness. Includes cause additional
model loads. These counters do not count all XML parsers: the builder has a
separate validation/DOM path too. The finding is specific to this prepared
workspace with automatic building off.

## Errors and file handles

`run_schema_failure_probe.py` compiles actual baseline `Schema`/handler sources
against real SDK dependencies. With the same retained descriptor and 24 model
queries, both full and abbreviated modes give:

| Synthetic input | Stream opens | Loaded |
| --- | ---: | --- |
| Valid minimal schema | 1 | true |
| Malformed XML | 25 | false |
| Element declaration without a name | 25 | false |

This confirms a way in which a real correction could eliminate repeated work.
It does not imply that all validation warnings trigger retries, or establish
which production input in the user's workspace does so.

`schema_handle_verify.py` uses actual baseline `Schema`, `SchemaDescriptor`,
`SchemaUtil` and `XMLDefaultHandler`. Twelve fresh JVMs cover file/JAR URLs,
the three inputs, both loading modes, cached queries and fresh descriptors.
The positive controls detect an intentionally open real handle and its closure.
Across 16,896 operations, the maximum fixture-handle count after an operation
is zero. After warmup the MXBean descriptor count remains 306 at every round
boundary; target differences are empty. No GC was requested. Classpath harness
handles are not comparable to the count in a full OSGi IDE.

There is a relevant historical issue: official Eclipse 3.6.2 release notes list
[Bug 326263](https://bugs.eclipse.org/bugs/show_bug.cgi?id=326263),
“Windows File Locks are obtained on bundles exporting extension points and not
released.” See the [maintenance-fix list](https://eclipse.dev/eclipse/development/readme_eclipse_3.6.2.html).
The current `SchemaUtil` still cites it, disables `JarURLConnection` caching,
and requires the JarFile itself to be closed. The historical fix is not proof
of a current leak or several seconds of current startup cost.

The optional full-IDE FD snapshots retained no `.exsd` targets at the settled
endpoint. Their original absolute totals include two scanner-directory entries
because this environment exposes different PID namespaces through ProcessHandle
and `/proc`. The scanner's self-filter was corrected after measurements using
the canonical `/proc/self/fd` path; a stronger real-FD test fails before the
correction and passes afterward. Target-specific lifetime results and primary
timings are unaffected; FD diagnostics were off in all primary cells. The exact
original primary probe JAR is retained in the raw-run archive.

## Data quality and verification

The preliminary environment produced SVG/AWT failures because `libXtst.so.6`
was missing. All of those series are excluded in their entirety, with raw logs
retained, not selectively filtered for favorable times. The library was added
only in the isolated native search path. A full 57-project control run then had
zero Eclipse errors before the valid matrix was launched. Exact package and ELF
hashes are in `native-library-fix.json`.

After the 20 valid timing runs, a transient directory-copy failure interrupted
preparation of the final diagnostic JVM. Retrying only the diagnostic copy/run
completed it; no primary timing was replaced. The runner now preserves the
original schedule when resuming with zero timing blocks. The archive contains
the exact primary-runner source matching its recorded hash.

Verification includes the three production stream regression tests; six targeted
formatting tests; quiet-window, output-contract and real-FD probe checks; corpus
hash/byte consistency; all 20 real IDE runs; and an independent recalculation of
all 36 reported contrasts. The full Tycho test suite for the new small repairs
has not run here. An SDK dependency's manifest produces one javac Class-Path
warning when rebuilding the observer; compilation and its targeted checks pass.

## Reproduce and inspect

Use a disposable copy of an Eclipse installation with its matching source
bundles, the recorded JDK, and a working display. The observer closes the tested
workbench after recording the result. See [probe/README.md](probe/README.md) for
building/installing the observer, preparing projects and running individual
startup or validation scenarios.

```bash
python3 probe/prepare_schema_corpus.py \
  --eclipse-home /absolute/reference-eclipse \
  --output-directory /absolute/new-corpus

python3 prepare_variants.py \
  --reference-install /absolute/reference-eclipse \
  --corpus /absolute/new-corpus \
  --java-home /absolute/jdk \
  --probe-jar /absolute/probe.jar \
  --output-directory /absolute/new-experiment

python3 run_matrix.py \
  --experiment /absolute/new-experiment \
  --launcher /absolute/launcher.jar \
  --java-home /absolute/jdk --blocks 5

python3 analyze_results.py /absolute/new-experiment \
  --output /absolute/analysis.json
```

Pass `--xvfb-wrapper` when a display wrapper is required; omit it with an existing
usable display. The pinned baseline and PR commits must be available in the Git
object database. Timings on another installation/machine are new observations,
not expected to reproduce these exact milliseconds.

Principal records:

- `results/analysis.json`: cell summaries, paired effects, intervals and counters.
- `results/run-results.json`: every warmup, primary and diagnostic run.
- `results/experiment-manifest.json`: source/classes, bundles and full corpus.
- `results/primary-and-diagnostic-runs.tar.xz`: unedited logs/results and exact
  primary observer/runner artifacts.
- `results/excluded-runs.json` and `results/excluded-environment-runs.tar.xz`:
  excluded environment runs, reasons and original logs.
- `schema_handle-results.json` / `schema_handle-audit.json`: lifecycle observations
  and checked close paths.
- `storage_stream-results.json`: identical-test baseline/fixed comparison.
- `audit-results.json`: the narrower production-PDE source audit and the decoded
  documentation-example repair.

To measure correctness repairs as another factor, first supply a concrete
reproducible production diagnostic/file and preserve validation settings and
successful work on both sides. This corpus does not justify inventing such an
error-fix factor or calling the documentation repair a startup optimization.
