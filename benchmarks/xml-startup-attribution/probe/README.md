# Real Eclipse startup measurement probe

This is an experiment-only OSGi bundle. It compiles against the actual bundles
in an Eclipse installation. It does not change the production PDE implementation.
Install the identical probe in every measured variant.

## Build and install

Use the same JDK that runs the reference IDE (JDK 21 or newer):

```bash
python3 build_probe.py /absolute/path/to/eclipse \
  --javac /absolute/path/to/jdk/bin/javac
```

The script verifies that the real Eclipse/SWT API classes are present, compiles
the Java sources, runs the quiet-period and output-contract checks, and creates
`build/org.eclipse.pde.xmlstudy.probe_1.0.0.jar`. It prints the absolute path and
SHA-256. It does not download dependencies or modify the installation.

Copy that JAR to the installation's `plugins/` directory. With the Equinox simple
configurator, add this line to the fixture's
`configuration/org.eclipse.equinox.simpleconfigurator/bundles.info`:

```text
org.eclipse.pde.xmlstudy.probe,1.0.0,plugins/org.eclipse.pde.xmlstudy.probe_1.0.0.jar,4,true
```

The bundle must start before the IDE application; it is deliberately eager.
An extension-only or late start can miss `StartupMonitor.applicationRunning()`.
An installation that uses `osgi.bundles` directly instead of the simple
configurator needs the equivalent `@4:start` entry there. Do not configure both.

## Launch interface

Keep the ordinary application `org.eclipse.ui.ide.workbench`. For a direct Java
launcher, JVM properties go before `-jar`; for the native Eclipse launcher they
go after `-vmargs`.

```bash
/absolute/path/to/jdk/bin/java \
  -Dxml.study.runId=example-startup \
  -Dxml.study.output=/absolute/path/to/results/example-startup.json \
  -jar /absolute/path/to/org.eclipse.equinox.launcher.jar \
  -nosplash \
  -application org.eclipse.ui.ide.workbench \
  -configuration /absolute/path/to/eclipse/configuration \
  -data /absolute/path/to/disposable-workspace
```

Use the display, GTK, heap, product and target-platform settings defined by the
study runner. This probe does not choose them. In particular, it never adds
`-clean`, changes the target, imports projects, opens editors, or triggers a
build during the default scenario.

| JVM property | Meaning |
| --- | --- |
| `xml.study.scenario=startup` | Default: observe the real startup and its background Jobs. |
| `xml.study.scenario=validation` | After `workbench_ready`, explicitly run the PDE schema builder; all subsequent workload records are labeled `post-start validation`. |
| `xml.study.projects=project.one,project.two` | Optional selection for the explicit validation scenario. Otherwise select all open PDE projects that have the schema builder in their build specification. |
| `xml.study.output=/absolute/result.json` | Optional final JSON file, written before the close request. Stdout phase records are always produced. |
| `xml.study.runId=identifier` | Copied into every phase and the final result. |
| `xml.study.fdDiagnostics=true` | Optional Linux open-file/JAR diagnostic snapshots at each phase. Disabled by default; use separate diagnostic runs. |
| `xml.study.enabled=false` | Disable the observer, for preparation only. |

### Optional workspace preparation

The headless application `org.eclipse.pde.xmlstudy.probe.prepareWorkspace` reads
`-Dxml.study.projectList=/absolute/list.txt`. The UTF-8 list contains one absolute
project-directory path per line; each directory must contain its real `.project`.
Blank lines and lines beginning with `#` are ignored.

Run it with `-Dxml.study.enabled=false` and the fixture's `-data` directory.
It disables automatic building, imports and opens the listed projects, saves
the workspace, and prints `XML_STUDY_PREP {json}`. It fails on an empty list or a
conflicting existing project location. Use copies of the study inputs: Eclipse
project import/activation can persist metadata and project preferences.

This preparation has an explicit consequence: an unchanged normal restart of
that workspace need not validate any schemas. The separate validation scenario
exists for that case. Preparation is never included in the startup timing.

### Reference corpus from all available providers

`prepare_schema_corpus.py` creates the project directories consumed by the
preparation application:

```bash
python3 prepare_schema_corpus.py \
  --eclipse-home /absolute/path/to/reference-eclipse \
  --output-directory /absolute/path/to/new-schema-corpus
```

The output directory must be new or empty. It contains `projects/`,
`corpus-manifest.json`, and `project-list.txt`. The optional
`--source-directory /absolute/path/to/source-jars` supplements source JARs not yet
installed in `plugins/`; installed artifacts take precedence when the same file
is present in both places.

