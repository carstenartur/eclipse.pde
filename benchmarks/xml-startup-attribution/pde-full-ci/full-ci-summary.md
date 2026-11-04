# Full PDE CI qualification — 4 November 2026

All five preserved branch heads passed the complete configured Linux PDE reactor in [GitHub Actions run 41903416722](https://github.com/carstenartur/eclipse.pde/actions/runs/41903416722). Each job finished with **69/69 reactor projects successful**, using Temurin 25.0.5, Maven 3.9.16 and Xvfb. The BREE, API, baseline-version and TCK checks remained enabled.

| Preserved branch | Commit | Reported tests | Passed | Failed / errors | Existing skips | Focused regression tests |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| [fix/schema-jar-cleanup](https://github.com/carstenartur/eclipse.pde/actions/runs/41903416722/job/126831565044) | `cb61c28ccb90` | 4,000 | 3,958 | 0 / 0 | 42 | 7/7 |
| [fix/schema-empty-documentation](https://github.com/carstenartur/eclipse.pde/actions/runs/41903416722/job/126831565375) | `201c47e00f9e` | 3,999 | 3,957 | 0 / 0 | 42 | 6/6 |
| [fix/single-schema-storage-stream](https://github.com/carstenartur/eclipse.pde/actions/runs/41903416722/job/126831564752) | `0af6ed7d6dca` | 3,996 | 3,954 | 0 / 0 | 42 | 3/3 |
| [format/schema-writer-tabs](https://github.com/carstenartur/eclipse.pde/actions/runs/41903416722/job/126831565235) | `bc14ff377dd3` | 3,995 | 3,953 | 0 / 0 | 42 | 2/2 |
| [perf/bounded-schema-parser-reuse](https://github.com/carstenartur/eclipse.pde/actions/runs/41903416722/job/126831565097) | `eedb94d80921` | 4,001 | 3,959 | 0 / 0 | 42 | 8/8 |

All **26 focused regression tests passed inside the full PDE UI suite**, with no failures, errors or skips. The existing suite reported 42 other skipped tests per job; no verification gate was weakened. Test totals above are Maven's 14 final Surefire result summaries per job. Passed totals were independently checked against all 50 XML reports per job, and the focused methods were verified individually. These are test executions across five builds, not a count of unique tests.

The five complete artifact ZIPs were preserved and their SHA-256 digests matched GitHub's artifact metadata. Full build logs and raw job logs are retained. All five source branch heads remain unchanged. Workflow revision: `2f962bc935d6a8003abaee2863c4745cf90ad73c`. Full identities, counts, methods and artifact hashes are in `full-ci-summary.json`.
