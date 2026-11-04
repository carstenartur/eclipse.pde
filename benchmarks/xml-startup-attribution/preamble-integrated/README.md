# Final integrated formatter qualification — 4 November 2026

The integrated Sandbox PR1805 source at
`0b066c49b074b7c90000e45577a5df470040169f`, tree
`ffd04d9f47c04173866c471c288ae4d8d51e3965`, passes the complete 298-schema,
eight-policy audit and one complete native PDE consumer run.

This is the final combined-source follow-up to the earlier
[PR1803 corpus qualification](../corpus-current/README.md) and
[independent PR1805 measurement](../preamble-independent/README.md). The owning
integration workflow's required GitHub CI and merge are separate from this
local source/consumer qualification; no CI gate is bypassed or inferred here.

## Source and corpus

The main parent `bd5116de4929805bb719864e367684e945088b52` has the same tree as
the audited `12033ef005df89f631cb2752e6e0949fbba8a2cd` formatter. Production
Java is unchanged. The integrated root XSL template exactly matches the
independent preamble change; all remaining XSL content exactly matches main.
The production delta is 12 added lines and one deleted line in that template.
The [source review](source-review.json) and [identity](source-identity.json)
record those comparisons.

All original files again match their preserved hashes and lengths: 298 schemas,
2,337,930 bytes and 4,557 documentation nodes. The corpus digest remains
`442e16926ec5ee2e3842ee332ed93f6b5eba490c7c04b6bd9969e3ec95e7a491`.
Every file and each of the eight policy combinations is idempotent on its first
pass: 2,384 checks and 4,768 transformations, with zero failures.

## Final sizes and preserved content

| Layout | Documentation policy | Previous combined bytes | Integrated bytes | Marginal preamble saving |
| --- | --- | ---: | ---: | ---: |
| Compact | Preserve | 1,943,420 | 1,932,990 | 10,430 |
| Compact | Trim eligible boundaries | 1,941,584 | 1,931,154 | 10,430 |
| Indented | Preserve | 2,086,446 | 2,075,718 | 10,728 |
| Indented | Trim eligible boundaries | 2,084,610 | 2,073,882 | 10,728 |

Both appinfo policies have these aggregate values. Preservation mode retains
all documentation signatures. Opt-in trimming still changes only the already
qualified 108 eligible nodes in 82 files. Every integrated output has exactly
the same documentation as its corresponding previous-policy output.

Complete-output comparisons verify that the marginal change consists only of
the generated preamble and its external layout slot: 35 bytes per compact file
and 36 per indented file. The preservation layouts save 404,940 and 262,212 bytes
respectively from the original corpus, including all preceding formatter work.

## Callback counts are not text-volume counts

All per-file character-content hashes and UTF-16 totals are unchanged by this
last preamble step. Measurements use the actual Eclipse `XmlProcessorFactory`.

| Layout / documentation | File-stream characters calls | StringReader characters calls |
| --- | ---: | ---: |
| Compact / preserve | 54,777 → 54,768 | 54,769 → 54,766 |
| Compact / trim | 54,772 → 54,764 | 54,765 → 54,762 |
| Indented / preserve | 89,850 → 89,850 | 89,847 → 89,856 |
| Indented / trim | 89,845 → 89,845 | 89,842 → 89,852 |

These small, input-dependent grouping shifts preserve identical character
data. Outside-root character events stay zero. A lexical observer separately
records 298 fewer comment callbacks and 8,344 fewer comment-body units per
policy. These integrated counts must not be substituted for the independent
head's different grouping shifts. Neither set establishes a CPU or startup
effect. The [warm timing study](../load-current/RESULTS-2026-11-04.md) remains
explicitly pinned to the preceding PR1803 formatting inputs.

## Native PDE results

The unchanged reference product, with active PDE Core 3.21.400.v20260810-0751
and real workspace services, read the original plus eight transformed trees.
It produced 8,046 observations, 5,364 successfully loaded full/abbreviated
models, 2,682 lightweight annotation results and 2,682 native HTML documents.
All **14,304 component comparisons agree**, with zero different, blocked or
failed observations. All 936 include resolutions match their actual workspace
provider resources.

The comparisons cover native metadata/grammar, full and raw/lazy documentation,
lightweight annotations and exact `SchemaTransformer.BUILD` HTML. There is no
production-class overlay or mocked loaded state in this final runtime. The
native process exits zero with `allComponentsQualified=true`; the transformer
audit reports Maven `BUILD SUCCESS`.

## Evidence

The [complete report](INTEGRATED-PREAMBLE-AUDIT.txt),
[structured handoff](READY-FOR-PUBLICATION.json),
[all measurements](measurement-summary.json),
[native summary](osgi-audit/runs/product/results/summary.json), source identity
and raw logs are retained here. The three large observation files are stored
losslessly as gzip; [compressed-evidence.json](compressed-evidence.json)
records both original and compressed byte lengths and SHA-256 values.

The complete [reproduction archive](https://chatgpt.com/library?file_id=libfile_0a0a6d81b5ac8191bfc3f1066aed93f7&account_id=personal)
contains 5,118 files, including original schemas, baseline and integrated
outputs, source snapshots, drivers, native observations, include resolutions
and logs. It is 6,562,296 bytes; SHA-256:
`88d0ae7dbac9f4a0e0a176b4fb27c82f548c134559e0208306931d538c1658db`.
Both earlier audit archives retain their exact hashes and contents.
