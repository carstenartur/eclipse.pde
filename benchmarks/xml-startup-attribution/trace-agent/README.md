# XML startup attribution agent

This is a diagnostic extension to the earlier startup experiment. It starts in
`premain`, before Equinox starts bundles, and observes the XML entry points that
were outside the original two PDE hooks. It is **not suitable for primary timing
comparisons**: stack capture, stream wrappers, synchronized JSON writing and
flushing all affect execution.

The earlier `XMLDefaultHandler.startDocument` and `Schema.load(InputStream)`
counters could establish where those hooks ran. They could not establish that
startup contained no XML. In particular, a missing JAR resource can fail in
`URLConnection.getInputStream()` before `Schema.load(InputStream)` is reached.
The new controls exercise that exact failure through the real PDE `Schema.load()`.

## Run

Requirements are a JDK capable of running the selected Eclipse product (the
recovered product was run with Temurin 25.0.5+8), Node 18 or later, Bash, `rg`, and
exactly three ASM jars in one directory: `asm`, `asm-tree`, `asm-commons`, all from
one release. ASM 9.10.1 was tested. The agent itself compiles for Java 17; the
Eclipse probe and control clients compile for Java 21. There are no downloads in
the runner and no new Python dependency.

```sh
export XML_TRACE_JAVA_HOME=/path/to/jdk25
export XML_TRACE_ASM_DIR=/path/to/asm-9.10.1-jars
./run-eclipse-scenarios.sh /path/to/eclipse /path/to/new-output headless

# On Linux, with Xvfb and the product's GTK/X11 runtime dependencies installed:
xvfb-run -a ./run-eclipse-scenarios.sh /path/to/eclipse /path/to/new-gui-output gui
```

`all` runs both groups. The output directory must not already exist. The original
installation is read only: each group has its own configuration, workspace and
fixture projects. It references the original plug-in directory through a symlink.
Each Eclipse launch is a separate JVM. The runner aborts after a failed control,
launch or coverage assertion; the failed artifacts remain available.

A GUI run needs an actual display and native GTK/X11 libraries. The local
recovery environment had no Xvfb or `libXtst`, so the checked-in local evidence is
headless. Compilation and headless controls do not constitute GUI execution.
Use the separate GUI output from CI before drawing conclusions about workbench
readiness, editor restoration or GUI background completion.

## Positive controls

The eight JDK controls use actual APIs:

1. SAX parses XML from a JAR URL.
2. DOM parses the same JAR resource.
3. `ZipFile.getInputStream` delivers exactly 66 bytes, matching both the known
   payload and the uncompressed ZIP entry size.
4. Opening a nonexistent JAR `.exsd` entry throws before parsing.
5. `Files.newInputStream` fails on a missing XML file.
6. A `FileInputStream` constructor fails on a missing XML file.
7. Malformed XML produces an observed parser exception.
8. A separate worker thread parses XML and retains its thread attribution.

The five Eclipse controls run the product's real classes on the class path:

1. Equinox `RegistryFactory` accepts an actual extension contribution.
2. EMF `XMIResourceImpl` loads one Ecore object.
3. PDE `Schema.load()` loads a valid schema with one element.
4. PDE `Schema.load()` opens a missing JAR entry, leaves the schema unloaded,
   emits the failed resource-open event, and never reaches the old InputStream
   overload hook.
5. An Eclipse Job runs and finishes before any startup-probe activation.

The verifiers require the corresponding trace events, actual API results, a
final summary, no lost events, no open spans and no instrumentation errors.
Running the client successfully without an agent does not satisfy the verifier.
The original eight probe logic checks and three real file-descriptor checks also
run when the probe is built.

## Scenario definitions

The fixture consists of two small PDE/Java projects. Both declare JavaBuilder,
ManifestBuilder and SchemaBuilder. The provider exports a Java package and
publishes its own extension point with `schema/control.exsd`. The dependent
consumer uses that package and contributes to that extension point. These are
explicit fixtures, not an imported production workspace.

