import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import {spawn} from 'node:child_process';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {summarizeTrace} from './summarize-trace.mjs';
import {createFixtures} from './fixtures.mjs';
import {verifyScenario} from './verify-scenario.mjs';
const here=path.dirname(fileURLToPath(import.meta.url));
const [installArg,outputArg,mode='headless']=process.argv.slice(2);
if(!installArg||!outputArg||!['headless','gui','all'].includes(mode)) throw new Error('Usage: run-eclipse-scenarios.mjs ECLIPSE_HOME NEW_OUTPUT_DIRECTORY [headless|gui|all]');
const original=path.resolve(installArg),out=path.resolve(outputArg);
if(fs.existsSync(out)) throw new Error('Output directory must be new; results are never overwritten');
fs.mkdirSync(out,{recursive:true});
const java=path.join(process.env.XML_TRACE_JAVA_HOME,'bin/java');
const agent=path.join(here,'build/xml-trace-agent.jar'),probe=path.resolve(here,'../probe/build/org.eclipse.pde.xmlstudy.probe_1.0.0.jar');
const jarNames=fs.readdirSync(path.join(original,'plugins')).filter(n=>n.endsWith('.jar')).sort();
const launcher=jarNames.filter(n=>n.startsWith('org.eclipse.equinox.launcher_'));
if(launcher.length!==1) throw new Error('Expected exactly one Equinox launcher');
const sha=file=>crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');
function sourceInputs(directory) {
 const files=[];
 for(const item of fs.readdirSync(directory,{withFileTypes:true})) {
  if(['build','results','classes','untraced','evidence'].includes(item.name))continue;
  const file=path.join(directory,item.name);
  if(item.isDirectory())files.push(...sourceInputs(file));
  else if(/\.(java|sh|mjs|xml)$/.test(item.name)||item.name==='MANIFEST.MF')files.push({name:path.relative(path.dirname(here),file),sha256:sha(file)});
 }
 return files.sort((a,b)=>a.name.localeCompare(b.name));
}
const result={formatVersion:2,sourceInputs:[...sourceInputs(here),...sourceInputs(path.resolve(here,'../probe'))],java,originalInstall:original,mode,agentSha256:sha(agent),bootstrapSha256:sha(path.join(here,'build/xml-trace-bootstrap.jar')),probeSha256:sha(probe),
 controls:[],runs:[],scope:'A small diagnostic matrix, with instrumentation. A cold registry is not a cold OS page cache. GUI and headless boundaries are reported separately.',
 pluginInputs:jarNames.map(name=>({name,sha256:sha(path.join(original,'plugins',name))}))};
