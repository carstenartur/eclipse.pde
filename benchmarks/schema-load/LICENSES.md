# Licenses and source availability

The original source headers and unchanged dependency JARs are retained. Extracted notices are in `licenses/`; `provenance/dependencies.json` identifies their exact artifact and includes corresponding public source-download URLs.

| Component | License / notice location |
|---|---|
| PDE source variants, support snapshot, Eclipse bundles and schema corpora | EPL-2.0; `licenses/EPL-2.0.txt` and each bundle's `about.html`. Bundles may carry additional third-party notices, which are preserved. |
| JMH 1.37 and annotation processor | GPL-2.0 with Classpath exception; complete `LICENSE` and `THIRD-PARTY` files from the JARs are included. |
| Apache Commons Math 3.6.1 | Apache-2.0; embedded `META-INF/LICENSE.txt` and `NOTICE.txt`. |
| jopt-simple 5.0.4 | MIT; artifact POM plus the complete copyright/license header extracted from its matching public source JAR. |
| Woodstox 7.3.0 | Apache-2.0; embedded `META-INF/LICENSE`. |
| Stax2 API 4.3.2 | Simplified BSD / BSD-2-Clause; embedded `META-INF/LICENSE` names FasterXML.com and the license reference. |
| Standalone reproduction driver | EPL-2.0. |

The PDE support snapshot's matching source JAR is included beside its binary archive. For the original corpus and source overlays, pinned repositories/commits and per-file hashes are in `provenance/`. Experimental local source variants are included directly and are not represented as published upstream commits.

The complete companion ZIP preserves the exact artifacts. Download-source URLs are provenance, not a promise that rolling Eclipse integration-build repositories will retain those files indefinitely.
