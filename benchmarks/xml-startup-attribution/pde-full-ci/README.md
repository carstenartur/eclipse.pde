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

## Preserved original artifacts

The original CI ZIP bytes are retained here, independently of GitHub Actions artifact expiry. Each contains the complete build log and uploaded test reports; hashes and original artifact IDs are recorded in the structured summary.

- [fix/schema-jar-cleanup](artifacts/pde-full-verify-schema-jar-cleanup-41903416722.zip) — SHA-256 `2d8c6fa90fca98dc1ae8268ea7dfdbbb24cb1056f38a684d2e2f039578a11086`.
- [fix/schema-empty-documentation](artifacts/pde-full-verify-schema-empty-documentation-41903416722.zip) — SHA-256 `27f76f2b75c9f86385e9bda042fa6da4f4835b19fa84b8f2eaf75151fe7f3409`.
- [fix/single-schema-storage-stream](artifacts/pde-full-verify-single-schema-storage-stream-41903416722.zip) — SHA-256 `e3e139fdcbf3d066b96b680e52963d1f14b42858180cf64f40a128c5926d78d9`.
- [format/schema-writer-tabs](artifacts/pde-full-verify-schema-writer-tabs-41903416722.zip) — SHA-256 `1cb58c03d1e26d6d81b34b5aa83db48edd2066d34f88a2a5c450642cc9904bfb`.
- [perf/bounded-schema-parser-reuse](artifacts/pde-full-verify-bounded-schema-parser-reuse-41903416722.zip) — SHA-256 `cfb8bc987e725af4d2519da244db73fa5a5029c7d3b016d4d5b13f3e2f10dbfa`.

The complete private qualification package, including all earlier controls, raw job logs and the prepared PR bodies, is retained as [PDE-5-branches-checkpoint-2026-11-04.zip](https://chatgpt.com/library?file_id=libfile_061333e1abb88191a8f1c8013ed1eeff&account_id=personal). It is 7,806,471 bytes; SHA-256 `43baf4985b0cecfd6b74af3188857d7eec1c9f6c7369649a8c5fedb80b99ee61`. The public artifacts above contain no unpublished PR drafts.
