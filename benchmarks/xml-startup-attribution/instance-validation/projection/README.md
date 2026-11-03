# Bounded structural-grammar projection

This supplementary check applies a real XSD 1.0 engine to a narrowly documented,
in-memory projection of the frozen Eclipse extension schemas. It complements
the [actual PDE reporter](../runner/README.md). It is not validation against the
unchanged EXSD files, a general EXSD converter, or an XMLSpy-equivalence claim.
No startup timing is measured here.

The final schema variant addresses four issues in five files. Of the 939
original contributions, **30 move from projected-invalid to projected-valid**.
There are **no newly unchecked contributions and no valid-to-invalid
transitions** in the final comparison. All 83 original descriptor files remain
byte-identical. The missing-resource restoration is a separate experiment.

## Exact adaptation policy

`project_grammar.py` uses the inventory's bundle identities, contribution paths
and declared-schema mappings. It does not guess associations from filenames.
Every inventoried schema and descriptor is checked against its frozen SHA-256;
resolved includes must also belong to that inventory. Hashes are checked again
after the audit. A changed input aborts the audit.

The projection makes only these adaptations:

1. Remove EXSD annotations, including their documentation and PDE metadata,
   from the grammar sent to the XSD compiler. Java and identifier metadata are
   inspected separately for the explicit skip/classification rules below.
2. Drop `targetNamespace` to describe unqualified extension-instance elements.
   Only unqualified or W3C-XSD-namespaced structural declarations are accepted.
3. Qualify supported built-in `type` and `base` names as `xs:string`,
   `xs:boolean` or `xs:anyURI`.
4. Translate the legacy attribute notation `use="default" value="..."` to
   `use="optional" default="..."`. Ambiguous forms are rejected. Validation
   does not insert defaults into the original XML.
5. Resolve relative includes and `schema://bundle/path` includes from the exact
   local corpus, flatten their global declarations, and deduplicate only
   structurally identical projected declarations. Network resolution is disabled.

The supported structural elements are `element`, `complexType`, `simpleType`,
`sequence`, `choice`, `all`, `attribute`, `restriction` and `enumeration`, with
the explicit attribute allowlists in the script. Declared order, choices,
occurrence bounds, required attributes, enumeration restrictions and character
content constraints are preserved. The baseline never repairs a sequence into
a choice or removes an enumeration merely to obtain a pass.

Unsupported constructs/types/namespaces, absent or external includes,
conflicting globals, XSD compilation failures and unavailable schema mappings
are **unchecked**, not valid. Namespaced instance elements or attributes are
also unchecked, preventing `xsi:type` or other unmodelled namespace semantics
from silently entering the check. A contribution using a known executable
extension child alternative of a Java attribute is explicitly unchecked in
this projection; native PDE validation and focused consumer checks cover that
syntax. This conservative subset does not assert full PDE grammar equivalence.

Only schemas associated with the inventoried contributions are compiled for
this check: 209 used schema projections compile in the baseline and final
variant; one used schema remains ambiguous. This is distinct from the raw-XSD
audit of all 298 EXSD resources.

## Results and the intermediate compatibility finding

| Schema variant; original instance bytes | Valid | Invalid | Unchecked |
| --- | ---: | ---: | ---: |
| Original baseline | 337 | 551 | 51 |
| hasFolder and shared expression corrections | 365 | 516 | 58 |
| Add command/CSS cardinality corrections | 365 | 516 | 58 |
| Add dependent navigator companion: final | **367** | **521** | **51** |

The shared expression correction first exposed a duplicate `enablement` in
`navigatorContent.exsd`: its unchanged local sequence no longer matched the
included core choice. Seven contributions consequently became unchecked in
the intermediate variants. They were never counted as repaired passes.

All three installed navigator consumers delegate that declaration to the same
core expression conversion. The companion changes only the local compositor's
opening and closing tags. Its generator requires the shared core choice repair
first. The seven contributions become checkable again: two are valid and five
retain other diagnostics. Baseline-to-final coverage is unchanged. The final
51 unchecked cases are 16 executable-child alternatives, 16 popupMenus
contributions with conflicting global declarations, three missing-schema
contributions, and 16 absent-provider contributions.

### Whitespace and identifier classification

`classify_findings.py` retains the original-input result and classifies its
diagnostics. The baseline has 1,623 empty-content diagnostics whose reported
character data is entirely XML whitespace; 425 contributions have only that
kind of diagnostic. An XSD-empty element prohibits even indentation text.
PDE ignores character events on this instance-validation path. This distinction
does not mean that all indentation between permitted child elements is invalid.

All 44 baseline enumeration diagnostics occur on attributes with PDE
`kind="identifier"` metadata. The literal enumeration remains enforced by the
projection; classification does not convert those diagnostics into passes.
No ordinary closed-enumeration violation was observed in this classification.

A separate sensitivity check deep-copies the instance and removes **only XML
whitespace directly diagnosed inside schema-empty elements**. It changes no
source file, schema, enumeration or ordering rule. It is labelled a
transformed-input diagnostic, not the original-input baseline or a proposed
production formatting fix.

| Whitespace sensitivity | Valid | Invalid | Unchecked |
| --- | ---: | ---: | ---: |
| Original schemas | 762 | 126 | 51 |
| hasFolder/shared-expression corrections | 816 | 65 | 58 |
| Add command/CSS corrections | 817 | 64 | 58 |
| Final with navigator companion | **819** | **69** | **51** |

There are 57 invalid-to-valid transitions in that final sensitivity comparison.
The original and final checks are not counts of broken plugins or runtime
failures; unsupported cases and metadata-specific semantics remain explicit.

## Consumer evidence and repair tests

