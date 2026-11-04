# Independent generated-preamble measurement — 4 November 2026

The original PR1805 claim is reproduced on its exact independent head
`f8dfe691a79de75f55c7633714a15c5626ca6166` versus base
`ef946b6fad6276694f32389311cb7e71cf7f3955`. All 298 original schemas and all
4,557 documentation signatures are checked. This is separate from the combined
PR1803 formatter and from any subsequent integration of PR1805.

| Layout | Before, bytes | After, bytes | Saved |
| --- | ---: | ---: | ---: |
| Compact | 2,014,348 | 2,003,918 | 10,430 |
| Indented | 2,129,822 | 2,119,094 | 10,728 |

Every file loses the exact 35-byte generated pre-root comment. Indented output
also loses its one external LF slot. The content-only SAX handler never receives
comment callbacks. A separately registered lexical observer sees 298 comments
and 8,344 comment-body character units disappear.

**The character payload inside the document does not decrease.** File-stream
`characters()` callback counts change from 60,641 to 60,643 in compact mode and
89,851 to 89,856 in indented mode. Character units and every per-file character
content hash are unchanged. A StringReader control produces different small
grouping shifts: zero additional callbacks in compact mode and two in indented
mode. Outside-root character callbacks remain zero throughout. Removing a
comment can shift parser buffers without changing the resulting character data;
byte count and this callback count are therefore not interchangeable metrics.

All 1,192 base/head/layout/file idempotence comparisons pass. The Maven run
passes all 38 tests with no failures, errors or skips: 33 existing preamble
cases, four actual PDE consumer cases and one full-corpus audit. The corpus has
no actual CDATA nodes; the separately tested CDATA safeguard does not contribute
to these byte differences.

The supported effect is fewer bytes and generated comments for the parser to
scan. This experiment does not measure CPU or IDE startup time, and it does not
show a reduction in character data delivered to the content handler.

See the [full report](PREAMBLE-AUDIT.txt),
[structured summary](READY-FOR-PUBLICATION.json),
[raw aggregate measurements](measurement-summary.json),
[per-file observations](per-file-results.jsonl),
[callback grouping differences](callback-partition-differences.json),
[source identity](source-identity.json) and [Maven log](maven-audit.log).

The complete [reproduction archive](https://chatgpt.com/library?file_id=libfile_b6318d05d8f481918ba60e736cd7f8c5&account_id=personal)
contains the actual corpus, both source revisions, transformed outputs,
harnesses, JUnit reports and logs. Its size is 1,758,399 bytes and SHA-256 is
`16cae8bda84a56b004902e6b16a5e351d1439e1b26e73f374bd89c4701853107`.
