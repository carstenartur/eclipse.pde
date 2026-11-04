import fs from 'node:fs';
import assert from 'node:assert/strict';

/** Evidence gates are based on actual runtime events, not job names or elapsed time. */
export function verifyScenario(filename, probe, {headless, clean, automaticBuild=false, editors=false, restoreEditors=false}) {
 const events=fs.readFileSync(filename,'utf8').trim().split('\n').map(JSON.parse);
 const phases=events.filter(e=>e.kind==='phase');
 const begins=events.filter(e=>e.kind==='begin');
 const registry=begins.filter(e=>e.operation==='registry_start');
 assert.equal(registry.length,1,'One registry start must be observed');
 assert.equal(registry[0].loadedFromCache,!clean,'Registry cache state must match the requested condition');
 const report={registryLoadedFromCache:registry[0].loadedFromCache,
  registryParses:begins.filter(e=>e.operation==='registry_parse').length,
  saxParses:begins.filter(e=>e.operation==='sax_parse').length,
  domParses:begins.filter(e=>e.operation==='dom_parse').length,
  emfLoads:begins.filter(e=>e.operation==='emf_load').length};
 if(clean) assert.ok(report.registryParses>0,'Cold registry must exercise ExtensionsParser');
 if(headless) {
  assert.ok(phases.some(e=>e.phase==='headless_application_entered'));
  assert.ok(phases.some(e=>e.phase==='headless_background_settled'));
  assert.ok(!phases.some(e=>e.phase==='workbench_ready'),'Headless must not claim workbench readiness');
  assert.equal(probe.fixtureProjects.length,2,'Both provider and consumer must be imported');
 } else {
  const ready=phases.find(e=>e.phase==='workbench_ready');
  const settled=phases.find(e=>e.phase==='background_settled');
  assert.ok(ready&&settled&&ready.elapsedNs<settled.elapsedNs,'GUI readiness and later quiet boundary must both exist');
  assert.ok(report.emfLoads>0,'GUI must exercise the EMF XML model path');
  report.readyUptimeMs=ready.jvmUptimeMs;report.settledUptimeMs=settled.jvmUptimeMs;
  const terminal=probe.phases.at(-1);
  report.workspace=terminal.workspace;
  assert.equal(terminal.workspace.autoBuildEnabled,automaticBuild,'Automatic-build state must match the scenario');
  if(editors||restoreEditors) {
   const ids=terminal.workspace.editors.map(e=>e.id);
   assert.ok(ids.includes('org.eclipse.pde.ui.manifestEditor'),'Manifest editor reference must exist');
   assert.ok(ids.includes('org.eclipse.pde.ui.schemaEditor'),'Schema editor reference must exist');
   assert.ok(terminal.workspace.editors.some(e=>e.materialized),'At least the active editor must actually be instantiated');
  }
 }
 if(automaticBuild) {
  const start=phases.find(e=>e.phase==='automatic_build_trigger_started');
  const finish=phases.find(e=>e.phase==='automatic_build_finished');
  assert.ok(start&&finish&&start.elapsedNs<finish.elapsedNs,'Automatic build must finish after its trigger');
  const actual=headless?probe.automaticBuild:probe.phases.at(-1).diagnostic;
  assert.ok(actual.automaticBuildEvents>0&&actual.autoBuildEnabled,'Actual AUTO_BUILD completion and enabled setting are required');
  assert.deepEqual(actual.errorMarkers,[],'Fixture must build without error markers');
  const during=begins.filter(e=>e.elapsedNs>=start.elapsedNs&&e.elapsedNs<=finish.elapsedNs);
  report.automaticBuild={...actual,pdeBuilders:during.filter(e=>e.operation==='pde_builder').length,
   javaBuilders:during.filter(e=>e.operation==='java_builder').length,
   schemaLoads:during.filter(e=>e.operation==='schema_load').length,
   consumerXmlOpens:during.filter(e=>['file_open','resource_open'].includes(e.operation)&&e.source.includes('org.eclipse.pde.xmlstudy.consumer')&&e.source.endsWith('plugin.xml')).length};
  assert.ok(report.automaticBuild.pdeBuilders>0,'PDE builders must execute');
  assert.ok(report.automaticBuild.javaBuilders>0,'Java builder must execute');
  assert.ok(report.automaticBuild.schemaLoads>0,'Schema.load must execute during the automatic build interval');
  assert.ok(report.automaticBuild.consumerXmlOpens>0,'Consumer plugin.xml must actually be opened during the automatic build interval');
 }
 return report;
}