| Scenario | Registry and workspace condition | Observation boundary |
| --- | --- | --- |
| `headless-cold-registry` | New configuration with `-clean`; import both fixture projects; automatic build off | Application entry, explicit PDE model/schema loads, one-second job quiet window, workspace save |
| `headless-prepared-restart` | Reuse that configuration/workspace without `-clean`; automatic build off | Same headless boundaries |
| `headless-automatic-build` | Prepared registry; enable automatic build and touch provider schema plus consumer `plugin.xml` | Actual automatic-build completion, then headless quiet boundary |
| `gui-workspace-preparation` | Headless preparation for the GUI group | Explicitly not a workbench-ready observation |
| `gui-cold-registry` | Prepared workspace; registry/configuration caches invalidated; automatic build off | Visible workbench ready, then background quiet boundary |
| `gui-prepared-restart` | Reuse GUI configuration/workspace without `-clean` | The two separate GUI boundaries |
| `gui-automatic-build` | Prepared baseline; enable automatic build and touch fixture resources during startup | Build trigger, ready, actual build completion and later quiet boundary, in their observed order |
| `gui-editor-seed` | Restore the baseline configuration, workspace **and fixture files**; automatic build off | After ready, open the PDE manifest and schema editors; close normally to persist them |
| `gui-restored-editors` | Reuse the seeded session without `-clean`; automatic build off | Ready and quiet boundaries, with restored references and materialized editors reported |

The automatic-build workload invokes no explicit `workspace.build` or full-build
request. It requires an `IResourceChangeEvent.POST_BUILD` event with `AUTO_BUILD`,
no error markers, actual Java and PDE builder calls, `Schema.load`, and a real open
of the consumer's `plugin.xml` during the trigger-to-completion interval. A
first-time automatic build may invoke an individual builder with `FULL_BUILD`;
the invocation kind and project are recorded rather than inferred from the job
name. Enabling automatic build and touching resources can cause more than one
automatic-build event.

The editor probe calls `getEditor(false)` so observation does not force lazy
restoration. The report distinguishes existing editor references from actually
instantiated editor parts. Seeding editor state is separate from the subsequent
restart. The seed deliberately opens both `org.eclipse.pde.ui.manifestEditor` and
`org.eclipse.pde.ui.schemaEditor`.

`-clean` means a cold Equinox registry/configuration cache. It does not clear the
OS page cache, JVM installation files, product archives or every possible cache.
The OS cache is uncontrolled and expected to be warm. This small matrix is for
coverage and causal attribution, not a statistically powered latency comparison.

## Coverage

The transformer emits the exact class/method inventory it successfully modified.
Its selected hooks include:

| Area | Hooks or events |
| --- | --- |
| Earliest observation | Java-agent `premain`, before application and probe activation |
| Registry | `RegistryStrategyOSGI.onStart` including `loadedFromCache`; `ExtensionsParser.parseManifest`; `ExtensionRegistry.addContribution` |
| Resource opening | JDK jar/file URL connections, `URL.openStream`, `Files.newInputStream`, `FileInputStream` constructors, selected Equinox bundle URL/entry streams |
| JAR lookup and reading | `ZipFile.getEntry`, `ZipFile.getInputStream`, Equinox bundle-file entry lookup and stream opening |
| SAX and DOM | JDK Xerces and external Xerces `AbstractSAXParser.parse` / `DOMParser.parse` |
| StAX | JDK `XMLInputFactoryImpl.createXMLStreamReader` creation only |
| PDE | The legacy handler hook, both `Schema.load` overloads, `AbstractExtensionsModel.load`, ManifestConsistencyChecker and ExtensionPointSchemaBuilder |
| Java build | `JavaBuilder.build` including observed build kind and project |
| EMF/E4 | `XMLLoadImpl.load`, `XMLResourceImpl.doLoad`, E4 ResourceHandler model-load methods |
| Jobs | JobListeners' actual `queueScheduled`, `queueRunning`, `queueDone`, awake/sleep/about-to-run methods, as well as the older names when present |
| Probe boundaries | Explicit headless phases; GUI probe emit/finish phases, including ready and background settled |

