#!/usr/bin/env node
// SPDX-License-Identifier: EPL-2.0
// Analyze complete, paired four-block runs using fresh JVMs as observations.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const directory = path.resolve(process.argv[2] || '.');
const label = process.argv[3] || 'balanced-v2';
if (!/^[a-z0-9-]+$/.test(label)) throw Error('Unsafe label');
const read = name => JSON.parse(fs.readFileSync(path.join(directory, name), 'utf8'));
const hash = name => crypto.createHash('sha256').update(fs.readFileSync(path.join(directory, name))).digest('hex');
const mean = values => values.reduce((a, b) => a + b, 0) / values.length;
const schedule = read(`schedule-${label}.json`);
const observations = read(`observations-${label}.json`);
if (schedule.blocks !== 4) throw Error('This analysis uses t(3); exactly four blocks are required');
if (observations.length !== schedule.schedule.length) throw Error('Incomplete run');
if (hash(`executed-runner-${label}.cjs`) !== schedule.runnerSha256) throw Error('Executed runner hash mismatch');
const key = value => `${value.variant}:${value.corpus}`;
const cases = [...new Set(schedule.schedule.map(key))];
if (observations.length !== 4 * cases.length) throw Error('Incomplete case matrix');
for (let block = 0; block < 4; block += 2) {
  const first = schedule.schedule.filter(x => x.block === block).map(key);
  const second = schedule.schedule.filter(x => x.block === block + 1).map(key).reverse();
  if (JSON.stringify(first) !== JSON.stringify(second)) throw Error('Unbalanced paired order');
}
const rows = observations.map((record, index) => {
  const expected = schedule.schedule[index];
  if (record.block !== expected.block || key(record) !== key(expected)) throw Error('Schedule mismatch');
  const raw = read(`${record.label}.json`);
  if (raw.length !== 1) throw Error('Expected one JMH record per fork');
  for (const metric of ['cpuMs', 'allocatedBytes']) {
    const values = raw[0].secondaryMetrics[metric].rawData.flat();
    if (values.length !== 6 || values.some(x => !Number.isFinite(x) || x <= 0)) throw Error('Invalid raw measurements');
    if (JSON.stringify(values) !== JSON.stringify(record.values[metric])) throw Error('Observation differs from raw JMH');
  }
  return {block: record.block, case: key(record), label: record.label,
    cpuMs: mean(record.values.cpuMs), allocatedBytes: mean(record.values.allocatedBytes),
    rawJsonSha256: hash(`${record.label}.json`), consoleLogSha256: hash(`${record.label}.log`)};
});
const cells = Object.fromEntries(cases.map(name => {
  const values = rows.filter(x => x.case === name);
  if (values.length !== 4 || new Set(values.map(x => x.block)).size !== 4) throw Error('Repeated or missing block');
  return [name, {forks: values.length, cpuMs: mean(values.map(x => x.cpuMs)),
    allocatedBytes: mean(values.map(x => x.allocatedBytes)),
    cpuMsByBlock: values.map(x => x.cpuMs), allocatedBytesByBlock: values.map(x => x.allocatedBytes)}];
}));
const t975df3 = 3.182446305;
function contrast(reference, treatment) {
  if (!cells[reference] || !cells[treatment]) return null;
  const metrics = {};
  for (const metric of ['cpuMs', 'allocatedBytes']) {
    const differences = Array.from({length: 4}, (_, block) =>
      rows.find(x => x.block === block && x.case === reference)[metric] -
      rows.find(x => x.block === block && x.case === treatment)[metric]);
    const average = mean(differences);
    const sd = Math.sqrt(differences.reduce((sum, x) => sum + (x - average) ** 2, 0) / 3);
    const margin = t975df3 * sd / 2;
    metrics[metric] = {savings: average, savingsPercentOfReferenceMean: 100 * average / cells[reference][metric],
      descriptive95Interval: [average - margin, average + margin], pairedDifferences: differences};
  }
  return {reference, treatment, blocks: 4, df: 3, metrics};
}
const pairs = [
  ['baseline:original', 'coalesced:original'],
  ['baseline:original', 'reuse:original'],
  ['baseline:original', 'combined:original'],
  ['coalesced:original', 'combined:original'],
  ['reuse:original', 'combined:original'],
  ['combined:original', 'combined:current-compact'],
  ['combined:original', 'combined:current-indented'],
  ['combined:current-indented', 'combined:current-compact']
];
const result = {
  analyzedAtUtc: new Date().toISOString(), label,
  scope: 'One full-model operation loads49 org.eclipse.ui schemas plus15 real includes. CPU and allocation counters measure the benchmark thread, not startup or whole-process CPU.',
  method: 'Six raw iteration values form one fork mean. Four paired block differences form each descriptive Student-t interval, df3. No multiple-comparison adjustment; one shared host and one pinned but unreserved CPU. These intervals do not capture host/environment uncertainty.',
  independentJvmObservations: rows.length, iterationsPerFork: 6,
  scheduleSha256: hash(`schedule-${label}.json`), executedRunnerSha256: schedule.runnerSha256,
  observationsSha256: hash(`observations-${label}.json`), analyzerSha256: crypto.createHash('sha256').update(fs.readFileSync(__filename)).digest('hex'),
  cells, contrasts: pairs.map(p => contrast(...p)).filter(Boolean), rows
};
fs.writeFileSync(path.join(directory, `analysis-${label}.json`), JSON.stringify(result, null, 2) + '\n');
console.log(JSON.stringify({cells, contrasts: result.contrasts}, null, 2));