The utility scans both JAR bundles and unpacked bundle directories. It identifies
sources by their actual `Eclipse-SourceBundle` host/version header, requires an
exact binary-version match, and prefers original binary schema bytes whenever
both artifacts contain a resource. Source bundles can retain non-Java resources
in top-level `schema/` even when their `roots` header lists only Java source
roots; both the top-level resource location and declared source roots are
considered. A second installed schema-provider version with the same bundle ID
is an explicit error, not an implicit version choice.

All `.exsd` and `.mxsd` files under those production schema roots are retained,
including reusable or undeclared schemas. Schema-like files outside these roots,
such as templates or test data, are listed as filtered inputs. Every selected
file is checked for XML well-formedness; malformed production inputs are copied
unchanged and reported with their parse diagnostic. A missing schema declaration
is reported separately from a malformed file. No missing schema or declaration
is synthesized, and external includes are never fetched.

Each provider's project retains its original bundle ID, binary manifest,
`plugin.xml`/`fragment.xml`, and properties files. Its generated `.project`
contains Java/PDE natures and only `org.eclipse.pde.SchemaBuilder`; `.classpath`
contains only the `bin` output entry, with no Java source folders. A fixed
`.settings/org.eclipse.pde.prefs` disables schema documentation generation in
every variant, isolating the schema-validation scenario from HTML output work.
This is a deliberate fixture setting, not a statement about the user's workspace
preferences. Eclipse nature configuration may add builders during import; check
the imported build specification too. The explicit validation scenario always
names `SchemaBuilder` directly, and preparation keeps automatic building off.

The manifest records original artifact paths and hashes, the chosen resource
origin and archive entry, byte counts, SHA-256 for every copied schema and binary
metadata file, project mappings, source-version mismatches, declarations,
include-resolution results, and all syntax diagnostics. Directory artifacts use
the documented deterministic content-tree hash. A final pass verifies that
copied schema files match their hashes and byte counts. When copying this corpus
to a variant directory, generate a new project list for that destination instead
of using the original absolute paths.

## Phases and their meaning

Every phase is one stdout line with this exact prefix:

```text
XML_STUDY_PHASE {"phase":"workbench_ready", ...}
```

Each record includes `phase`, `scenario`, `runId`, `processId`, `jvmUptimeMs`, `processCpuNs`,
`probeElapsedMs`, `visibleWindows`, and a Job snapshot.

1. `probe_started`: the autostart bundle installed the listener and monitor.
2. `application_running`: Eclipse invoked `StartupMonitor.applicationRunning()`.
   This is not yet the workbench readiness endpoint.
3. `workbench_ready`: an asynchronous SWT dispatch observed at least one
   non-disposed, visible workbench shell and `isStarting() == false`. The first
   dispatch is queued immediately from `applicationRunning()`, not delayed to
   the periodic poll. A missing/not-yet-ready workbench is retried every 100 ms.
4. `validation_settled`: another UI dispatch confirmed at least one visible
   window, the Job condition below, and one complete second without observed
   Job activity. In the validation scenario the explicit workload must also
   have completed. This endpoint includes the one-second confirmation window.
5. `timeout` or `probe_error`: a terminal unsuccessful outcome instead of
   `validation_settled`. Preserve it as a failed run; do not use it as a faster
   sample.

The validation scenario adds `validation_started` and `validation_finished`
strictly after readiness. It calls the real resource API with `FULL_BUILD` and
builder `org.eclipse.pde.SchemaBuilder` for each selected project. It preserves
the workspace's PDE compiler/documentation preferences. Results identify the
selected projects, discovered `.exsd` files, the build interval, and existing
plus newly reported PDE marker counts on those schema files.
The marker report also includes every diagnostic's workspace schema path,
severity, message, line and marker type in deterministic order. This collection
occurs after the separately recorded `buildWallNs` interval. The later settled
endpoint includes the collection cost. Source compaction can move marker lines;
keep the full records while comparing the diagnostic meaning separately.

`schemaFiles` counts eligible input files discovered by the probe. It does **not**
count `Schema.load` calls, successful parses, or retries. A successful build
invocation can still report XML/schema markers. Examine the marker outcome and
use separate diagnostic instrumentation when parse counts are required.

### Job completion rule

All `RUNNING` and `WAITING` Eclipse Jobs block completion. `SLEEPING` Jobs also
block if their priority is `Job.BUILD`, their implementation belongs to
`org.eclipse.pde.*`, or they are `AutoBuildJob` implementations. This includes
delayed PDE/build work. Unrelated sleeping periodic jobs do not block forever.
Scheduling, running, completion, wakeup and sleep events reset the quiet clock.

