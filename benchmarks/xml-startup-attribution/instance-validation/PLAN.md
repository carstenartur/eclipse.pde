# Extension instance and schema conformance investigation

## Goal and authorization

Continue the user's requested investigation by checking actual `plugin.xml`
and `fragment.xml` contributions against their extension-point schemas, then
compare confirmed discrepancies with the consuming implementation. The user
authorized execution on 2026-11-03. This extends the existing experiment;
the previous schema-only and GUI measurements keep their original scope.

## Approach

Use the pinned reference installation and the real PDE extension validator.
Enumerate configured bundles, including contributors without schemas. Retain
the exact XML/schema bytes and match source bundles by host and version.
Compile the original EXSD documents with a standard XSD processor separately;
its dialect diagnostics are not instance-validation results.

A standards-based projection of supported EXSD grammar is optional only if
source inspection establishes a concrete gap in PDE's instance checks. Such
a projection must describe every adaptation, reject unsupported constructs,
have independent positive/negative controls, and never rewrite production
inputs merely to make a validator accept them.

## Tasks

- [x] Inventory all 193 configured non-source entries, explicitly separating
  the prior observer from the 192 production binaries, and their original XML
  descriptors; retain the 298 matching schemas from the prior corpus.
  Owner: `inventory/`. Outputs: immutable corpus manifest, project list,
  extension-point and contribution mappings, raw XSD compilation diagnostics.
- [x] Execute the actual PDE `ExtensionsErrorReporter` in a real headless
  OSGi application. Owner: `runner/`. Record exact diagnostic preferences,
  each contribution's point/schema/model availability, and file diagnostics.
  Explicitly distinguish validated contributions from skipped ones.
- [x] Prove the harness detects an unknown attribute, illegal child, missing
  required attribute and occurrence violation using disposable positive
  controls. Restore and hash-check all original inputs before baseline.
- [x] Classify findings against the original schema and consumer source.
  Keep schema dialect differences, missing provider resources, genuine
  configuration defects and insufficient-fixture findings distinct.
- [x] Prepare minimal repairs only where the intended behavior is evidenced;
  rerun the affected real validator and targeted consumer checks. Measure
  repeated loading only if a real finding exercises that failure path.
- [x] Independently review coverage and claims; retain reproducible scripts,
  configurations, raw results, classifications and unresolved limitations.

## Review focus

- Zero diagnostics is not proof of validation when a schema/model was absent.
- Grammar severities must not silently default to ignore.
- A minimal project cannot establish Java class/resource resolution correctness.
- Existing executable-extension syntax may differ from plain XSD syntax.
- Accepted legacy EXSD constructs are not automatically runtime defects.
- No headless validation timing is reported as Eclipse GUI startup latency.

## Completion criteria

Report exact inventory and validation coverage, list actionable findings with
consumer evidence, retain original diagnostics and any before/after changes,
and state explicitly which performance effects were or were not demonstrated.

## Completed observations

The baseline contains 939 extension contributions in 83 original descriptors.
The actual native reporter emits 119 diagnostics. Four identified schema issues
are addressed in five schema files, including a narrowly required companion for
the navigator's copied expression grammar. The final variant has 115 native
diagnostics and 30 more accepted contributions in the bounded strict projection,
with no newly unchecked contributions and unchanged descriptor bytes.

Separately restoring two authentic missing resources improves loaded-schema
coverage from 920 to 923 contributions. Actual model queries cause 25 failed
stream attempts before restoration and one successful load afterwards, for the
chosen initial-load-plus-24-query workload. No additional target handles remain.
These operation counts do not establish startup frequency or elapsed-time savings.

The final focused verification comprises 42 Python methods, 19 native harness
controls in each of five runs, and 18 checks against actual SDK consumers. The
original GUI study's timing conclusions retain their original scope. Full
Tycho tests were not run for these experiment-only additions.
