import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import {gzipSync} from 'node:zlib';
const [sourceArg,destinationArg]=process.argv.slice(2);
if(!sourceArg||!destinationArg)throw Error('Usage: node package-evidence.mjs RUN_OUTPUT NEW_EVIDENCE_DIRECTORY');
const source=path.resolve(sourceArg),destination=path.resolve(destinationArg);
if(fs.existsSync(destination))throw Error('Evidence destination must be new');
fs.mkdirSync(destination,{recursive:true});
const sha=bytes=>crypto.createHash('sha256').update(bytes).digest('hex');
const manifest=JSON.parse(fs.readFileSync(path.join(source,'run-manifest.json'),'utf8'));
const index={formatVersion:1,sourceRunStatus:manifest.status||'incomplete',files:[],meaning:'Raw traces are gzip-compressed without changing their JSONL bytes. Workspaces, installation copies and generated class files are omitted.'};
function preserve(relative,compress=false){
 const input=path.join(source,relative);if(!fs.existsSync(input))return;
 const bytes=fs.readFileSync(input),target=relative+(compress?'.gz':'');
 fs.mkdirSync(path.dirname(path.join(destination,target)),{recursive:true});
 const saved=compress?gzipSync(bytes,{level:9}):bytes;fs.writeFileSync(path.join(destination,target),saved);
 index.files.push({file:target,sha256:sha(saved),bytes:saved.length,...(compress?{uncompressedSha256:sha(bytes),uncompressedBytes:bytes.length}:{})});
}
preserve('run-manifest.json');
for(const run of [...manifest.controls,...manifest.runs]){
 for(const file of ['process.log','probe.json','trace-summary.json','verification.json'])preserve(`${run.id}/${file}`);
 preserve(`${run.id}/trace.jsonl`,true);
}
fs.writeFileSync(path.join(destination,'evidence-index.json'),JSON.stringify(index,null,2)+'\n');
console.log(JSON.stringify({destination,files:index.files.length,totalBytes:index.files.reduce((a,b)=>a+b.bytes,0)},null,2));
