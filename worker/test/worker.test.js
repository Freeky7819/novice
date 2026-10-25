import {test} from 'node:test';
import assert from 'node:assert/strict';
import {webcrypto,timingSafeEqual,randomUUID} from 'node:crypto';
import {createWorker} from '../index.js';
import trusted from '../generated.js';
import {BASE,ORIGIN,validate,strictJSON} from '../validation.js';
import {readArticle,robotsAllowed,allowedURL} from '../article.js';

const id='a'.repeat(40), other='b'.repeat(40);
const valid={neutral:'Nevtralen slovenski povzetek. Drugi stavek.',mine:'Po domače razložena novica. Drugi stavek.',topics:['znanost']};
const item={id,title:'Science',excerpt:'RSS excerpt',source_id:'test',url:'https://source.example/article'};
const json=(value,status=200)=>new Response(JSON.stringify(value),{status,headers:{'Content-Type':'application/json'}});
const cryptoAPI={subtle:{digest:webcrypto.subtle.digest.bind(webcrypto.subtle),timingSafeEqual},randomUUID};
class KV {
  data=new Map();
  async get(key,type) {const v=this.data.get(key);return v===undefined?null:type==='json'?JSON.parse(v):v;}
  async put(key,value) {this.data.set(key,value);}
  async list({prefix}) {return {keys:[...this.data.keys()].filter(k=>k.startsWith(prefix)).map(name=>({name})),list_complete:true};}
}
function fixture(options={}) {
  const env={SUMMARIES:new KV(),NOVICE_KODA:'TEST_ONLY_CODE',ANTHROPIC_API_KEY:'TEST_ONLY_AI',GITHUB_TOKEN_NOVICE:'TEST_ONLY_GITHUB',...options.env};
  const calls={ai:[],git:[],pages:[],article:[]};let now=Date.parse('2026-10-25T10:00:00Z');
  const fetcher=async(url,init={})=>{
    if(url.startsWith(BASE)) {
      calls.pages.push(url);
      if(url.endsWith('feed.json')) return json({items:options.items||[item,{...item,id:other}]});
      if(url.endsWith('config.json')) return json({topics:trusted.topics.map(id=>({id})),sources:[{id:'test',name:'Test source',enabled:options.enabled!==false,domains:['source.example']}]});
      if(url.endsWith('summaries.json')) return json(options.legacy||{});
    }
    if(url==='https://api.anthropic.com/v1/messages') {
      calls.ai.push(JSON.parse(init.body));
      if(options.ai) return options.ai(init);
      return json({stop_reason:'end_turn',content:[{type:'text',text:JSON.stringify(valid)}]});
    }
    if(url==='https://api.github.com/repos/Freeky7819/novice/dispatches') {
      calls.git.push(JSON.parse(init.body));return new Response(null,{status:options.gitStatus||204});
    }
    throw new Error('Unexpected external call');
  };
  const app=createWorker({fetcher,cryptoAPI,clock:()=>now,reader:async entry=>{calls.article.push(entry.id);return {text:'Public body text.',basis:'article'};}});
  const request=(body={id},code=env.NOVICE_KODA,origin=ORIGIN)=>app.fetch(new Request('https://worker.example/api/summary',{
    method:'POST',headers:{'Content-Type':'application/json',...(origin?{Origin:origin}:{}),'X-Novice-Koda':code},body:JSON.stringify(body)}),env);
  return {env,calls,app,request,advance:(ms)=>{now+=ms;}};
}

test('wrong code returns only 401, foreign or missing origin returns 403, no external calls',async()=>{
  const f=fixture();
  for(const code of ['', 'wrong','TEST_ONLY_CODF']) {const r=await f.request({id},code);assert.equal(r.status,401);assert.deepEqual(await r.json(),{error:'unauthorized'});}
  for(const origin of [null,'https://evil.example','https://freeky7819.github.io.evil.example']) {
    const r=await f.request({id},undefined,origin);assert.equal(r.status,403);assert.equal(r.headers.get('Access-Control-Allow-Origin'),null);
  }
  assert.equal(f.calls.pages.length,0);assert.equal(f.calls.ai.length,0);
});

