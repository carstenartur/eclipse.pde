import fs from 'node:fs';
import assert from 'node:assert/strict';
const events=fs.readFileSync(process.argv[2],'utf8').trim().split('\n').map(JSON.parse);
const has=p=>events.some(p);
assert.deepEqual(events.filter(e=>e.kind==='trace_error'||e.kind==='instrumentation_error'),[]);
for(const [phase,operation] of [['control_registry','registry_parse'],['control_emf','emf_load'],['control_pde_schema','schema_load']]) {
 assert.ok(has(e=>e.phase===phase&&e.operation===operation&&e.kind==='end'&&e.outcome==='returned'),`${operation} must be observed with real Eclipse classes`);
}
assert.ok(has(e=>e.phase==='control_pde_schema_missing_jar'&&e.kind==='end'&&e.operation==='resource_open'&&e.outcome==='threw'&&e.source.endsWith('!/missing.exsd')),'Actual Schema.load failure before its InputStream overload must be visible');
assert.ok(!has(e=>e.phase==='control_pde_schema_missing_jar'&&e.kind==='begin'&&e.operation==='schema_load'&&e.method.includes('Ljava/io/InputStream;')),'Missing JAR control must fail before the old InputStream hook');
assert.ok(has(e=>e.phase==='control_early_job'&&e.kind==='job'&&e.jobName==='XML pre-probe positive-control job'&&/running/i.test(e.event)),'Job running before probe activation must be observed');
assert.ok(has(e=>e.phase==='control_early_job'&&e.kind==='job'&&/done/i.test(e.event)),'Job completion must be observed');
assert.ok(has(e=>e.kind==='agent_summary'&&!e.droppedEvents&&!e.inFlightSpans&&!e.outputFailed),'A complete final summary is required');
console.log(JSON.stringify({status:'ok',cases:5,events:events.length,methods:events.filter(e=>e.kind==='instrumented').flatMap(e=>e.methods).length},null,2));