I/O selection includes XML-like suffixes (`.xml`, `.xmi`, `.exsd`, `.mxsd`, `.xsd`,
`.dtd`) and resources opened inside an observed parser/loader span. `.class`
lookups are excluded even inside parser setup to prevent class loading from
dominating the trace. An unresolved source is reported as `<unresolved>`; a known
InputSource system ID or tracked stream is preferred. A caller stack is retained
for each begin event, together with a parent span ID, thread name and thread ID.

An operation has `begin` and `end` records with source, initial phase, end phase,
outcome and duration. Missing entry lookups and thrown opens are distinct. A
public `Schema.load()` can return normally after catching a failed open; the
child failed-open event and the control's `isLoaded()` result are therefore
necessary to interpret success. `returned` means the method returned, not that a
schema was semantically valid.

Counts are method invocations, including nested overloads and repeated loads.
Do not sum operation categories to infer a document count. The explicit
headless WorkspaceExtensionsModel load is an abbreviated header load; the
automatic-build scenario separately exercises real builder/XML work.

A phase is the latest global phase marker, not exclusive ownership of every
concurrent operation. The original phase and `endPhase` show work that spans a
boundary. Jobs retain their identity and dispatch events even when they started
before the late bundle probe could attach a listener. Job counts are not XML
parse counts, and the quiet window ignores sleeping jobs. Later scheduled work
can still happen after the recorded boundary.

## Byte attribution and limits

The returned streams from selected open methods are wrapped. They record bytes
delivered, skipped bytes, EOF, close or shutdown, and bytes delivered in each
phase. ZIP stream records additionally retain the entry's declared uncompressed
size, compressed size and compression method.

The summarizer adds **only** `zip_entry_open` stream records attributed by an XML
suffix. It does not add URL and ZIP wrapper layers together. Reopening an entry
or rereading bytes counts again. The sum is uncompressed bytes delivered through
that stream layer; it is **not** physical disk I/O, compressed JAR traffic, unique
XML bytes or total parser allocation. Compressed ZIP size is metadata, not a
measurement of compressed reads. Streams not fully consumed can have `reachedEof`
false. FileInputStream constructor observations explicitly have
`bytesMeasured=false`.

The agent does not claim universal XML coverage. Parser implementations outside
the listed classes, native parsers, all StAX reader iterations, all possible URL
protocols or channels, and character readers with no useful system ID can remain
outside resource attribution. Source/caller gaps are retained rather than filled
in by inference. A complete trace means its instrumented spans and event stream
completed without recorded losses; it does not prove that every XML operation
in the JVM was instrumented. No generic claim of “zero startup XML” is warranted
from an absent counter alone.

Bootstrap delegation and module read edges let Eclipse bundle classes and JDK
parser classes reach the same sink. This is another reason to run the agent only
in diagnostics. Wrapping can change concrete stream identity and runtime cost.
Controls and actual Eclipse runs check the selected product; they do not establish
compatibility with every product or JDK version.

## Results and retained artifacts

Every run writes:

- `process.log`, including start failures and Eclipse error entries;
- `trace.jsonl`, including instrumentation inventory, phases, begin/end, streams,
  jobs and final completeness counters;
- `trace-summary.json`, aggregating selected operations and ZIP byte delivery;
- `probe.json`, with workload result, ready/quiet boundaries or explicitly
  headless boundaries;
- `run-manifest.json` at the output root, recording commands, exit/timeout state,
  input/plugin/agent/probe/source hashes, cache conditions and coverage checks.

Control directories also contain `verification.json`. A runtime failure, error
log entry, missing probe output, lost event, unfinished span or failed scenario
assertion makes the run fail. No success label is derived from timing alone.

For durable, compact evidence without workspace copies:

```sh
node package-evidence.mjs /path/to/run-output /path/to/new-evidence-directory
```

This preserves full raw JSONL bytes as gzip and writes SHA-256 hashes for both
compressed files and their uncompressed source. Keep the manifest and process
logs together with the traces. The original workspaces remain in the run output
for inspection; they are not needed to reproduce the fixture.

The local results are documented in `RESULTS-2026-11-04.md`. GUI results must be
reported independently when the display-capable CI run has completed.