test('preflight permits only exact Pages origin, POST and required headers',async()=>{
  const f=fixture();
  const r=await f.app.fetch(new Request('https://worker.example/api/summary',{method:'OPTIONS',headers:{Origin:ORIGIN,'Access-Control-Request-Method':'POST','Access-Control-Request-Headers':'content-type,x-novice-koda'}}),f.env);
  assert.equal(r.status,204);assert.equal(r.headers.get('Access-Control-Allow-Origin'),ORIGIN);
  const bad=await f.app.fetch(new Request('https://worker.example/api/summary',{method:'OPTIONS',headers:{Origin:ORIGIN,'Access-Control-Request-Method':'GET'}}),f.env);
  assert.equal(bad.status,403);
});

test('unknown id, extra fields, arbitrary URL, invalid JSON and disabled source rejected before AI',async()=>{
  const f=fixture();
  assert.equal((await f.request({id:'c'.repeat(40)})).status,404);
  for(const data of [{url:'https://evil.example'},{id,url:'https://evil.example'},{id:'https://source.example/'},{id:[id]}]) assert.equal((await f.request(data)).status,400);
  assert.equal((await fixture({enabled:false}).request()).status,403);
  assert.equal(f.calls.ai.length,0);
});

test('one article, one AI request, both modes in KV, exact dispatch payload and cache hit',async()=>{
  const f=fixture();const r=await f.request();assert.equal(r.status,200);
  const result=await r.json();assert.equal(result.neutral,valid.neutral);assert.equal(result.mine,valid.mine);assert.equal(result.basis,'article');
  assert.deepEqual(f.calls.article,[id]);assert.equal(f.calls.ai.length,1);assert.equal(f.calls.git.length,1);
  assert.equal(f.calls.ai[0].model,trusted.model);assert.equal(f.calls.ai[0].system,trusted.system);
  assert.equal(f.calls.git[0].event_type,'povzetek');
  assert.deepEqual(Object.keys(f.calls.git[0].client_payload).sort(),['basis','created_at','id','mine','model','neutral','topics']);
  const again=await (await f.request()).json();assert.equal(again.cached,true);assert.equal(f.calls.ai.length,1);
  assert.equal(f.calls.pages.filter(x=>x.endsWith('feed.json')).length,1);
  f.advance(300001);await f.request();assert.equal(f.calls.pages.filter(x=>x.endsWith('feed.json')).length,2);
});

test('Pages summaries cache is returned without AI, even with zero daily limit or no provider keys',async()=>{
  const f=fixture({legacy:{[id]:{status:'ok',basis:'public_part',result:valid}},env:{AI_MAX_PER_DAY:'0',ANTHROPIC_API_KEY:'',GITHUB_TOKEN_NOVICE:''}});
  const r=await f.request();assert.equal(r.status,200);assert.equal((await r.json()).basis,'public_part');
  assert.equal(f.calls.ai.length,0);assert.equal(f.calls.git.length,0);assert.equal(f.calls.article.length,0);
});

test('failures consume budget, retry waits 90 seconds, UTC day resets',async()=>{
  const f=fixture({env:{AI_MAX_PER_DAY:'2'},ai:()=>json({stop_reason:'end_turn',content:[{type:'text',text:'{"neutral":"<script>","mine":"bad","topics":[]}'}]})});
  assert.equal((await f.request()).status,502);assert.equal((await f.request()).status,429);assert.equal(f.calls.ai.length,1);
  f.advance(91000);assert.equal((await f.request()).status,502);f.advance(91000);
  assert.equal((await f.request({id:other})).status,429);assert.equal(f.calls.ai.length,2);
  assert.equal([...f.env.SUMMARIES.data.keys()].filter(k=>k.startsWith('attempt:')).length,2);
  assert.equal(await f.env.SUMMARIES.get('summary:'+id),null);assert.equal(f.calls.git.length,0);
  f.advance(86400000);assert.equal((await f.request()).status,502);assert.equal(f.calls.ai.length,3);
});

test('default daily limit is 50, failures included, cache still works at limit',async()=>{
  const items=Array.from({length:51},(_,i)=>({...item,id:i.toString(16).padStart(40,'0')}));
  const f=fixture({items});
  for(const entry of items.slice(0,50)) assert.equal((await f.request({id:entry.id})).status,200);
  assert.equal((await f.request({id:items[50].id})).status,429);assert.equal(f.calls.ai.length,50);
  assert.equal((await f.request({id:items[0].id})).status,200);assert.equal(f.calls.ai.length,50);
});

