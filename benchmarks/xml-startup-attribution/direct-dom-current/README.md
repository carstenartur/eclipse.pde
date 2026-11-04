# Fresh direct-DOM compatibility check — 4 November 2026

The unchanged prototype at
`f46383e59b70d06526857e0f3c85563862a88a3b` was extracted from Git into a new
isolated directory and its existing `run.sh --check` executed with Temurin
25.0.5+8 and the actual Eclipse Platform runtime 3.35.0 JAR.

The run exited zero and reported **81,322 checks passed**, covering nine
synthetic fixtures and all 21 repository EXSD files in both full and abbreviated
modes. The [receipt](verification.json) records every extracted source/input
hash, the runtime hash, Java version and log hash. The unchanged
[raw log](compatibility-current.log) is retained.

This is a fresh compatibility check only. The historical comparison and its
timing limits remain in the
[prototype report](https://github.com/carstenartur/eclipse.pde/tree/f46383e59b70d06526857e0f3c85563862a88a3b/benchmarks/direct-dom-comparison).
No new timing or full PDE build was run for this prototype. No implementation
change was made to obtain the result.
