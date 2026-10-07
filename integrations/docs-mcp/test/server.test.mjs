import test from 'node:test';
import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
const server = new URL('../server.mjs', import.meta.url);
const initialize = {jsonrpc:'2.0',id:1,method:'initialize',params:{protocolVersion:'2025-06-18',clientInfo:{name:'test',version:'1'},capabilities:{}}};
const ready = {jsonrpc:'2.0',method:'notifications/initialized'};
function run(messages, prefix=[initialize,ready]) {
  const p=spawnSync(process.execPath,[server.pathname],{input:[...prefix,...messages].map(x=>typeof x==='string'?x:JSON.stringify(x)).join('\n')+'\n',encoding:'utf8',timeout:10000,maxBuffer:2000000});
  assert.equal(p.status,0,p.stderr);assert.equal(p.stderr,'');
  return p.stdout.trim().split('\n').map(x=>JSON.parse(x));
}
const request=(id,method,params={})=>({jsonrpc:'2.0',id,method,params});
test('handshake, resource discovery and reading match tool content',()=>{
 const r=run([request(2,'resources/list'),request(3,'resources/read',{uri:'dagp://docs/policy'}),request(4,'tools/call',{name:'read_document',arguments:{id:'policy'}}),request(5,'tools/list')]);
 assert.equal(r[0].result.protocolVersion,'2025-06-18');
 assert.ok(r[1].result.resources.some(x=>x.uri==='dagp://docs/quickstart'));
 assert.match(r[2].result.contents[0].text,/66.00/);
 assert.equal(r[2].result.contents[0].text,r[3].result.content[0].text);
 assert.equal(r[4].result.tools.length,3);
 assert.ok(r[4].result.tools.every(x=>x.annotations.readOnlyHint));
});
test('bounded search and document list',()=>{
 const r=run([request(2,'tools/call',{name:'search_documents',arguments:{query:'quorum'}}),request(3,'tools/call',{name:'list_documents',arguments:{}})]);
 const hits=JSON.parse(r[1].result.content[0].text);assert.ok(hits.length>0 && hits.length<=10);
 assert.ok(hits.every(x=>x.snippet.length<=286));
 assert.ok(JSON.parse(r[2].result.content[0].text).some(x=>x.id==='security'));
});
test('no filesystem escape, unknown tool, excess arguments or empty search',()=>{
 const r=run([
  request(2,'resources/read',{uri:'file:///etc/passwd'}),
  request(3,'resources/read',{uri:'dagp://docs/../../LICENSE'}),
  request(4,'tools/call',{name:'read_document',arguments:{id:'../../LICENSE'}}),
  request(5,'tools/call',{name:'read_document',arguments:{id:'policy',path:'/etc/passwd'}}),
  request(6,'tools/call',{name:'execute',arguments:{}}),
  request(7,'tools/call',{name:'search_documents',arguments:{query:' '}})]);
 assert.equal(r[1].error.code,-32602);assert.equal(r[2].error.code,-32602);
 assert.ok(r.slice(3).every(x=>x.result.isError));
});
test('reject malformed JSON, batches, invalid params and pre-initialization use; survive errors',()=>{
 const r=run(['{',[],request(2,'tools/list'),{jsonrpc:'2.0',id:3,method:'ping',params:[]},request(4,'ping')],[]);
 assert.equal(r[0].error.code,-32700);assert.equal(r[1].error.code,-32600);
 assert.equal(r[2].error.code,-32002);assert.equal(r[3].error.code,-32600);assert.deepEqual(r[4].result,{});
});
test('version fallback and duplicate initialize rejection',()=>{
 const init={...initialize,params:{...initialize.params,protocolVersion:'2099-01-01'}};
 const r=run([initialize],[init,ready]);
 assert.equal(r[0].result.protocolVersion,'2025-06-18');assert.equal(r[1].error.code,-32600);
});
test('oversized unframed input terminates without buffering unbounded data',()=>{
 const p=spawnSync(process.execPath,[server.pathname],{input:'x'.repeat(70000),encoding:'utf8',timeout:10000});
 assert.equal(p.status,1);assert.match(p.stderr,/64 KiB/);assert.equal(p.stdout,'');
});
