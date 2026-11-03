# Configured XML instances and authentic missing-schema restoration

These tools prepare and audit the inputs for the separate real-PDE instance
validator. They do not replace PDE validation and do not measure startup time.

## Scope and original inputs

`prepare_instance_corpus.py` reads the supplied installation's actual
`configuration/org.eclipse.equinox.simpleconfigurator/bundles.info`. It checks
each configured identity against its artifact's manifest, using OSGi version
semantics (`1.85` and `1.85.0` are equivalent). Distinct configured versions of
plain libraries remain in the inventory. Multiple versions of an XML/schema
provider cannot silently choose the workspace model: they fail preparation.

The frozen reference has 243 configured entries: 50 source bundles, 192
production binary entries and the excluded previous study observer
`org.eclipse.pde.xmlstudy.probe`. The latter is recorded explicitly rather than
counted as an Eclipse production contribution. One plain library ID has two
configured versions. The earlier helper scanned all 305 present artifacts
(255 binary plus 50 source), including 62 unconfigured binary artifacts. All
57 schema providers and all 298 original schemas remain in the configured set.

Original production results:

| Input or coverage status | Count |
| --- | ---: |
| Disposable provider/contributor projects | 83 |
| Original `plugin.xml` files | 83 |
| Original `fragment.xml` files | 0 |
| Extension-point declarations | 293 |
| Extension contributions | 939 |
| Contributions with a present associated schema | 920 |
| Contributions referring to a declared but missing schema | 3 |
| Contributions to a point absent from this reference | 16 |
| Original EXSD resources | 298 |
| XML syntax errors in these descriptors/schemas | 0 |

The 16 absent-point contributions target `org.eclipse.ui.trace.traceComponents`
(14) and `org.eclipse.help.base.searchParticipant` (2). Their provider artifacts
are absent from this assembled reference. They are coverage gaps, not evidence
that those extension contributions are malformed.

The helper copies original binary manifests, XML descriptors, properties and
schema bytes. Source schemas require an exact host and OSGi-version match;
binary resources take precedence. The schema corpus identity remains
`442e16926ec5ee2e3842ee332ed93f6b5eba490c7c04b6bd9969e3ec95e7a491`.
Generated project files configure Java/PDE natures and only the SchemaBuilder.
The importing headless application must disable automatic building before
import and run the requested instance reporter explicitly.

## Raw standard-XSD audit

`audit_raw_xsd.py` compiles the unchanged EXSD documents as W3C XSD 1.0 with
lxml 6.1.1 / libxml2 2.14.6, on Python 3.12.14. No instance is validated by this
step. No schema is normalized. The resolver permits only original corpus
schemas and maps `schema://` references to those local files. Network access
and paths outside the corpus are blocked and counted separately.

All 298 documents are well formed. One compiles unchanged as standard XSD;
297 do not. No missing/blocked include retrieval occurred. Among these files,
225 use legacy `appInfo`, 38 use the legacy attribute `use="default"`, and 94
lack an XSD root namespace. These counts overlap. PDE deliberately supports
legacy syntax, so **297 standard-XSD compilation failures do not mean 297 PDE
load failures or configuration bugs**. The sole unchanged XSD compile pass is
`org.eclipse.jdt.debug/schema/jdiclient.exsd`.

## Restore existing resources, with exact version provenance

Two declared resources are absent from both the frozen binary and matching
source packages. Both exist at the exact source commit recorded in the binary
manifest's `Eclipse-SourceReferences` header:

| Bundle and resource | Exact source commit | Later packaging repair |
| --- | --- | --- |
| `org.eclipse.ui.externaltools/schema/configurationDuplicationMaps.exsd` | `4d9d68a9615c267f272840f344afa6f7e6c14523` | [platform `11c6900`](https://github.com/eclipse-platform/eclipse.platform/commit/11c69009825fac418d1bf9668b887da1413d0a72) |
| `org.eclipse.equinox.p2.repository.tools/schema/org.eclipse.equinox.p2.repository.tools.verifier.exsd` | `b8b9780b20896ad5482568ceffca8d1f686102cf` | [p2 `b97f8c8`](https://github.com/eclipse-equinox/p2/commit/b97f8c833af78b65eacf7a9c4e59d8aad0fb0240) |

Both packaging repairs merged on 2026-10-23 and added `schema/` to
`bin.includes`; both cite [PDE issue 2535](https://github.com/eclipse-pde/eclipse.pde/issues/2535).
The frozen `build.properties` files omitted the schema directory from both
binary and source inclusion lists. Those original build files and the two
unchanged schemas are retained under `resources/`, with original licensing.
The schema bytes also match the last schema-path changes in 2023 and 2010,
respectively, and the later packaging-fix commits. Exact URLs, commits, source
headers, byte counts and hashes are in `resources/provenance.json`.

`restore_missing_schemas.py` verifies those resources and the original binary
source-reference headers before creating a new corpus. It does not overwrite
an existing schema or alter the baseline corpus. The resulting fixture has
300 schemas, 923 mapped contributions, 16 absent-point contributions, and no
missing declared schema. All 83 descriptor bytes and all 298 original schema
hashes remain unchanged. The manifests and project paths are refreshed for
the new destination; metadata explicitly labels this as a reference repair
using already merged upstream packaging fixes.

An additional read-only finding is retained separately: the restored p2
schema's Java `basedOn` metadata names the obsolete
`org.eclipse.equinox.p2.metadata.analyzer.IIUAnalysis`. The real consumer casts
to `org.eclipse.equinox.p2.repository.tools.analyzer.IIUAnalyzer`. The exact
restored schema is deliberately left unchanged. This metadata issue is not
silently included in the missing-resource comparison.

## Reproduce

Run from this directory. Output directories must be new; use disposable
workspaces for the subsequent PDE run.

```bash
python3 prepare_instance_corpus.py \
  --eclipse-home /absolute/reference-eclipse \
  --output-directory /absolute/instance-corpus

python3 audit_raw_xsd.py \
  --corpus-manifest /absolute/instance-corpus/corpus-manifest.json \
  --output /absolute/results/raw-xsd-audit.json

python3 restore_missing_schemas.py \
  --original-corpus /absolute/instance-corpus \
  --output-directory /absolute/instance-corpus-restored

python3 -m unittest discover -s . -p 'test_*.py'
```

The 11 focused checks cover configured scope, byte preservation, OSGi version
identity, instrumentation exclusion, contribution mapping, safe raw-XSD
resolution, restoration coverage and provenance rejection. They are tests of
these experiment tools, not a replacement for the Eclipse/Tycho suite.

`results/summary.json` retains exact versions, counts and archive checksums.
The three `.json.xz` files are lossless copies of the original inventory,
restored inventory and full raw-XSD diagnostics. For example:

```bash
xz --decompress --stdout results/raw-xsd-audit.json.xz
```

`results/missing-schema-findings.json` contains the consumer/source references
and records the separate, unapplied p2 metadata finding. Timing and retry
conclusions belong to the independently executed real-PDE runner.
