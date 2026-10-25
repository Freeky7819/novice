import {test} from 'node:test';
import assert from 'node:assert/strict';
import {fileURLToPath} from 'node:url';
import {Miniflare,convertV4MiniflareOptions} from 'miniflare';
import {BASE,ORIGIN} from '../validation.js';
import trusted from '../generated.js';

test('real Workers runtime: native constant-time auth, HTMLRewriter, KV and fake provider/dispatch',async(t)=>{
  const id='d'.repeat(40), calls={ai:0,git:0}, paragraph='Scientists studied a distant star and measured changes in its brightness. ';
  const html='<html><body><nav><p>MENU MUST NOT BE SENT</p></nav><article><script>SECRET SCRIPT</script><h1>Public science report</h1><p>'+paragraph.repeat(20)+'</p><aside><p>AD MUST NOT BE SENT</p></aside></article></body></html>';
  const json=value=>new Response(JSON.stringify(value),{headers:{'Content-Type':'application/json'}});
  const mf=new Miniflare(convertV4MiniflareOptions({
    modules:['index.js','generated.js','article.js','validation.js'].map(name=>({type:'ESModule',path:fileURLToPath(new URL('../'+name,import.meta.url))})),
    modulesRoot:fileURLToPath(new URL('../',import.meta.url)),compatibilityDate:'2026-10-25',
    kvNamespaces:['SUMMARIES'],bindings:{NOVICE_KODA:'TEST_ONLY_RUNTIME_CODE',ANTHROPIC_API_KEY:'TEST_ONLY_AI',GITHUB_TOKEN_NOVICE:'TEST_ONLY_GITHUB',AI_MAX_PER_DAY:'50'},
    outboundService:async(request)=>{
      const u=request.url;
      if(u===BASE+'data/feed.json') return json({items:[{id,title:'Public science',excerpt:'RSS excerpt',source_id:'test',url:'https://source.example/article'}]});
      if(u===BASE+'data/config.json') return json({topics:trusted.topics.map(id=>({id})),sources:[{id:'test',name:'Test source',enabled:true,domains:['source.example']}]});
      if(u===BASE+'data/summaries.json') return json({});
      if(u==='https://source.example/robots.txt') return new Response('User-agent: *\nAllow: /',{headers:{'Content-Type':'text/plain'}});
      if(u==='https://source.example/article') return new Response(html,{headers:{'Content-Type':'text/html'}});
      if(u==='https://api.anthropic.com/v1/messages') {
        calls.ai++;
        const body=await request.json(), article=JSON.parse(body.messages[0].content);
        assert.ok(article.article_text.includes('Scientists studied'));
        assert.ok(!/MENU MUST|SECRET SCRIPT|AD MUST/.test(article.article_text));
        assert.ok(article.article_text.length<=12000);
        return json({stop_reason:'end_turn',content:[{type:'text',text:JSON.stringify({neutral:'Slovenski povzetek.',mine:'Po domače pojasnjeno.',topics:['znanost']})}]});
      }
      if(u==='https://api.github.com/repos/Freeky7819/novice/dispatches') {
        calls.git++;const body=await request.json();assert.equal(body.client_payload.id,id);assert.equal(body.client_payload.basis,'article');
        return new Response(null,{status:204});
      }
      throw new Error('All real network calls are forbidden in this test');
    }}));
  t.after(()=>mf.dispose());
  const post=(code,origin=ORIGIN)=>mf.dispatchFetch('https://worker.example/api/summary',{method:'POST',headers:{Origin:origin,'X-Novice-Koda':code,'Content-Type':'application/json'},body:JSON.stringify({id})});
  assert.equal((await post('wrong')).status,401);
  assert.equal((await post('TEST_ONLY_RUNTIME_CODE','https://evil.example')).status,403);
  const r=await post('TEST_ONLY_RUNTIME_CODE');assert.equal(r.status,200,await r.clone().text());
  assert.equal((await r.json()).basis,'article');assert.equal(calls.ai,1);assert.equal(calls.git,1);
  assert.equal((await post('TEST_ONLY_RUNTIME_CODE')).status,200);assert.equal(calls.ai,1);
  const kv=await mf.getKVNamespace('SUMMARIES'), cached=await kv.get('summary:'+id);
  assert.ok(cached.includes('Slovenski povzetek'));assert.ok(!cached.includes('Scientists studied'));
});