test('KV ledger survives a fresh Worker instance; corrupt state fails closed',async()=>{
  const f=fixture({env:{AI_MAX_PER_DAY:'1'}});await f.request();
  const fresh=fixture({env:{SUMMARIES:f.env.SUMMARIES,AI_MAX_PER_DAY:'1'}});
  assert.equal((await fresh.request({id:other})).status,429);assert.equal(fresh.calls.ai.length,0);
  await fresh.env.SUMMARIES.put('last:'+other,'{"at":"not-a-date"}');
  assert.equal((await fresh.request({id:other})).status,429);
});

test('GitHub failure keeps the valid result and retries only dispatch after cooldown',async()=>{
  const f=fixture({gitStatus:500});
  const result=await (await f.request()).json();assert.equal(result.git_saved,false);
  await f.request();assert.equal(f.calls.git.length,1);assert.equal(f.calls.ai.length,1);
  f.advance(91000);await f.request();assert.equal(f.calls.git.length,2);assert.equal(f.calls.ai.length,1);
});

test('strict AI validation matches Python and rejects duplicate or escaped duplicate keys',()=>{
  for(const raw of ['{"neutral":"a","neutral":"b","mine":"c","topics":[]}','{"neutral":"a","\\u006eeutral":"b","mine":"c","topics":[]}']) assert.throws(()=>validate(raw,trusted.topics));
  for(const bad of [{...valid,neutral:'x'.repeat(601)},{...valid,mine:'<script>'},{...valid,topics:['unknown']},{...valid,url:'https://evil.example'},{...valid,topics:'ai'}]) assert.throws(()=>validate(JSON.stringify(bad),trusted.topics));
  assert.deepEqual(strictJSON('{"x":"{not a key}","nested":{"a":1}}'),{x:'{not a key}',nested:{a:1}});
});

test('robots rules, allow tie, agent specificity and wildcard endings',()=>{
  assert.equal(robotsAllowed('User-agent: *\nDisallow: /',item.url),false);
  assert.equal(robotsAllowed('User-agent: *\nDisallow: /\nAllow: /article$',item.url),true);
  assert.equal(robotsAllowed('User-agent: *\nDisallow: /\nUser-agent: Novice\nAllow: /',item.url),true);
  assert.equal(robotsAllowed('User-agent: *\nDisallow: /*?secret=',item.url+'?secret=1'),false);
  assert.equal(robotsAllowed('User-agent: *\nCrawl-delay: 5',item.url),false);
});

test('reader restricts domains on each redirect, respects robots and paywall, bounds text',async()=>{
  for(const url of ['http://127.0.0.1/a','https://source.example.evil/a','file:///a','https://u:p@source.example/a','https://source.example:8443/a']) assert.throws(()=>allowedURL(url,['source.example']));
  const calls=[];let mode='ok';
  const fetcher=async(url)=>{
    calls.push(url);
    if(url.endsWith('robots.txt')) return mode==='robots'?new Response('User-agent: *\nDisallow: /'):new Response('',{status:404});
    if(mode==='redirect') return new Response(null,{status:302,headers:{Location:'http://127.0.0.1/secret'}});
    if(mode==='paywall') return new Response('<script>{"isAccessibleForFree":false}</script>',{headers:{'Content-Type':'text/html'}});
    if(mode==='large') return new Response('x'.repeat(1_000_001),{headers:{'Content-Type':'text/html'}});
    return new Response('<article><p>Public science.</p></article>',{headers:{'Content-Type':'text/html'}});
  };
  const source={domains:['source.example']}, opts={fetcher,extract:async()=> 'Text '.repeat(5000)};
  const result=await readArticle(item,source,opts);assert.equal(result.text.length,12000);assert.equal(result.basis,'article');
  for(mode of ['robots','redirect','paywall','large']) {calls.length=0;const r=await readArticle(item,source,opts);assert.equal(r.basis,'excerpt');assert.equal(r.text,'');assert.ok(calls.every(x=>new URL(x).hostname==='source.example'));}
});
