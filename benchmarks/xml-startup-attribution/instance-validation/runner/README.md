# Native PDE extension-instance validation

This diagnostic application invokes the installed PDE `ExtensionsErrorReporter`
through `DefaultSAXParser.parse` and `validateContent`. This is the reporter
selected by `ManifestConsistencyChecker` for modern bundles with a
`META-INF/MANIFEST.MF`. No extension grammar rules are reimplemented in the
application. Its subclass observes the superclass's diagnostics and associates
them with extension contributions.

The runner imports an explicitly listed corpus into a fresh headless Eclipse
workspace, using a private copy of the reference installation and corpus. It
checks every root `plugin.xml` and `fragment.xml`; projects containing schema
providers are imported as well. Original descriptor, manifest, schema and
properties bytes are hashed before and after the run. Project metadata and
preferences are disposable fixture settings.

## Run

```bash
python3 run_validation.py \
  --reference /absolute/path/to/reference-eclipse \
  --corpus /absolute/path/to/instance-corpus \
  --java-home /absolute/path/to/jdk \
  --output /absolute/path/to/new-run-directory
```

The corpus must contain `project-list.txt`, with absolute project directories
beneath the corpus root. Those directories contain their real manifests,
descriptors and available matching schemas. The runner copies this input and
rewrites only the copied project list. Existing nonempty output directories are
rejected. No shared Maven-cache artifact or reference-installation file changes.

The application does not launch the UI, measure startup time, build Java, or
enable automatic building. `build_runner.py` compiles against actual reference
SDK bundles and records source/artifact hashes. A dependency manifest may emit
the existing `org.sat4j.core.jar` javac path warning; no replacement dependency
is introduced for it.

## Scope and effective preferences

The four structural categories are explicitly set to `CompilerFlags.ERROR`:

- `compilers.p.unknown-element`
- `compilers.p.unknown-attribute`
- `compilers.p.no-required-att`
- `compilers.p.unresolved-ex-points`

Java class lookup, discouraged classes, resource lookup, NLS, identifier-reference
lookup, deprecation and internal-use warnings are explicitly ignored. Reduced
projects contain no complete Java classpath or binary resource tree; presenting
those findings as production errors would be misleading. Preferences are written
to the real `CompilerFlags` qualifier, `org.eclipse.pde`, and read back through
`CompilerFlags.getFlag` before validation. Raw marker severities therefore reflect
this deliberate configuration, not the reference IDE's default warning levels.

Raw results distinguish completed validation from a valid input. All diagnostics
are retained per file; extension-related diagnostics are also attributed to the
point ID and source line. The exact descriptor set and contribution count must
match the copied input. Process failure, missing output, changed input hashes,
Eclipse error-log entries or failing harness controls reject a run.

The application records all registered PDE models and their locations because
the target registry can contain models beyond the configured input corpus.
Provider/source URLs are captured for every referenced point. A separate
post-validation lookup records whether its declaration, schema URL, model and
extension root exist, and whether the actual `Schema` is loaded/valid. Missing
schemas and unknown points are coverage gaps, never silently counted as validated
inputs. These supplemental lookups are not a count of parsing during validation.

## Controls and known validator limitations

A separate disposable singleton PDE project provides the controls; the original
production files are never mutated for controls. Three valid grammar comparators
and two valid alternatives in a complex choice must have no markers. Unknown
attributes/children, missing required attributes, minimum/maximum cardinality,
invalid enumeration and an unknown point must be detected. Missing and undeclared
schemas must be classified as coverage gaps.

Additional deliberately invalid inputs observe boolean lexical validation,
sequence order, character content, and two nested-choice shapes. An invalid input
accepted without a diagnostic is recorded as a validator limitation; it is not
called valid or hidden by the successful harness status. Thus passing these
controls does not mean that PDE provides complete W3C XSD validation.

## Optional production-resource retry and handle diagnostic

Add `--repeat-load-probe` to run a separate diagnostic after validation. It uses
actual `SchemaRegistry` URLs for the two previously missing production resources
and a valid `applications.exsd` comparator. In each full/abbreviated case a real
SDK `SchemaDescriptor` is retained with its model for an initial load plus 24
queries, rotating `findElement`, `getElements` and `getResolvedElements`.

A per-URL observing connection counts actual `getInputStream` attempts, successful
streams, closures and exception types/messages. Real I/O is delegated to the
original connection. JAR connections remain `JarURLConnection` instances, cache
settings propagate to the delegate, and `getJarFile` delegates unchanged, retaining
the PDE close path. The deprecated per-URL constructor is intentionally used in
this diagnostic because `URL.of` rejects a custom `file:` handler. No globally
registered protocol handler or production class is modified.

The Linux handle check counts only the specific underlying file/JAR target,
resolving symlinks. It records before/after counts and verifies a real positive
control by opening that same target, observing one extra handle and closing it.
No garbage collection is requested. A preexisting target handle is shown as such;
unchanged counts do not establish who owns it. None of these counts or diagnostic
process durations are reported as Eclipse startup savings.

## Consumer contract check

The separate `consumer-probe` application runs the unchanged
`../fixes/ConsumerContractProbe.java` inside initialized Eclipse OSGi. The helper
retains its existing command line:

```bash
python3 ../fixes/run_consumer_checks.py /absolute/path/to/reference-eclipse \
  --java-home /absolute/path/to/jdk \
  --output /absolute/path/to/new-consumer-result.json
```

The seven core-expression composites must retain three supplied children and
evaluate them successfully. The `hasFolder` checks cover an existing directory,
a regular file and an absent path. Output captures the unchanged probe's source
hash, actual SDK code sources and bundle versions, platform initialization, every
check, process status and the Eclipse log. The previous standalone-classpath
attempt is retained as excluded setup evidence because `adapt` needs Eclipse's
initialized platform. Neither this probe nor its launcher changes the native
validation application or its comparison results.