The two extra cardinality patches are in `extra-repairs/patches/`:

* `commands.exsd`: allow 0..N `parameter` children under `defaultHandler`.
  The installed Equinox `ConfigurationElement.createExecutableExtension`
  accepts zero and collects all supplied parameters (source lines 243–260).
  Exact workbench bytecode links `HandlerPersistence` through `HandlerProxy`
  to that executable-extension API.
* CSS `elementProvider`: allow multiple providers, retaining a minimum of one.
  The installed `RegistryCSSElementProvider` iterates top-level providers and
  their widget declarations (source lines 60–76); the actual SWT contribution
  supplies three providers in one extension.

`ExtraConsumerProbe.java` uses the unchanged installed SDK and the standard
standalone registry, including real reflective class loading. Eight assertions
exercise 0/1/2 initialization parameters, an absent handler class, selection of
each of three providers from one contribution, and an unmatched object. All
eight pass. This is a focused consumer contract probe, not a full UI test.

For the dependent navigator companion, exact installed sources show
`ElementHandler.getDefault().create(ExpressionConverter.getDefault(), ...)`
in `NavigatorContentDescriptor` (269–270), `CommonActionProviderDescriptor`
(170–171) and `CommonWizardDescriptor` (179–180). The separately retained OSGi
probe exercises the shared expression consumers and hasFolder (10 assertions).

The extra schema tests first observed three positive assertion failures on
the original schemas, then seven passing methods on their repaired copies.
The companion tests first observed one compilation error and seven failed
coverage assertions on the four-repair predecessor; both companion methods
pass on the final corpus. Negative cases preserve required attributes,
unknown-child rejection, exact-one `not` cardinality and minimum provider/widget
counts. The final retained Python log contains 17 projection/classification,
five initial-repair and nine extra/companion methods, alongside 11 inventory
methods. These are 42 focused methods, distinct from the SDK consumer assertions.

## Reproduction

Commands below run from the repository root. Supply the frozen corpus produced
by the [inventory](../inventory/README.md), the reference IDE and an appropriate
JDK. Python with `lxml` is required; retained results used lxml 6.1.1 and
libxml2 2.14.6. Use fresh variant directories.

```sh
xml_study=benchmarks/xml-startup-attribution/instance-validation
xml_corpus=/path/to/frozen/corpus
xml_results=/path/to/new/results
xml_reference=/path/to/reference-ide
xml_jdk=/path/to/jdk
mkdir -p "$xml_results"

python3 "$xml_study/projection/project_grammar.py" "$xml_corpus" \
  --output "$xml_results/projected-grammar-baseline.json"
python3 "$xml_study/projection/classify_findings.py" "$xml_corpus" \
  --output "$xml_results/projected-findings-classification.json"

python3 "$xml_study/fixes/prepare_repairs.py" "$xml_corpus" \
  "$xml_results/corpus-repaired"
python3 "$xml_study/projection/extra-repairs/prepare_extra_repairs.py" \
  "$xml_results/corpus-repaired" "$xml_results/corpus-four-repaired"
python3 "$xml_study/projection/extra-repairs/prepare_extra_repairs.py" \
  "$xml_results/corpus-four-repaired" "$xml_results/corpus-final-repaired" \
  --only navigator-enablement-companion

python3 "$xml_study/projection/project_grammar.py" \
  "$xml_results/corpus-final-repaired" \
  --output "$xml_results/projected-grammar-final-repaired.json"
python3 "$xml_study/projection/classify_findings.py" \
  "$xml_results/corpus-final-repaired" \
  --output "$xml_results/projected-findings-final-repaired.json"

python3 -m unittest discover -s "$xml_study/projection" -p 'test_*.py'
XML_INSTANCE_CORPUS="$xml_results/corpus-final-repaired" \
  python3 -m unittest discover -s "$xml_study/fixes" -p 'test_schema_repairs.py'
XML_INSTANCE_CORPUS="$xml_results/corpus-final-repaired" \
  python3 -m unittest discover -s "$xml_study/projection/extra-repairs" -p 'test_*.py'
python3 "$xml_study/projection/extra-repairs/run_extra_consumer_checks.py" \
  "$xml_reference" --java-home "$xml_jdk" \
  --output "$xml_results/extra-consumer-contract-checks.json"
```

The default extra-repair command applies only the two cardinality corrections;
the companion is a separate explicit `--only` step. Running the initial/extra
schema tests on the baseline deliberately reproduces their positive failures;
running the companion tests on the four-repair predecessor reproduces the
include conflict. No original corpus is edited in place.

## Retained evidence

[`results/summary.json`](results/summary.json) contains compact counts,
transitions, coverage reasons and test provenance. The lossless
[`projection-evidence.tar.xz`](results/projection-evidence.tar.xz) retains all
four original-input audits and classifications, both transition artifacts,
variant manifests, before/final bytes of the five changed schemas, exact
consumer source/bytecode evidence, SDK probe outputs and test records.
[`results/manifest.json`](results/manifest.json) lists every member's SHA-256,
size and original source location; `SHA256SUMS` covers the archive and compact
metadata. Archive members preserve original bytes and paths recorded in JSON.

Complete console records are retained for the initial two-repair red/green
check and the final 42-method run. The extra/companion red runs are retained as
the existing structured observation records in their source-evidence JSONs,
not reconstructed console transcripts. Their original tool-session failures
and the subsequent green results are described with that provenance distinction.
Excluded standalone-expression setup results remain labelled excluded; the
successful replacement uses initialized OSGi.

```sh
cd benchmarks/xml-startup-attribution/instance-validation/projection/results
sha256sum -c SHA256SUMS
tar -xJf projection-evidence.tar.xz
```