const save=()=>fs.writeFileSync(path.join(out,'run-manifest.json'),JSON.stringify(result,null,2)+'\n');
save();
async function execute(id,args,timeoutMs=120000) {
 const folder=path.join(out,id);fs.mkdirSync(folder,{recursive:true});
 const log=fs.openSync(path.join(folder,'process.log'),'wx');
 const started=new Date().toISOString();
 const processResult=await new Promise(resolve=>{
  let timedOut=false;
  const child=spawn(java,args,{stdio:['ignore',log,log],env:process.env});
  const timeout=setTimeout(()=>{timedOut=true;child.kill('SIGTERM');setTimeout(()=>child.kill('SIGKILL'),5000).unref();},timeoutMs);
  child.on('error',error=>{clearTimeout(timeout);resolve({exitCode:null,spawnError:error.message,timedOut});});
  child.on('close',(exitCode,signal)=>{clearTimeout(timeout);resolve({exitCode,signal,timedOut});});
 });
 fs.closeSync(log);
 return {id,started,finished:new Date().toISOString(),command:[java,...args],...processResult};
}
async function verifyControl(id,className,verifier) {
 const folder=path.join(out,id),trace=path.join(folder,'trace.jsonl');
 const args=[`-javaagent:${agent}=${trace}`,'-cp',`${here}/controls/classes:${original}/plugins/*`,className,folder];
 const run=await execute(id,args);
 const verification=await new Promise(resolve=>{
  const cp=spawn(process.execPath,[path.join(here,'controls',verifier),trace],{stdio:['ignore','pipe','pipe']});
  let stdout='',stderr='';cp.stdout.on('data',d=>stdout+=d);cp.stderr.on('data',d=>stderr+=d);
  cp.on('close',exitCode=>resolve({exitCode,stdout,stderr}));
 });
 fs.writeFileSync(path.join(folder,'verification.json'),JSON.stringify(verification,null,2)+'\n');
 run.verification=verification;run.status=run.exitCode===0&&verification.exitCode===0?'ok':'failed';result.controls.push(run);save();
 if(run.status!=='ok') throw new Error(`${id} failed; no startup runs are permitted before the positive controls pass`);
}
await verifyControl('jdk-controls','TraceControls','verify-controls.mjs');
await verifyControl('eclipse-controls','EclipseTraceControls','verify-eclipse-controls.mjs');
function setupInstall(name) {
 const fixture=createFixtures(path.join(out,name+'-fixture'));
 const root=path.join(out,name),config=path.join(root,'configuration');
 fs.mkdirSync(path.join(config,'org.eclipse.equinox.simpleconfigurator'),{recursive:true});
 fs.symlinkSync(path.join(original,'plugins'),path.join(root,'plugins'),'dir');
 let ini=fs.readFileSync(path.join(original,'configuration/config.ini'),'utf8');
 ini+='\nosgi.configuration.cascaded=false\n';
 fs.writeFileSync(path.join(config,'config.ini'),ini);
 const info=fs.readFileSync(path.join(original,'configuration/org.eclipse.equinox.simpleconfigurator/bundles.info'),'utf8')+`\norg.eclipse.pde.xmlstudy.probe,1.0.0,${pathToFileURL(probe).href},2,true\n`;
 fs.writeFileSync(path.join(config,'org.eclipse.equinox.simpleconfigurator/bundles.info'),info);
 for(const item of ['.eclipseproduct']) if(fs.existsSync(path.join(original,item))) fs.copyFileSync(path.join(original,item),path.join(root,item));
 if(fs.existsSync(path.join(original,'p2'))) fs.cpSync(path.join(original,'p2'),path.join(root,'p2'),{recursive:true});
 return {root,config,fixture,workspace:path.join(out,name+'-workspace')};
}
async function eclipse(id,installation,headless,clean,options={}) {
 const {automaticBuild=false,editors=false,restoreEditors=false}=options;
 const fixture=installation.fixture;
 const extra=[`-Dxml.trace.autoBuild=${automaticBuild}`,`-Dxml.study.scenario=${automaticBuild?'autobuild':editors?'editors':'startup'}`];
 const folder=path.join(out,id),trace=path.join(folder,'trace.jsonl');
 const args=['-Xms256m','-Xmx1024m','--enable-native-access=ALL-UNNAMED',`-javaagent:${agent}=${trace}`,
  `-Dxml.trace.fixture=${fixture}`,`-Dxml.study.output=${folder}/probe.json`,`-Dxml.study.runId=${id}`,
  '-Dxml.study.fdDiagnostics=false','-Dxml.study.diagnostics=true','-Dxml.study.timeoutMs=120000',`-Dxml.study.enabled=${headless?'false':'true'}`,...extra,
  '-jar',path.join(original,'plugins',launcher[0]),'-install',installation.root,'-configuration',installation.config,'-data',installation.workspace,
  '-nosplash','-consoleLog','-application',headless?'org.eclipse.pde.xmlstudy.probe.headlessDiagnostic':'org.eclipse.ui.ide.workbench',...(clean?['-clean']:[])];
 const run=await execute(id,args,180000);
 run.scenario=id;run.registryCondition=clean?'cache invalidated with -clean':'persisted configuration reused, no -clean';
 run.workspaceCondition='Provider and consumer PDE/Java projects; '+(automaticBuild?'auto build enabled with resource touches':restoreEditors?'auto build off, two PDE editor references restored':editors?'auto build off, two PDE editors opened after readiness':'auto build off, no seeded editors');
 run.osCache='uncontrolled, expected warm';run.primaryTiming=false;
 const logfile=fs.readFileSync(path.join(folder,'process.log'),'utf8');
 run.eclipseErrorEntries=(logfile.match(/!ENTRY\s+\S+\s+4\s/g)||[]).length;
 try {run.trace=summarizeTrace(trace);fs.writeFileSync(path.join(folder,'trace-summary.json'),JSON.stringify(run.trace,null,2)+'\n');}
 catch(error){run.traceError=error.message;}
 try {run.probe=JSON.parse(fs.readFileSync(path.join(folder,'probe.json'),'utf8'));}
 catch(error){run.probeError=error.message;}
 try {run.coverage=verifyScenario(trace,run.probe,{headless,clean,...options});}
 catch(error){run.coverageError=error.message;}
 run.status=run.exitCode===0&&!run.timedOut&&!run.eclipseErrorEntries&&run.trace?.complete&&run.probe?.status==='ok'&&!run.coverageError?'ok':'failed';
 const stored={...run,trace:undefined,traceSummary:run.trace?`${id}/trace-summary.json`:null};result.runs.push(stored);save();
 console.log(JSON.stringify({id,status:run.status,exitCode:run.exitCode,events:run.trace?.events,coverageErrors:run.trace?.coverageErrors.length,eclipseErrorEntries:run.eclipseErrorEntries,coverageError:run.coverageError}));
 if(run.status!=='ok') throw new Error(`${id} failed; inspect its retained process, probe and trace files`);
 return run;
}
if(mode==='headless'||mode==='all') {
 const installation=setupInstall('headless-install');
 await eclipse('headless-cold-registry',installation,true,true);
 await eclipse('headless-prepared-restart',installation,true,false);
 await eclipse('headless-automatic-build',installation,true,false,{automaticBuild:true});
}
if(mode==='gui'||mode==='all') {
 if(!process.env.DISPLAY) {result.guiBlocked='DISPLAY is not set; use an Xvfb display for GUI diagnostics';save();throw new Error(result.guiBlocked);}
 const installation=setupInstall('gui-install');
 await eclipse('gui-workspace-preparation',installation,true,true);
 // Discard only runtime caches, retaining the exact same bundle configuration.
 for(const entry of fs.readdirSync(installation.config)) if(!['config.ini','org.eclipse.equinox.simpleconfigurator'].includes(entry)) fs.rmSync(path.join(installation.config,entry),{recursive:true,force:true});
 await eclipse('gui-cold-registry',installation,false,true);
 await eclipse('gui-prepared-restart',installation,false,false);
 const baseline=path.join(out,'gui-baseline');fs.mkdirSync(baseline);
 fs.cpSync(installation.config,path.join(baseline,'configuration'),{recursive:true,preserveTimestamps:true});
 fs.cpSync(installation.workspace,path.join(baseline,'workspace'),{recursive:true,preserveTimestamps:true});
 fs.cpSync(path.dirname(installation.fixture),path.join(baseline,'fixture'),{recursive:true,preserveTimestamps:true});
 await eclipse('gui-automatic-build',installation,false,false,{automaticBuild:true});
 for(const [target,saved] of [[installation.config,'configuration'],[installation.workspace,'workspace'],[path.dirname(installation.fixture),'fixture']]) {
  fs.rmSync(target,{recursive:true});fs.cpSync(path.join(baseline,saved),target,{recursive:true,preserveTimestamps:true});
 }
 await eclipse('gui-editor-seed',installation,false,false,{editors:true});
 await eclipse('gui-restored-editors',installation,false,false,{restoreEditors:true});
}
result.status='ok';save();
console.log(`Diagnostic artifacts: ${out}`);
