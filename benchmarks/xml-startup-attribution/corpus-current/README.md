# Complete 298-schema formatter qualification — 4 November 2026

## Source and corpus identity

This audit qualifies the exact combined formatter tree
`b8ccc2b4253da1e2e49b6cfe496c5aeb95e6ef8f`, published in Sandbox PR1803 as
`12033ef005df89f631cb2752e6e0949fbba8a2cd` and merged unchanged as
`bd5116de4929805bb719864e367684e945088b52`. The local equivalent commit in the
raw audit metadata is `20dabecfb988073c5c27c9bf68004cf22c6a52f3`.
The tree includes metadata normalization, appinfo handling and documentation
policy work. It **does not include preamble PR1805**.

The later [integrated PR1805 audit](../preamble-integrated/README.md) qualifies
the complete combined formatter. The original figures below remain unchanged
and provide the baseline for its marginal preamble measurements.

All **298 original schemas** were recovered byte-for-byte: 2,337,930 UTF-8 bytes
and 4,557 documentation nodes. Every file matches its preserved byte count and
SHA-256. There are no missing files, substituted revisions or hash mismatches.
The original corpus digest is
`442e16926ec5ee2e3842ee332ed93f6b5eba490c7c04b6bd9969e3ec95e7a491`.
Recovery used 39 matching binary-package schemas, the preserved 49-file UI
archive, and 210 files from exact source commits recorded by the original
binary bundles. Missing declared schemas outside this original corpus were
not silently invented or added.

## Formatter results

The existing 99 focused tests pass on Java 25. Across all eight combinations of
indentation, appinfo target and documentation policy, every file is idempotent:
2,384 file/option comparisons, 4,768 transformation calls, zero failures.
All 22,175 XML elements are retained. The preservation policy retains all 4,557
documentation signatures; opt-in boundary trimming changes 108 eligible nodes
in 82 files and saves an additional 1,836 bytes. Its retained content is checked
separately from the preservation policy.

| Corpus/layout | Documentation policy | Bytes | Savings from original | SAX characters calls |
| --- | --- | ---: | ---: | ---: |
| Original | Original | 2,337,930 | — | 101,992 |
| Compact | Preserve | 1,943,420 | 394,510 | 54,769 |
| Compact | Trim eligible boundaries | 1,941,584 | 396,346 | 54,765 |
| Indented | Preserve | 2,086,446 | 251,484 | 89,847 |
| Indented | Trim eligible boundaries | 2,084,610 | 253,320 | 89,842 |

The two appinfo policies have the same aggregate counts in this corpus; all
eight variants remain independently checked. Callback counts belong to the
observed parser/input path and are not universal file properties or timings.
The separate [current load benchmark](../load-current/RESULTS-2026-11-04.md)
uses the exact 49-file UI subset of the preservation variants in this table.

## Actual PDE consumers in active OSGi

The existing eight focused PDE consumer fixtures pass. The complete corpus
was then read in three independent, initialized Eclipse/OSGi configurations:

1. The unchanged reference PDE Core 3.21.400.v20260810-0751 binary.
2. All relevant schema production sources from baseline
   `f948c57878a1a011625b5214d63a1ec01bd243ff`.
3. The empty-documentation fix at
   `201c47e00f9e0bcae8ec3f435eb58704a6ee5027`.

Each runtime produced **14,304 equal component comparisons**, with zero
differences, blocked cases, failures or Eclipse errors. Each loaded 5,364 full
and abbreviated models and verified 936 actual include resolutions. The six
comparison components are full metadata/grammar, full documentation, exact
generated HTML, abbreviated metadata/grammar, actual raw/lazy documentation,
and lightweight schema annotations. HTML is compared exactly, without
normalizing or filtering differences. The 9 original/transformed trees retain
real provider projects and include locations.

Both source variants also match the reference binary in all 16,092 original
and transformed component digests. Source and input hashes, including the
effective overridden classes, are retained. Distinct schema URLs were checked
for the description-cache key collision that could otherwise obscure results.

An earlier standalone full-corpus harness failed because the PDE singleton was
not active while resolving includes. That harness limitation is retained in
the diagnostic report; it is resolved by these actual OSGi runs. This corpus
does not reproduce the separate empty-documentation bug. Its dedicated
regression fixtures do. No repeated-load startup cost is inferred from the
standalone failure or from this successful corpus.

These checks establish the observed formatter/consumer compatibility and
idempotence. They do not replace the repository's required Tycho/CI gates,
prove arbitrary XML equivalence, or measure IDE startup speed.

## Complete evidence

The [summary](corpus-audit-summary.json),
[per-file/option results](corpus-audit-detail.tsv),
[recovery provenance](corpus-recovery.json),
[corpus verification](corpus-verification.json),
[OSGi qualification](osgi-audit/qualification-summary.json) and
[OSGi report](osgi-audit/OSGI-CORPUS-AUDIT.txt) are retained here.

The complete [audit archive](https://chatgpt.com/library?file_id=libfile_a4438035e83481919885f888f0704ccc&account_id=personal)
contains the actual corpus and transformed trees, exact source snapshots,
reproduction harnesses and all raw model/HTML/include observations and logs.
It is 9,235,665 bytes; SHA-256:
`0c70a429e29e9458694c207cbeb7c7b48d15f6a5e2fca46bf7766218d3bb15fd`.
