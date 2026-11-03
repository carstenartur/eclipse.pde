# Recorded native PDE instance-validation results

The installed PDE `ExtensionsErrorReporter` ran in real headless Eclipse against
the original 83 `plugin.xml` files and 939 extension contributions in the frozen
reference corpus. The corpus has no `fragment.xml` files. The reporter was PDE
3.21.400.v20260810-0751 on Java 25.0.5+8-LTS, Linux.

All five comparisons used the same native application JAR and runner script.
Every run completed with exit 0, all 19 harness controls passing, zero Eclipse
error-log entries, an exact descriptor/contribution match, and unchanged input
bytes. Structural diagnostic categories were explicitly set to ERROR; class and
resource categories were disabled because the imported projects are reduced
fixtures. These counts are not the default IDE warning severities.

| Recorded run | PDE diagnostics | Contributions with loaded schema | Schema-load failures | Unknown extension point |
| --- | ---: | ---: | ---: | ---: |
| `pde-baseline-final` | 119 | 920 | 3 | 16 |
| `pde-repaired`: hasFolder + shared expression grammar | 118 | 920 | 3 | 16 |
| `pde-four-repaired`: also command parameter and CSS provider cardinality | 115 | 920 | 3 | 16 |
| `pde-final-repaired`: also navigator companion to shared expression change | 115 | 920 | 3 | 16 |
| `pde-restored`: authentic missing resources restored, separate intervention | 119 | 923 | 0 | 16 |

The final schema repairs remove exactly four native diagnostics: one illegal
`hasFolder` child in `org.eclipse.ui.ide`, two required-`parameter` cardinality
findings in `org.eclipse.debug.ui`, and one maximum-`provider` finding in
`org.eclipse.e4.ui.css.swt`. No native diagnostic was added. The shared-expression
repair does not remove the 99 native `popupMenus` diagnostics. The intermediate
four-repair corpus is retained for provenance; the navigator companion is needed
for the separate strict-projection compatibility check owned by the parent study.

## What the controls establish

The native reporter detects unknown elements and attributes, required attributes,
minimum/maximum cardinality, invalid enumerations and unknown points. Missing or
undeclared schemas are recorded as coverage gaps even when no marker is emitted.
Five valid comparator cases produce no markers. Deliberately invalid booleans,
reversed sequences, unexpected text content and incomplete sequence arms inside
a choice are accepted silently. Both arms of a simple choice are rejected. Thus
passing these controls establishes a functioning native harness, not complete
W3C XSD validation.

## Missing-resource queries and handles

The two real missing schema URLs belong to
`org.eclipse.equinox.p2.repository.tools.verifier` and
`org.eclipse.ui.externaltools.configurationDuplicationMaps`. A separate diagnostic
retains a real schema model for one initial load plus 24 explicitly induced
accessor queries. Both missing resources cause 25 actual failed stream attempts,
each raising `FileNotFoundException`; the valid `applications.exsd` comparator
opens and closes one stream. Restoring the two authentic schema resources changes
each former missing case to one successful stream, zero exceptions and a loaded
model. Results agree for full and abbreviated models.

There is no additional retained target handle across these calls. The verifier
source JAR remains at 0; the externaltools source JAR retains an already existing
1. Positive controls observe an added handle and its closure, including 1→2→1
for the latter. Ownership of that existing handle is not established. Restored
schemas use copied file URLs instead of the missing JAR entries, so their 0→0
counts do not prove that the old source-JAR handle was closed. No forced garbage
collection is involved. Induced query counts and process durations are not
Eclipse startup-frequency or startup-saving measurements.

## Actual consumer checks

The unchanged `ConsumerContractProbe.java` passed all ten checks inside the
separate real OSGi application: seven expression composites retain all three
supplied children and evaluate TRUE; `hasFolder` returns the expected results
for a directory, a regular file and an absent path. The platform is initialized,
the application exits 0 and its Eclipse log contains zero errors. The JSON records
the actual SDK code sources and versions. The probe source SHA-256 is
`978a43cb545db1dd7b4b265f40e79da54135eabfdc708c251ebcd35c84d000ca`.
The earlier plain-classpath failure is preserved as excluded setup evidence.

## Evidence package

`native-validation-summary.json` contains exact settings, coverage, all controls,
diagnostic additions/removals, retry/handle counters, consumer provenance and raw
artifact hashes. `native-validation-results.tar.xz` contains the five raw JSON
results, execution/build records, logs, corpus manifests, harness sources, both
probe JARs and the consumer evidence. `SHA256SUMS` covers the summary and archive.
Archive members were read back and compared byte-for-byte with their source data.

To reproduce the evidence packaging from existing completed runs:

```bash
python3 ../archive_results.py --verification /absolute/path/to/verification/instance-validation
```
