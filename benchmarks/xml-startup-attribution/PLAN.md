# XML correctness and Eclipse startup experiment

## Goal

Identify reproducible production XML/schema defects, correct confirmed defects,
and compare an actual Eclipse IDE under controlled inputs. Separate the effect
of correctness repairs, PR #2575 text coalescing and safe input compaction.
The user's installation/workspace is not available; any local reference
installation and workload must be identified explicitly.

## Design decisions

- Keep the existing reviewed PR unchanged. Store the experiment on an isolated
  branch based on `ba6a5d6f2f455ab7dfe972ce678d07d9f80de267`.
- Use real Eclipse/PDE implementations. Do not substitute generic W3C XSD
  validation for PDE's EXSD grammar or repair intentionally invalid test data.
- A failing schema may cause repeated reads. Prove that mechanism with counted
  input streams separately from production-file findings.
- Prefer a real GUI Eclipse installation plus a pinned workspace over headless
  bundle bootstrap. If GUI startup is blocked, report that limit and preserve
  a runnable comparison; never call a headless parser run an IDE startup.
- Measure workbench readiness and completion of the selected workspace work
  separately. Keep source files, preferences, validation and product identical
  except for the intervention. A quicker abort is not successful work.
- Use randomized blocks of fresh JVMs and separate normal-cache runs from
  registry rebuilds. `-clean` is not a cold OS filesystem cache.
- Compare individual interventions and their combination. Use all eight
  combinations of three binary factors if available and affordable; report
  interactions rather than forcing single-change percentages to sum to 100%.
- Record raw wall/CPU times, parse/read counts and validation outcomes. Keep
  detailed profiling runs separate from primary timing runs when instrumentation
  is expensive. Do not claim an effect smaller than observed run variation.

## Tasks and verification

- [x] Inventory production defects and the available Eclipse/JDK/display setup.
  Each candidate records its file, violated PDE rule and reproduced diagnostic.
- [x] Reproduce repeated parsing after a malformed schema with the real Schema
  class and a counting URL; contrast with a valid input and label it synthetic.
- [x] Apply minimal repairs only to confirmed production defects; verify that
  their original diagnostics disappear without suppressing validation.
- [x] Build the reference-workspace/probe/runner with a versioned input manifest.
  Verify a smoke run reaches a visible workbench and the chosen completion
  condition; collect failures/timeouts as failures, not faster runs.
- [x] Run the controlled variant matrix and analyze absolute milliseconds,
  distributions, errors and interaction effects. Publish exact reproduction
  commands, changes, raw results and limitations.
- [x] Independently review correctness and measurement claims and prepare the result for publication.

## Review focus

- Invalid input that stops parsing early must not appear as an improvement.
- Expected-invalid test fixtures must not become production fixes.
- Reset caches, modified jars and workspace preferences must be matched.
- Build completion must not race a job that has not yet been scheduled.
- Parser CPU, background work and user-visible startup latency are distinct.

## Outcome

See README.md and results/analysis.json. The final study covers 298 schemas in 57 provider projects, 20 valid GUI runs and a separate diagnostic run. No production schema-load failure was reproduced in this reference corpus. Therefore no fabricated XML-error-fix timing factor was added. A storage-stream bug and a documentation example were repaired independently; their startup effects are not claimed.