The snapshot lists pending Jobs and per-kind event totals. Lists have explicit
truncation counts/flags; totals still cover all observed Jobs. The listener is
installed before startup, but jobs completed before probe activation are outside
its scope. No PDE model manager or registry is forced to initialize just to
classify a Job. Registering the listener initializes Eclipse's Job infrastructure
earlier than an entirely uninstrumented launch; this overhead is shared by all
variants and should be acknowledged.

The quiet check is retried every 100 ms, so the settled endpoint has up to one
poll interval of observation delay. Finite quiet does not prove that no future
delayed task will ever run. Jobs are not every JVM thread; asynchronous work
outside the Job framework, including some indexing, is not fully represented.
This is an operational PDE/startup-job endpoint, not a claim of global CPU idle.

## Timing, timeout and shutdown

`jvmUptimeMs` is the runtime's JVM uptime. It excludes native launcher work before
the VM starts. An external runner should record its own monotonic launch and
phase-reception timestamps for end-to-end wall time. `processCpuNs` uses the public
`com.sun.management.OperatingSystemMXBean.getProcessCpuTime()` API when supported,
with `ProcessHandle.Info.totalCpuDuration()` as a fallback. The selected API is
reported as `cpuCounter`. It includes all process threads; `-1` means unavailable.
The probe reflects on the public interface via the platform class loader, never
on an encapsulated implementation class. Nanosecond units do not imply nanosecond clock
resolution. `probeElapsedMs` starts at activator entry and is only a diagnostic
offset, not the overall startup duration.

The observation deadline is fixed at 60 seconds from activator entry. The probe
emits a terminal `timeout` and requests a workbench close if possible. It cannot
guarantee that a blocked UI thread dispatches a close request, so the external
runner **must also enforce a process timeout**. Use a small, separately recorded
shutdown allowance. Neither that allowance nor process-exit time is a startup
metric. A launch that never starts this bundle requires the external timeout too.

After either successful settlement or failure, the probe writes the final JSON
and queues `IWorkbench.close()` on the UI thread. State saving and shutdown occur
after the terminal measurement. A close veto prints `XML_STUDY_CLOSE_REJECTED`.
Failure to write the optional result file prints `XML_STUDY_OUTPUT_ERROR`; the
stdout observations remain available. An isolated, unsaved-editor-free fixture
avoids prompts during closure.

The visible-window check proves SWT visibility and a UI dispatch, not compositor
paint completion or measured keyboard responsiveness. The plugin does not assert
that any schemas were parsed on a normal restart. Allocation profiling and URI
parse/read counters belong in separately labeled diagnostic runs; the primary
probe adds no per-element or per-schema logging.

### Optional open-file/JAR diagnostics

With `xml.study.fdDiagnostics=true`, each phase additionally contains a
`fileDescriptors` snapshot from `/proc/self/fd`. It reports sorted descriptor
numbers and link targets, regular-file and `.jar`-suffix target groups, descriptor
counts, and unique target counts. Other descriptor types (pipes, sockets,
anonymous inodes, devices and directories) remain distinguishable. The scanner
reads links and file metadata, not file contents. A JAR classification is based
on the filename suffix; it does not inspect the archive contents.

The scanner's own `/proc/<pid>/fd` directory descriptors are excluded, and its
DirectoryStream is closed before the snapshot is returned or written. Capture
start/end uptime and scan duration expose the diagnostic cost. This is a
non-atomic snapshot: descriptors can close or open during enumeration; raced or
inaccessible entries are counted. A platform without accessible `/proc/self/fd`
gets `supported: false` and a reason, not a failed startup.

Class loaders and ZIP/JAR caches can retain open archives intentionally. A larger
count or long-lived JAR handle alone does not establish a resource leak. Compare
the same scenario and lifecycle stage across repeated controlled operations.
The default timing matrix must leave this flag disabled.

## Verify a real run

Capture stdout without stripping the phase prefix, then run:

```bash
python3 verify_run.py /absolute/path/to/stdout.log --scenario startup
python3 verify_run.py /absolute/path/to/validation-stdout.log --scenario validation
```

The verifier rejects missing/duplicate phases, hidden windows, backwards clocks,
an incomplete quiet period, pending Jobs, background Job failures, and artificial
validation mislabeled as normal startup. Marker counts are returned for the study
runner to compare with its expected outcomes; they are not silently discarded.

The Java clock-boundary checks and Python output-contract checks exercise the
probe logic only. A passing build is not a real GUI startup result. A real run
must additionally pass this verifier and the study's input/outcome checks.
