# XML instances, extension schemas and repeated loading

Study date: 2026-11-03. This follow-up extends the [original XML/startup
study](../README.md) from schema documents to the actual extension contributions
in `plugin.xml` and `fragment.xml`. It uses the same frozen reference IDE.
The original PR [eclipse-pde/eclipse.pde#2575](https://github.com/eclipse-pde/eclipse.pde/pull/2575)
and its text-coalescing implementation are unchanged.

## Findings

The user's observation that a standard XML validator can reject Eclipse XML
against its associated schema is reproducible with concrete examples. The
earlier zero-marker SchemaBuilder result did not test these XML instances.
There are several different causes; they must not be combined into a count of
broken plugins or attributed automatically to startup latency.

* The real PDE instance reporter emits **119 diagnostics** over **939 extension
  contributions in 83 original plugin.xml files**. Sixteen are missing-provider
  coverage findings in this assembled reference. Other findings include genuine
  inconsistencies between schemas and the runtime consumers.
* An explicitly bounded standards-based grammar projection rejects 551 of those
  contributions, accepts 337, and leaves 51 unchecked. **425 contributions fail
  solely because whitespace appears inside elements whose declared content is
  empty.** This is a much more precise result than calling those plugins broken.
* Four small schema corrections, across five schema files, are prepared as
  separate patches. Their
  consumers support the existing XML; changing the XML to satisfy the erroneous
  schema would therefore be the wrong repair. The original instance bytes are
  unchanged in all repair comparisons.
* Two genuinely missing production schema resources exercise a repeated-load
  path: an initial load plus 24 model queries makes **25 failed input-stream
  attempts per missing resource**, in both full and abbreviated mode. Restoring
  the authentic files reduces this to **one successful load**. These resources
  were already included by upstream packaging fixes on 2026-10-23.
* No growth in handles to the tested files/JARs occurs in that diagnostic.
  One source JAR already has a handle before its trial; unchanged counts do not
  identify its owner or prove that every Eclipse handle is closed.
* These are validation, correctness and operation-count results. They establish
  neither seconds saved during Eclipse startup nor the share of startup latency
  attributable to each correction. The earlier GUI study still provides no
  statistically clear startup improvement in its prepared-workspace scenario.

## Exact coverage and three different checks

The inventory follows the actual `bundles.info` configuration, not every JAR
found in the installation. It contains 243 configured entries: 50 source entries,
192 production binary entries and one explicitly excluded observer from the
previous experiment. Source resources must match their binary host and version.
Both JAR and unpacked bundles are supported.

| Input or mapping | Count |
| --- | ---: |
| Original descriptor files | 83 plugin.xml; 0 fragment.xml present |
| Extension contributions | 939 |
| Extension-point declarations | 293 |
| Original EXSD resources | 298 from 57 providers |
| Contributions with a loadable associated schema model | 920 |
| Contributions with a declared but missing schema resource | 3 |
| Contributions whose extension-point provider is absent | 16 |
| XML syntax errors in inventoried descriptors/schemas | 0 |

Platform, Equinox, JDT, PDE, EMF and the other configured contributors are
included; this is not restricted to PDE's own schemas. The 16 absent-provider
contributions target `org.eclipse.ui.trace.traceComponents` (14) and
`org.eclipse.help.base.searchParticipant` (2). They are not counted as validated.
This is an assembled reference, not a claim about every Eclipse product or the
user's historical installation.

The three checks answer different questions:

| Check | What it establishes | Result on original inputs |
| --- | --- | --- |
| Raw W3C XSD compilation | Can an unchanged EXSD itself be compiled as standard XSD 1.0? | 1 compiles; 297 do not |
| Actual PDE `ExtensionsErrorReporter` | What does the installed PDE instance validator report with explicit grammar checks enabled? | 119 diagnostics; 920 contributions have loaded schema models |
| Bounded EXSD grammar projection | What additional supported structural/type constraints does a standard XSD engine detect after declared dialect adaptations? | 337 accepted, 551 rejected, 51 unchecked |

All 298 EXSDs are well-formed XML. Their raw XSD compilation failures include
legacy `appInfo`, `use="default"`, and namespace conventions. No missing local
include caused those compilation failures. These are not 297 demonstrated PDE
load failures. PDE documents a limited schema feature set and does not support
XML namespaces in extension-point grammars; see the [official schema editor
documentation](https://help.eclipse.org/latest/topic/org.eclipse.pde.doc.user/guide/tools/editors/schema_editor/editor.htm).

The native run uses the real SDK `ExtensionsErrorReporter`, `DefaultSAXParser`,
`SchemaRegistry` and schema models in a real headless OSGi application. This is
the reporter selected for modern bundles by `ManifestConsistencyChecker`.
Unknown elements/attributes, missing required attributes and unresolved points
are deliberately configured as errors. Java classpaths, resources, NLS and
identifier references are outside this reduced fixture and are explicitly
excluded. The **119 error severities are experiment settings**, not a statement
about the IDE's default marker preferences.

Nineteen independent control cases exercise the native reporter. They verify
normal valid inputs, rejected bad attributes/children/cardinalities/enumerations,
and explicit missing-schema coverage. They also demonstrate that the reporter
can accept bad boolean text, reversed sequence order, prohibited character
content, and one complex nested-choice shape without a diagnostic. Another
nested-choice shape is detected. Passing the harness therefore means that the
observed behavior matches the controls, not that PDE implements full XSD
validation. See [runner documentation](runner/README.md) and its recorded
control diagnostics.

The supplemental projection removes annotations, translates the supported
legacy default notation, resolves only inventoried local/schema includes and
qualifies built-in XSD types. It preserves sequence/choice, occurrence bounds,
required attributes and enumeration constraints. Unsupported executable-child
syntax, ambiguous global declarations and unresolved providers remain unchecked.
All schema inputs, including included files, are hash-verified. This is not
Altova XMLSpy, not a complete EXSD-to-XSD converter, and not an assertion that
the user's exact historical diagnostics have been reproduced.

## Why a strict validator complains about whitespace

One original example is the `org.eclipse.ant.core` contribution to
`org.eclipse.ant.core.extraClasspathEntries`:

```xml
<extraClasspathEntry library="lib/antsupportlib.jar">
      </extraClasspathEntry>
```

Its schema gives the element attributes but no content. Under the XSD rule for
an empty content type, even that newline and indentation are character content;
the compact `<extraClasspathEntry library="lib/antsupportlib.jar"/>` satisfies
the empty-content requirement. PDE's instance reporter ignores character events
on this path. See the [W3C element-content validity rules](https://www.w3.org/TR/xmlschema-1/#cvc-complex-type).

The original-input projection records 1,623 such diagnostics. All their
character data consists only of XML whitespace. For 425 contributions these
are the only diagnostics. Thirty-one descriptor files have reported diagnostics
only in this category; unchecked contributions inside those files remain
unchecked.

A separately labeled diagnostic deletes only those specifically diagnosed
whitespace nodes in in-memory copies. It changes the result from
**337 / 551 / 51** to **762 / 126 / 51** (accepted / rejected / unchecked),
removing 14,469 characters. No production file was reformatted. This comparison
explains a validator discrepancy; it does not measure parsing speed.

The other projected diagnostics include 44 enumeration findings on attributes
marked by PDE as `kind="identifier"`. All 44 use that metadata path, such as a
perspective target declared with `*` but supplied as an actual identifier.
The projection retains the literal enumeration; it does not silently relax the
schema to turn these into passes. There are zero observed violations of an
ordinary closed enumeration in this classification. Another 263 diagnostics
are structural and require case-by-case interpretation.

Replacing spaces with tabs leaves whitespace character content in an empty
element and therefore does **not** fix this particular conformance issue.
Whitespace-only content between permitted child elements is a different case.
The previous narrowly scoped formatting experiment remains separate.

## Concrete schema repairs and consumer evidence

The patches are independently reviewable. `fixes/prepare_repairs.py` applies the
first two to a new corpus; `projection/extra-repairs/prepare_extra_repairs.py`
adds the other two and a dependent navigator companion. Every input descriptor
stays byte-identical. Hashes and
upstream paths are recorded in the variant manifests.

| Repair | Evidence for the intended contract | Scope |
| --- | --- | --- |
| [Declare `hasFolder`](fixes/has-folder.patch) in projectConfigurators.exsd | The real plugin.xml uses it; `FileExpressionHandler` recognizes it and `HasFolderExpression` tests a directory at the required relative path | Add the missing element and reference, retaining required `path` |
| [Use repeated choices](fixes/expression-choices.patch) in expressionLanguage.exsd | `ExpressionConverter` accepts arbitrary expression children in seven composite expressions; the original repeated sequence requires every listed alternative in order | Replace seven sequence compositors by choices; retain occurrence limits; align the [navigator's copied enablement declaration](projection/extra-repairs/patches/navigator-enablement-companion.patch) |
| [Allow 0..N initialization parameters](projection/extra-repairs/patches/default-handler-parameters.patch) in commands.exsd | Two existing defaultHandler contributions omit parameters; the real registry's executable-extension implementation handles zero, one or several | Correct only the `parameter` occurrence bounds |
| [Allow multiple CSS providers](projection/extra-repairs/patches/multiple-element-providers.patch) | The SWT contribution supplies three providers; `RegistryCSSElementProvider` iterates all of them | Change only provider maximum occurrence; retain its minimum |

The seven expression composites are `enablement`, `and`, `or`, `with`,
`resolve`, `adapt` and `iterate`. For example, the existing runtime accepts an
`and` containing `equals` and another `and`, while the literal original schema
requires the sequence to begin with `not` and then contain all alternatives.

All five original schema files also match the retrieved upstream files at the
pinned platform/UI revisions inspected on 2026-11-03. The byte comparisons and
revision IDs are recorded in `results/upstream-schema-comparison.json` and
`results/core-ide-upstream-comparison.json`. The new schema corrections are
therefore distinct from the already merged resource-packaging fixes below.

Focused positive and negative grammar tests fail for the relevant positive
examples on the frozen schemas and pass on their repaired copies. Tests retain
rejections for missing required attributes, unknown children, and invalid `not`
or provider counts. Separate consumer probes use unchanged installed SDK
classes. The expression/hasFolder probe runs inside initialized OSGi; the
executable-extension/CSS probe uses the standard registry. These are targeted
contract checks, not a full Eclipse/Tycho suite.

The native diagnostic comparison and stricter projection transitions are
retained with the results. The hasFolder repair removes its one native marker;
the expression-compositor change does not remove the legacy popupMenus markers.
The latter must not be presented as a global popupMenus repair.

| Native run, with identical reporter and preferences | Diagnostics | Loaded-schema contributions | Missing-schema contributions |
| --- | ---: | ---: | ---: |
| Original inputs | 119 | 920 | 3 |
| hasFolder and shared expression corrections | 118 | 920 | 3 |
| Add command/CSS cardinality corrections | 115 | 920 | 3 |
| Add navigator companion: final schema-repair variant | 115 | 920 | 3 |
| Separately restore only the two missing resources | 119 | 923 | 0 |

Each run contains the same 83 descriptors and 939 contributions, the same
16 absent-provider cases, 19 passing harness controls, zero Eclipse error-log
entries and unchanged input hashes. The final 115 native diagnostics consist
of the 99 popupMenus findings and the 16 absent-provider findings. The repaired
native markers are exactly one hasFolder, two defaultHandler and one CSS
provider marker.

The original-input strict projection changes from **337 / 551 / 51** to
**367 / 521 / 51** after all five schema-file repairs: exactly 30 contributions
move from rejected to accepted, with no loss of coverage. The separately labeled
whitespace sensitivity changes from **762 / 126 / 51** to **819 / 69 / 51**.
These are conformance counts, not speed measurements. Raw diagnostics and an
explicit contribution-by-contribution transition matrix remain available.

### Compatibility check on the shared expression correction

An intermediate version with four changed files exposed a duplicate
`enablement` declaration in `navigatorContent.exsd`. It had been identical to
the shared grammar and could be deduplicated; after correcting only the shared
grammar, the conservative projection correctly refused seven contributions
because the declarations differed. They were never counted as repaired.

The exact installed navigator consumers use the same core `ExpressionConverter`
for that declaration. The companion patch changes only the local compositor's
opening and closing tags, restoring consistency with the shared choice. Its
generator requires the shared correction first. All seven contributions become
checkable again: two are accepted, and five retain other diagnostics. Those
remaining findings are retained. The intermediate comparison is preserved to
make this compatibility check reviewable.

### Findings deliberately left unresolved

`popupMenus.exsd` includes both the legacy common-expression grammar and the
core-expression grammar. They define globals with the same names but different
contents. The consumer uses legacy `ActionExpression` for `visibility` and core
`ExpressionConverter` for object-contribution `enablement`. Changing the include
order or globally substituting all such declarations would not establish the
correct contextual grammar. The native baseline has 99 diagnostics in this
area; they are not 99 proven runtime failures.

One JDT Debug contribution has two `visibility` children. The corresponding
consumer assigns the visibility test repeatedly, so the later one replaces the
earlier one. This deserves a separate correctness decision: the intended
combination of conditions is not established, so no AND/OR rewrite was invented.

The authentic p2 verifier schema contains stale Java `basedOn` metadata naming
`org.eclipse.equinox.p2.metadata.analyzer.IIUAnalysis`; the real consumer expects
`org.eclipse.equinox.p2.repository.tools.analyzer.IIUAnalyzer`. This is recorded
without altering the authentic restoration comparison. It was not included in
the deliberately limited native grammar preferences.

## Missing resources: a demonstrated source of repeated work

The exact binary manifests identify source commits containing two resources
omitted from their binary and source packages:

| Resource | Contributions affected |
| --- | ---: |
| externaltools `schema/configurationDuplicationMaps.exsd` | 2 |
| p2 repository tools `schema/org.eclipse.equinox.p2.repository.tools.verifier.exsd` | 1 |

The schema registry returns a URL into the matching source JAR, but the entry
does not exist. Its retained model stays unloaded. The diagnostic uses the real
SDK `SchemaDescriptor` and those actual registry URLs, counting delegated
`getInputStream()` attempts without replacing the production loader. It checks
both full and abbreviated modes, with an initial load and 24 subsequent model
queries.

| Per-resource diagnostic | Missing original resource | Authentic resource restored |
| --- | ---: | ---: |
| Input-stream attempts | 25 | 1 |
| FileNotFoundExceptions | 25 | 0 |
| Model loaded after the queries | No | Yes |
| Successful stream closed | No successful stream | Yes |

The valid `applications.exsd` comparator opens once in both variants. Restoring
both resources raises loaded-schema contribution coverage from **920 to 923**;
the 16 absent-provider contributions remain gaps. The restoration uses exact
source bytes from the frozen binaries' `Eclipse-SourceReferences` commits,
verified against independent historical and packaging-fix revisions.

This is already fixed upstream by [platform commit 11c6900](https://github.com/eclipse-platform/eclipse.platform/commit/11c69009825fac418d1bf9668b887da1413d0a72)
and [p2 commit b97f8c8](https://github.com/eclipse-equinox/p2/commit/b97f8c833af78b65eacf7a9c4e59d8aad0fb0240),
both dated 2026-10-23. The experiment restores their resource availability in
the older reference; it does not propose duplicating those upstream fixes.

The before case accesses a missing JAR entry; the restored workspace model uses
a real file. Therefore these are reproducible failure/retry counts, not a
controlled file-versus-JAR throughput benchmark. In particular, **25 is the
chosen diagnostic workload, not a measured number of queries during startup**.

Target-specific `/proc/self/fd` counts do not grow during any case. A positive
control opens each same target, observes one additional handle and verifies
that it disappears on close. The externaltools source JAR starts and finishes
with one preexisting handle; the missing p2 source JAR starts and finishes at
zero. JAR caching is disabled on the observed delegated attempts. No forced GC
is used. This supports no added retained handle in these exercised paths on
Linux/JDK 25; it cannot rule out other paths or historical Windows locking bugs.

## Interpretation for startup and PR #2575

Loading a bundle's extension declarations and loading its development-time
EXSD model are separate activities. The existence of a schema in every plugin
does not establish that the full schema loader processes all of them during
every startup. The earlier prepared-workspace observation saw its schema-model
loads only after an explicitly requested SchemaBuilder run.

This follow-up supplies concrete evidence that a real failed schema load can
be repeated even on the abbreviated path. Supplying the resource removes that
work. It does not establish how often a particular startup requests those
models, what fraction of elapsed startup time they consume, or an additive
percentage contribution for each measure. No further GUI timing series was
mixed into this correctness investigation. The original 20-run GUI data and
its uncertainty remain in the parent report.

Likewise, changing a schema to match an already supported runtime grammar
improves validation and documentation. It need not change runtime execution at
all. Smaller inputs, fewer transient allocations, fewer failed loads, better
validation coverage and faster workbench readiness are separate outcomes.

For PR #2575, these findings give useful follow-up issues and concrete schema
patches. They do not turn its measured full-load saving into a demonstrated
startup saving. The existing PR's benchmark denominator remains one complete
pass over its schema corpus, not a per-schema saving.

## Reproduction and retained evidence

See [inventory instructions](inventory/README.md), [native runner instructions](runner/README.md)
and [projection/repair instructions](projection/README.md). The original corpus and repaired variants
have separate manifests. Losslessly compressed raw results include exact
diagnostics, effective preferences, schema coverage, controls, before/after
hashes and provider URLs; compact summaries are readable without extraction.
The [combined summary](results/summary.json) verifies the five native runs use
identical reporter builds, preferences and descriptor bytes. The final check
ran 42 Python test methods (11 inventory, 17 projection/classification, 5 initial
repairs, 9 additional/companion repairs); all passed. The two SDK consumer
probes passed 10 and 8 contract checks respectively. These counts are distinct
from the 19 native-reporter control cases in each comparison run.

Use a new output directory for every variant. The common order is inventory,
raw-XSD audit, native baseline, bounded projection, separate repair/restoration
copies, and the same validators against those copies. The reference installation
and original corpus are never edited in place.

Initial harness setup failures, including an attempted plain-Java expression
probe that lacked the initialized platform adapter manager, are excluded from
successful result sets. The successful replacement runs that exact consumer
probe in OSGi. Experiment tool tests and targeted SDK probes are reported as
such; a full Tycho build was not run for these experiment-only additions.
