from pathlib import Path
import csv, json, random, statistics

root = Path(__file__).resolve().parent
results = root / 'results'
groups = {}
for path in sorted(results.glob('*-*.json')):
    if not path.stem[-1:].isdigit() or not path.stat().st_size:
        continue
    data = json.loads(path.read_text())[0]
    key = path.stem.rsplit('-', 1)[0]
    group = groups.setdefault(key, {'cpu_ms_forks': [], 'allocated_bytes_forks': [], 'wall_ms_forks': []})
    # AuxCounters EVENTS aggregate score is a sum of the iteration averages.
    # Use rawData, then take the mean per independent JVM fork.
    for metric, name in [('cpuMs', 'cpu_ms_forks'), ('allocatedBytes', 'allocated_bytes_forks')]:
        raw = data['secondaryMetrics'][metric]['rawData']
        group[name].append(statistics.mean(x for row in raw for x in row))
    group['wall_ms_forks'].append(data['primaryMetric']['score'])
for key, group in groups.items():
    for name, forks in list(group.items()):
        group[name.replace('_forks', '_mean')] = statistics.mean(forks)
        group[name.replace('_forks', '_min_max')] = [min(forks), max(forks)]

comparisons = {}
for before, after in [('upstream-original', 'reuse-original'), ('upstream-original', 'coalesced-original'),
                      ('coalesced-original', 'combined-original'), ('upstream-original', 'combined-original'),
                      ('combined-original', 'combined-safe-indented'), ('combined-original', 'combined-safe-compact'),
                      ('coalesced-original', 'woodstox-original')]:
    if before in groups and after in groups:
        comparisons[before + ' -> ' + after] = {
            metric + '_reduction_pct': 100 * (1 - groups[after][metric + '_mean'] / groups[before][metric + '_mean'])
            for metric in ('cpu_ms', 'allocated_bytes', 'wall_ms')}

cold = {}
if (results / 'cold.csv').exists():
    rows = list(csv.DictReader((results / 'cold.csv').open()))
    for provider in ('upstream', 'reuse', 'combined'):
        selected = [row for row in rows if row['provider'] == provider]
        cold[provider] = {name + '_median': statistics.median(float(row[name]) for row in selected)
                          for name in ('cpu_ms', 'wall_ms', 'allocated_bytes', 'loaded_classes')}
    baseline = {int(row['trial']): float(row['cpu_ms']) for row in rows if row['provider'] == 'upstream'}
    rng = random.Random(2535)
    for provider in ('reuse', 'combined'):
        deltas = [float(row['cpu_ms']) - baseline[int(row['trial'])] for row in rows if row['provider'] == provider]
        boot = sorted(statistics.median(rng.choices(deltas, k=len(deltas))) for _ in range(10000))
        cold[provider]['paired_cpu_delta_median'] = statistics.median(deltas)
        cold[provider]['paired_cpu_delta_bootstrap_95_pct'] = [boot[249], boot[9749]]
        cold[provider]['faster_pairs'] = sum(d < 0 for d in deltas)
summary = {'warm': groups, 'comparisons': comparisons, 'first_batch': cold}
(results / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
print(json.dumps(summary, indent=2))
