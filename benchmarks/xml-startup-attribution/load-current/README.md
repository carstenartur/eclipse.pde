# Current-source loading and work counters

This follow-up checks the actual 4 November branch sources against the preserved,
hash-verified October corpus and dependencies. It is a full schema-model loading
experiment, not an Eclipse startup benchmark. The companion
`xml-performance-org.eclipse.ui-2026-10-24.zip` contains the exact offline inputs.

Four implementations hold dependencies and original input bytes constant:

- Baseline: `f948c57878a1a011625b5214d63a1ec01bd243ff`.
- Coalesced: handler from `de6efde7becdbcc5515c0a45c908d2592ccd465e`.
- Reuse: `Schema` and `SchemaReader` from `eedb94d809215598b39d53f711733e0313e04fbe`.
- Combined: both source substitutions above.

The remaining fixes have independent regression tests. This experiment does not
silently count their correctness benefits as measured loading speedups. It does
not exercise `StorageSchemaDescriptor`, missing JAR entries, or schema writing.

## Run

Requirements: Node.js, Git, unzip and JDK 25. All three pinned commits must be in
the supplied Git object database. Unpack the companion archive without changing
its `xml-followup` contents, and verify `SHA256SUMS` before proceeding.

```sh
node run.cjs prepare --repo /path/to/eclipse.pde \
  --archive /path/to/xml-followup --java-home /path/to/jdk25 --out /path/to/results
node run.cjs diagnose --out /path/to/results
node run.cjs measure --out /path/to/results --blocks 3 --label originals
```

`prepare` compiles the actual source overlays and unchanged archived JMH driver.
Before timing, all 49 real model serializations must agree across implementations.
The driver's literal mixed-content, malformed XML and five DOCTYPE rejection and
recovery controls run as part of validation. Each timed operation loads all 49
top-level schemas plus 15 real include loads through `SchemaDescriptor` and the
actual PDE schema model. The workload has 229 top-level model elements.

Each case in each block runs in a fresh JVM with 8 x 2 seconds warmup and 6 x 1
second measurement, Serial GC, a 512 MiB heap and one active processor. Case order
rotates and reverses between blocks. Optional `--cpu N` pins the parent and child
JVMs to one allowed Linux CPU; it does not reserve that CPU from other processes.
Use fork/block means as observations, not six iterations as six independent JVMs.
CPU and allocation values must come from JMH auxiliary counters' `rawData`; their
aggregate `score` is not the per-operation mean in this driver.

To compare a newly formatted copy of the same corpus, preserve its directory
layout and use `add-corpus --name compact --source /path/to/formatted --out ...`.
The tool rebuilds every corpus JAR with a common fixed timestamp and verifies
model parity before recording a comparison. Then include cases explicitly, e.g.
`--cases combined:original,combined:compact`. Every new corpus needs its formatter
source revision, policy settings and transformation checks recorded alongside it.

## Work counters

`SaxDomWork` deliberately uses reflection to inspect the real handler's DOM before
its public getter normalizes adjacent text nodes. It uses PDE's actual JDK parser
factory. It then counts normalized nodes and hashes a length-delimited DOM
representation with sorted attributes. These intrusive diagnostics are separate
from JMH and are not timing measurements. They cover only the 49 top-level files;
the full-model timing additionally loads the referenced schemas.

For identical bytes, baseline and coalesced runs must have identical character
callbacks, character units, normalized text-node counts and DOM hashes. This
directly tests the distinction between SAX events and temporary DOM nodes. It
does not count lexical comment callbacks, disk reads or every XML consumer in
Eclipse. The companion startup trace agent addresses those broader paths.

Output records include pinned source hashes, corpus hashes, compile logs, all
validation logs, explicit schedules and complete per-fork JMH JSON/console logs.
The machine is shared; treat observed CPU changes as workload-specific evidence
and retain uncertainty. These results cannot establish an IDE startup percentage.
