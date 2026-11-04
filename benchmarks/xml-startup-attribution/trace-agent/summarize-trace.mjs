import fs from 'node:fs';
export function summarizeTrace(filename) {
 const text=fs.readFileSync(filename,'utf8');
 const events=text.trim().split('\n').filter(Boolean).map(line=>JSON.parse(line));
 const result={formatVersion:1,measurement:'diagnostic attribution; not a timing comparison',events:events.length,phases:[],registryStarts:[],operations:{},
  xmlZipBytesByReadPhase:{},xmlZipStreamRecords:0,openFailures:[],coverageErrors:[],instrumented:[],jobEvents:0,summary:null};
 for(const event of events) {
  if(event.kind==='begin'&&event.operation==='registry_start') result.registryStarts.push({phase:event.phase,loadedFromCache:event.loadedFromCache,jvmUptimeMs:event.jvmUptimeMs});
  if(event.kind==='phase') result.phases.push({phase:event.phase,jvmUptimeMs:event.jvmUptimeMs});
  if(event.kind==='end') {
   const key=`${event.phase}|${event.operation}|${event.outcome}`;
   result.operations[key]=(result.operations[key]||0)+1;
   if(event.outcome==='threw'&&['resource_open','zip_entry_open','file_open'].includes(event.operation)) result.openFailures.push(event);
  }
  if(event.kind==='stream'&&event.operation==='zip_entry_open'&&event.resourceAttribution==='xml_suffix') {
   result.xmlZipStreamRecords++;
   for(const [phase,bytes] of Object.entries(event.bytesByPhase)) result.xmlZipBytesByReadPhase[phase]=(result.xmlZipBytesByReadPhase[phase]||0)+bytes;
  }
  if(event.kind==='instrumented') result.instrumented.push({class:event.class,methods:event.methods});
  if(event.kind==='instrumentation_error'||event.kind==='trace_error'||event.kind==='incomplete') result.coverageErrors.push(event);
  if(event.kind==='job') result.jobEvents++;
  if(event.kind==='agent_summary') result.summary=event;
 }
 result.complete=!!result.summary&&!result.summary.droppedEvents&&!result.summary.inFlightSpans&&!result.summary.outputFailed&&result.coverageErrors.length===0;
 result.byteMeaning='Only zip_entry_open stream records classified by XML suffix are summed. Bytes are uncompressed bytes delivered, including rereads. They are neither physical disk bytes nor a compressed-JAR traffic measurement. All URL/file/EMF/parser layers remain in the raw trace.';
 return result;
}
if(process.argv[1]&&import.meta.url===new URL(`file://${process.argv[1]}`).href) {
 const result=summarizeTrace(process.argv[2]);
 if(process.argv[3]) fs.writeFileSync(process.argv[3],JSON.stringify(result,null,2)+'\n');
 else console.log(JSON.stringify(result,null,2));
}
