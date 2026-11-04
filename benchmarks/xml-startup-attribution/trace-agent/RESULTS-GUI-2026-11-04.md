# GUI startup XML diagnostics — 2026-11-04

## Verified outcome and identity

The [CI run 41904302644](https://github.com/carstenartur/eclipse.pde/actions/runs/41904302644)
completed successfully at commit `8f9e34d14c79bc6257a535abca9c6e8b07131826` on
`experiment/xml-startup-costs`. All nine scenarios passed, including five real
workbench launches under Xvfb. Eight JDK controls, five Eclipse controls, eight
probe logic checks and three descriptor checks also passed. No implementation
change was needed after the first GUI execution.

[Artifact 13359139160](https://github.com/carstenartur/eclipse.pde/actions/runs/41904302644/artifacts/13359139160)
is 2,311,883 bytes; its ZIP SHA-256 is
`c8fcacc92eeaebbe63880c8a635392766cd0ab16c8e639c5debb14adcdfc7dff`.
The exact evidence is retained in [evidence/2026-11-04-ci](evidence/2026-11-04-ci),
including the original [manifest](evidence/2026-11-04-ci/run-manifest.json),
[hash index](evidence/2026-11-04-ci/evidence-index.json), raw gzipped JSONL and
[verification report](evidence/2026-11-04-ci/verification-report.json).

Independent local re-reading verified all 43 indexed artifact files, all 11 raw
trace hashes, all trace span closures/final-summary counts, all nine regenerated
summaries and coverage results, all 28 source hashes, and all 346 binary plug-in
JAR hashes against the recovered reference. Every scenario exited zero with no
trace/instrumentation errors, dropped events, unfinished spans or Eclipse error
entries. The agent and bootstrap hashes match the earlier local headless run.

The prior run at `640249e4` failed before controls because CI did not have `rg`.
Adding the documented `ripgrep` prerequisite fixed that setup failure. It provides
no startup result; its artifact contained only the two built agent JARs.

## XML before workbench readiness

These are observed **method entries before `workbench_ready`**, not unique
physical files or a sum of documents across parser layers. The editor seed run
opens its editors only after readiness and is therefore reported separately.

| GUI scenario | Platform registry cached | Registry parser | SAX | DOM | EMF load | Schema.load |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Cold registry | false | 170 | 297 | 29 | 6 | 0 |
| Prepared restart | true | 19 | 159 | 22 | 6 | 0 |
| Automatic build | true | 36 | 164 | 21 | 6 | 0 |
| Editor seed | true | 0 | 143 | 22 | 6 | 0 |
| Restored editors | true | 36 | 163 | 26 | 6 | 2 |

The cold run delivered 2,497,500 uncompressed XML bytes through observed ZIP-entry
streams before readiness; the other four GUI runs delivered 130,512 each. These
are delivered bytes at that stream layer, including rereads, not compressed JAR
traffic, unique XML data or physical disk I/O.

The prepared run's platform registry really reports `loadedFromCache=true`.
Its 36 registry parser calls across the entire run come from
`TargetBundle.getProvidedSource`: 18 synthetic source-point XML contributions and
18 exploded `plugin.xml`/`fragment.xml` contributions. Nineteen of those calls
happened before readiness and 17 afterward. The caller stacks distinguish this
PDE target initialization from reconstruction of the cached platform registry.
An unknown/anonymous InputSource remains explicitly unresolved in the raw data;
it is not assigned a guessed path.

## Readiness and background completion differ

The automatic-build scenario enabled building and touched the provider schema
plus consumer `plugin.xml` during startup. Its observed JVM-uptime markers were:

| Marker | Uptime, ms |
| --- | ---: |
| Automatic-build trigger started | 1,942 |
| Fixture resources touched | 1,983 |
| Workbench ready | 6,476 |
| Automatic build finished | 7,498 |
| Background quiet boundary | 8,919 |

The trigger-to-completion interval contains two actual `AUTO_BUILD` completion
events, two Java builder calls, four PDE builder calls, four `Schema.load`
entries and seven selected consumer XML open calls, with zero build error
markers. All six builder calls and the four schema-load entries occurred **after
workbench readiness** in this run. Between readiness and the quiet boundary,
there were another 184 SAX parser entries and 172 registry parser entries.
There was no explicit full-build request; resource changes triggered automatic
building. Build kinds and project names are retained in the report.

These timestamps establish ordering in an instrumented diagnostic run. They do
not estimate a patch speedup or provide a statistically powered startup latency
comparison. A one-second quiet window is part of the later boundary.

## Actual editor restoration

The seed run opened both the PDE manifest editor and schema editor after
readiness; both became instantiated and their state was saved by normal close.
On the separate restored-editor restart, the schema editor was already
instantiated at readiness, with two `Schema.load` method entries (the nested
public/InputStream load paths) before that boundary. The manifest editor reference
was restored but remained lazy. The observer uses `getEditor(false)` and did not
force the lazy editor to instantiate.

Thus a zero schema count in the earlier prepared/no-editor scenario does not
apply to a restart that restores the schema editor. The new positive control
establishes the relevant path with the actual product classes.

## Completion, warnings and scope

The five GUI runs each exercised E4 model loading and six EMF load entries. The
three headless runs and headless GUI-workspace preparation are labeled separately;
none claims GUI readiness. All nine run results are present in the manifest.

The raw trace continues through shutdown. In four prepared GUI runs it captures
one further file open and DOM parse from `JavaPlugin.stop`, loading
`QualifiedTypeNameHistory.xml` on the framework-stop thread. Those events are
reported after the quiet boundary, not folded into startup counts.

The logs retain an Xvfb accessibility-bus warning in each GUI run and one GTK
missing-theme-icon warning during editor seeding. These are native environment
warnings; there were no Eclipse error entries or failed scenario assertions.

The GUI quiet gate includes running/waiting jobs and sleeping BUILD-priority,
PDE and AutoBuildJob jobs; the headless gate includes running/waiting jobs only.
Neither boundary proves that every executor or future scheduled task is finished.
Parser/method counts, nested layers, selected byte coverage and unknown paths
retain the limitations documented in [README](README.md). The product, fixture,
cache conditions and heavy instrumentation differ from the original primary
timing matrix. The run establishes XML attribution and scenario sensitivity.
