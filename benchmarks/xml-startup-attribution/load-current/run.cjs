#!/usr/bin/env node
// SPDX-License-Identifier: EPL-2.0
// Current-source follow-up to the archived 49-schema full-model JMH experiment.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const {spawnSync} = require('node:child_process');
const args = process.argv.slice(2), mode = args.shift();
const options = {};
while (args.length) { const key = args.shift(); if (!key.startsWith('--') || !args.length) throw Error('Expected --name value'); options[key.slice(2)] = args.shift(); }
const out = path.resolve(options.out || 'current-load-results');
const sha = value => crypto.createHash('sha256').update(value).digest('hex');
function run(command, argv, log) {
  let result;
  if (log) { const fd = fs.openSync(log, 'w'); try { result = spawnSync(command, argv, {stdio: ['ignore', fd, fd]}); } finally { fs.closeSync(fd); } }
  else result = spawnSync(command, argv, {encoding: 'utf8', maxBuffer: 16 * 1024 * 1024});
  if (result.error || result.status !== 0) throw Error(`${command} failed (${result.status}): ${log || result.stderr || result.error}`);
  return result.stdout || '';
}
const save = (name, value) => fs.writeFileSync(path.join(out, name), JSON.stringify(value, null, 2) + '\n');
const read = name => JSON.parse(fs.readFileSync(path.join(out, name), 'utf8'));
function files(dir) { return fs.readdirSync(dir, {withFileTypes:true}).flatMap(e => e.isDirectory() ? files(path.join(dir,e.name)) : [path.join(dir,e.name)]).sort(); }
function cp(m, variant) { return [path.join(out,'bench'), path.join(out,'classes',variant), path.join(out,'support'), ...m.dependencies].join(path.delimiter); }
function validate(m, variants, corpora) {
  let reference;
  for (const variant of variants) {
    const log = path.join(out, `validate-${variant}-${corpora.join('-')}.log`);
    run(m.java, ['-Devaluation='+m.archive,'-Dcorpus='+path.join(out,'corpus'),'-cp',cp(m,variant),'bench.SchemaLoadBenchmark','validate',...corpora], log);
    const models = {};
    for (const line of fs.readFileSync(log,'utf8').split('\n')) if (line.startsWith('MODEL ')) {
      const [,corpus,name,hash] = line.split(' '); (models[corpus] ||= {})[name] = hash;
    }
    if (Object.keys(models).length !== corpora.length) throw Error('Missing corpus validation');
    for (const corpus of corpora) {
      if (Object.keys(models[corpus] || {}).length !== 49) throw Error('Expected 49 model hashes');
      const value = JSON.stringify(Object.entries(models[corpus]).sort()); reference ||= value;
      if (reference !== value) throw Error(`Model mismatch: ${variant}/${corpus}`);
    }
  }
  return sha(reference);
}
function jarCorpus(m, name, source) {
  if (!/^[a-z0-9-]+$/.test(name)) throw Error('Unsafe corpus name');
  const dest = path.join(out,'corpus',name);
  fs.mkdirSync(dest,{recursive:true}); fs.cpSync(source,dest,{recursive:true});
  const schemas = files(dest).filter(f=>f.endsWith('.exsd'));
  if (schemas.length !== 49) throw Error(`Expected 49 schemas, got ${schemas.length}`);
  run(m.jar,['--create','--file',path.join(out,'corpus',name+'.jar'),'--date=2026-11-04T00:00:00Z','-C',dest,'.']);
  return schemas.map(f=>({path:path.relative(dest,f),bytes:fs.statSync(f).size,sha256:sha(fs.readFileSync(f))}));
}
if (mode === 'prepare') {
  for (const key of ['repo','archive','java-home']) if (!options[key]) throw Error(`Missing --${key}`);
  const archive = path.resolve(options.archive), repo = path.resolve(options.repo), jdk = path.resolve(options['java-home']);
  fs.mkdirSync(out,{recursive:true}); fs.mkdirSync(path.join(out,'support'),{recursive:true});
  const deps = JSON.parse(fs.readFileSync(path.join(archive,'provenance/classpaths.json'),'utf8'));
  const m = {date:new Date().toISOString(),scope:'49 top-level org.eclipse.ui schemas plus their 15 include loads; full SchemaDescriptor/Schema model path, not Eclipse startup',archive,repo,java:path.join(jdk,'bin/java'),javac:path.join(jdk,'bin/javac'),jar:path.join(jdk,'bin/jar'),dependencies:[...deps.eclipse,...deps.benchmark].map(p=>path.join(archive,p)),variants:{},corpora:{},sharedMachine:true};
  m.javaVersion = run(m.java,['-version']) || spawnSync(m.java,['-version'],{encoding:'utf8'}).stderr;
  run('unzip',['-q','-o',path.join(archive,deps.snapshot),'-d',path.join(out,'support')]);
  const base='f948c57878a1a011625b5214d63a1ec01bd243ff', coalesce='de6efde7becdbcc5515c0a45c908d2592ccd465e', reuse='eedb94d809215598b39d53f711733e0313e04fbe';
  const prefix='ui/org.eclipse.pde.core/src/';
  for (const [name,h,r] of [['baseline',base,base],['coalesced',coalesce,base],['reuse',base,reuse],['combined',coalesce,reuse]]) {
    const sourceFiles=[['org/eclipse/pde/internal/core/XMLDefaultHandler.java',h],['org/eclipse/pde/internal/core/schema/Schema.java',r]];
    if (r===reuse) sourceFiles.push(['org/eclipse/pde/internal/core/schema/SchemaReader.java',r]);
    const sources=[]; m.variants[name]={handlerCommit:h,schemaCommit:r,files:[]};
    for (const [file,ref] of sourceFiles) {
      const value=run('git',['-C',repo,'show',ref+':'+prefix+file]), dest=path.join(out,'sources',name,file);
      fs.mkdirSync(path.dirname(dest),{recursive:true}); fs.writeFileSync(dest,value); sources.push(dest);
      m.variants[name].files.push({path:prefix+file,ref,sha256:sha(value)});
    }
    fs.mkdirSync(path.join(out,'classes',name),{recursive:true});
    run(m.javac,['--release','17','-proc:none','-cp',[path.join(out,'support'),...m.dependencies].join(path.delimiter),'-d',path.join(out,'classes',name),...sources],path.join(out,`compile-${name}.log`));
  }
  fs.mkdirSync(path.join(out,'bench'),{recursive:true});
  run(m.javac,['--release','25','-cp',cp(m,'baseline'),'-processorpath',[path.join(archive,'lib/benchmark/jmh-core-1.37.jar'),path.join(archive,'lib/benchmark/jmh-generator-annprocess-1.37.jar')].join(path.delimiter),'-processor','org.openjdk.jmh.generators.BenchmarkProcessor','-d',path.join(out,'bench'),path.join(archive,'src/bench/SchemaLoadBenchmark.java'),path.join(__dirname,'SaxDomWork.java')],path.join(out,'compile-benchmark.log'));
  m.benchmarkSourceSha256=sha(fs.readFileSync(path.join(archive,'src/bench/SchemaLoadBenchmark.java')));
  m.corpora.original=jarCorpus(m,'original',path.join(archive,'corpus/original'));
  m.normalizedModelHash=validate(m,Object.keys(m.variants),['original']);
  save('manifest.json',m); console.log('Prepared four current source variants; all 49 model serializations identical.');
} else if (mode === 'add-corpus') {
  const m=read('manifest.json'); m.corpora[options.name]=jarCorpus(m,options.name,path.resolve(options.source));
  validate(m,Object.keys(m.variants),['original',options.name]); save('manifest.json',m);
  console.log(`Added ${options.name}; model parity verified for all four implementations.`);
} else if (mode === 'diagnose') {
  const m=read('manifest.json'), rows=[];
  for (const corpus of Object.keys(m.corpora)) for (const variant of ['baseline','coalesced']) {
    const log=path.join(out,`sax-dom-${variant}-${corpus}.json`);
    run(m.java,['-cp',cp(m,variant),'SaxDomWork',path.join(out,'corpus',corpus+'.jar')],log);
    rows.push({variant,corpus,...JSON.parse(fs.readFileSync(log,'utf8'))});
  }
  for (const corpus of Object.keys(m.corpora)) {
    const a=rows.find(x=>x.variant==='baseline'&&x.corpus===corpus), b=rows.find(x=>x.variant==='coalesced'&&x.corpus===corpus);
    for(const key of ['schemas','characterCallbacks','characterUnits','normalizedTextNodes','domHash']) if(a[key]!==b[key]) throw Error(`Coalescing changed ${key} for ${corpus}`);
  }
  save('sax-dom-summary.json',rows); console.log(JSON.stringify(rows,null,2));
} else if (mode === 'measure') {
  const m=read('manifest.json'), selected=(options.cases || 'baseline:original,coalesced:original,reuse:original,combined:original').split(',').map(x=>x.split(':'));
  const blocks=Number(options.blocks||3), schedule=[], all=[];
  if (!Number.isInteger(blocks)||blocks<3) throw Error('At least three fresh-JVM blocks required');
  for (const [v,c] of selected) if(!m.variants[v]||!m.corpora[c]) throw Error('Unknown variant/corpus');
  validate(m,[...new Set(selected.map(x=>x[0]))],[...new Set(selected.map(x=>x[1]))]);
  for(let block=0;block<blocks;block++) {
    let order=selected.slice(block%selected.length).concat(selected.slice(0,block%selected.length)); if(block%2)order=order.reverse();
    for(const [variant,corpus] of order) schedule.push({block,variant,corpus});
  }
  const runId=options.label||'current'; if(!/^[a-z0-9-]+$/.test(runId))throw Error('Unsafe label');
  save(`schedule-${runId}.json`,{blocks,order:'Rotate cases by block; reverse odd blocks. All comparisons use fresh JVMs.',schedule,warmup:'8 x 2 seconds',measurement:'6 x 1 second',forksPerCasePerBlock:1,exclusiveCpu:options.cpu??null});
  for(const item of schedule) {
    const label=`${runId}-b${item.block}-${item.variant}-${item.corpus}`, result=path.join(out,label+'.json'), log=path.join(out,label+'.log');
    const argv=['-Devaluation='+m.archive,'-Dcorpus='+path.join(out,'corpus'),'-cp',cp(m,item.variant),'org.openjdk.jmh.Main','^bench.SchemaLoadBenchmark.loadSchemas$','-p','variant='+item.corpus,'-wi','8','-w','2s','-i','6','-r','1s','-f','1','-rf','json','-rff',result];
    run(options.cpu?'taskset':m.java,options.cpu?['-c',options.cpu,m.java,...argv]:argv,log);
    const records=JSON.parse(fs.readFileSync(result,'utf8')); if(records.length!==1)throw Error(`Missing JMH result ${label}`);
    const metrics=records[0].secondaryMetrics;
    const values=Object.fromEntries(Object.entries(metrics).map(([key,value])=>[key,value.rawData.flat()]));
    if(!values.cpuMs||!values.allocatedBytes||Object.values(values).some(xs=>xs.length!==6||xs.some(x=>!Number.isFinite(x))))throw Error(`Incomplete JMH counters ${label}`);
    all.push({...item,label,values}); save(`observations-${runId}.json`,all); console.log(`Completed ${label}`);
  }
} else throw Error('Modes: prepare, add-corpus, diagnose, measure');
