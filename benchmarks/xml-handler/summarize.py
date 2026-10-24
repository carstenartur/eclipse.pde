#!/usr/bin/env python3
"""Summarize already-normalized JMH auxiliary counters from raw iteration data."""
import json
import math
from pathlib import Path
import statistics
import sys

path = Path(sys.argv[1])
results = json.loads(path.read_text())
assert len(results) == 2
summary = {}
for result in results:
    assert result['forks'] == 3 and result['measurementIterations'] == 6
    mode = result['params']['mode']
    summary[mode] = {}
    metrics = result['secondaryMetrics']
    for variant in ['Original', 'Compact']:
        row = {}
        for implementation in ['baseline', 'patched']:
            for suffix, label in [('Cpu', 'cpu_ms'), ('Bytes', 'allocated_bytes')]:
                data = metrics[implementation + variant + suffix]['rawData']
                assert len(data) == 3 and all(len(f) == 6 for f in data)
                assert all(math.isfinite(v) and v > 0 for f in data for v in f)
                forks = [statistics.mean(f) for f in data]
                row[implementation + '_' + label] = statistics.mean(forks)
                row[implementation + '_' + label + '_by_fork'] = forks
        differences = [a-b for a, b in zip(row['baseline_cpu_ms_by_fork'], row['patched_cpu_ms_by_fork'])]
        mean = statistics.mean(differences)
        margin = 4.302652729911275 * statistics.stdev(differences) / math.sqrt(3)
        row['cpu_saved_ci95'] = [mean-margin, mean+margin]
        row['cpu_reduction_pct'] = 100 * (1 - row['patched_cpu_ms'] / row['baseline_cpu_ms'])
        row['allocation_reduction_pct'] = 100 * (1 - row['patched_allocated_bytes'] / row['baseline_allocated_bytes'])
        summary[mode][variant.lower()] = row
        print(f"{mode}/{variant}: {row['baseline_cpu_ms']:.3f} -> {row['patched_cpu_ms']:.3f} ms; "
              f"CPU reduction {row['cpu_reduction_pct']:.1f}%; allocation reduction {row['allocation_reduction_pct']:.1f}%")
path.with_name('summary.json').write_text(json.dumps(summary, indent=2) + '\n')
