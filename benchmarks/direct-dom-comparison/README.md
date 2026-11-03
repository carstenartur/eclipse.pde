# Direct DOM comparison for PR #2575

This prototype switches **only full schema loading** to direct DOM parsing.
`Schema.load(InputStream)` delegates to `SchemaDocumentParser`. Abbreviated
schema loading continues to use the existing SAX handler and does not initialize
the additional DOM factory. Other XML model loaders are unchanged.

This branch is based on cleaned-up PR commit
`de6efde7becdbcc5515c0a45c908d2592ccd465e`. The comparison was initially developed
against `7eefc2b05869eede949f72a3e68574d2806f308d`; the timing caveat below records
that difference. It is an executable alternative for review, not a claim that
direct DOM should replace the reviewed optimisation.

## Production behaviour

- Use the real Platform `XmlProcessorFactory` to reject every DOCTYPE.
- Configure one privately owned DOM factory with namespace awareness disabled,
  comments ignored, and CDATA coalesced into ordinary text.
- Deny external DTD/schema protocols and install an empty entity resolver.
- Synchronize builder creation on that factory; each parse uses its own builder
  outside the lock. The nested factory holder avoids initialization on the
  abbreviated route.
- Remove processing instructions from the parsed root and normalize it.
  `XMLDefaultHandler` puts every PI outside the root, even a PI nested in source
  elements, and joins character data across it. `Schema` consumes only the root.
  Simply using the default DOM builder changes this tree shape.

Factory ownership was checked against the actual runtime 3.35.0 bytecode:
`createDocumentBuilderFactoryWithErrorOnDOCTYPE()` calls
`DocumentBuilderFactory.newInstance()` on each invocation. Its similarly named
`createDocumentBuilderWithErrorOnDOCTYPE()` instead uses a shared cached
factory. The prototype does **not** change flags on Platform's shared factory.
The compatibility harness also checks that the Platform default builder still
retains comments and CDATA after the prototype factory has been used.

## Reproduce

Requirements: JDK 25 and an actual `org.eclipse.core.runtime` 3.35.0 jar
(or another version exposing the same factory API).

```bash
JAVA_HOME=/path/to/jdk-25 \
ECLIPSE_RUNTIME_JAR=/path/to/org.eclipse.core.runtime-3.35.0.jar \
bash benchmarks/direct-dom-comparison/run.sh 500
```

Use `--check` instead of `500` to run only the compatibility checks.

The script compiles the production handler, prototype parser and two standalone
Java programs into a temporary directory. It generates no replacement Platform
classes. The `Schema.java` integration is a one-line delegation; this focused
script does not compile the entire PDE bundle or run Tycho/OSGi tests.

The compatibility program recursively compares every root node, attribute,
character value, node type and namespace property with the production SAX
handler. It checks all **21 repository EXSD files in both modes**, plus nine
synthetic fixtures covering mixed content, exact whitespace, CDATA, comments,
leading/nested/trailing PIs, qualified names, namespace declarations, Unicode,
entities and long text. Literal assertions additionally check the expected
flattened text and abbreviated result. Malformed XML, undefined entities and
DOCTYPEs containing internal/external declarations must throw `SAXException`
in both modes. Forty concurrent parses check that builders remain independent.

Before implementing the compatibility configuration, the same tree comparison
was run against Platform's unconfigured direct DOM builder. It failed on the
first mixed-content fixture with `AssertionError: /child[1]/ child count`,
because CDATA was a separate node. The completed parser passed **81,322 checks**.

## Measured comparison

Recorded environment: OpenJDK 25.0.5+8, Platform runtime 3.35.0, fixed 256 MiB
heap, JDK built-in XML provider. Corpus bytes are preloaded; file I/O and schema
model conversion are excluded. Each measurement parses all 21 files in full
mode, then walks every root, attribute and descendant, consuming a checksum.
The prototype's PI-removal and normalization pass is included. Both routes
produce checksum `-7602512830363663866`.

After 500 warmup corpus loads per parser, eight measured rounds use 500 corpus
loads per parser per round, alternating execution order. CPU time and allocated
bytes come from the current thread's management counters. Results are per
complete 21-file corpus:

| Route | Median CPU | Round range | Median allocated bytes |
| --- | ---: | ---: | ---: |
| Patched SAX handler | 1.983 ms | 1.886–2.183 ms | 1.865 MiB |
| Direct DOM prototype | 2.071 ms | 1.977–2.258 ms | 2.302 MiB |

Raw output is in `results.tsv`. An initial run with only 50 warmup loads and 100
measured loads showed JIT drift and is retained in `pilot-results.tsv`; that
specific uncertainty motivated the longer warmup. The reported values are one
process on one runtime, not a statistical claim that either route is faster.
The CPU ranges overlap, and allocation is higher for this compatibility-preserving
direct DOM implementation. They are not startup timings or a measurement of the
cached abbreviated registry path. This is not a JMH benchmark, and no old-handler
baseline is measured here.
The recorded timings preceded the redundant final-flush removal; compatibility
was rerun after that cleanup. The final-flush removal is not timed separately.

## Concrete complexity comparison

`Schema.java` removes nine physical lines and adds one. The new package-private
parser is **86 physical lines**, including its license, imports, whitespace and
comments. Relative to the cleaned-up PR, the schema parser integration adds a net
**78 physical production lines**. Its responsibilities
are abbreviated dispatch, an owned/lazy/configured DOM factory, builder creation,
and compatibility treatment of PIs. `XMLDefaultHandler` remains necessary for
abbreviated mode and the other model loaders; this limited prototype does not
remove it or its existing normalization code.

Thus direct DOM makes the immediate `Schema.load` method shorter, but this
particular compatibility-preserving, schema-only alternative does not reduce
the repository's total parser code. Removing the PI compatibility treatment
would simplify it by changing observable root structure and documentation
text around nested PIs. Removing abbreviated SAX would require an alternative
that avoids character-data allocation, or an explicit acceptance of allocating
then discarding that text.

Generalising the alternative to product, feature and site loaders requires
preserving their separate `XMLCopyrightHandler` extraction of the first comment
seen with an empty element stack. Those loaders also receive a whole Document;
their PI/comment contract is broader than the root-only schema contract. That
work, and switching the composite cheat-sheet and schema-conversion callers,
is deliberately outside this concrete comparison.

No startup improvement, universal speedup, whole-PDE build success, or simplified
replacement of every XML loader is claimed by this prototype.
