import trusted from './generated.js';
import {readArticle} from './article.js';
import {BASE,ORIGIN,BASES,Failure,strictJSON,exactKeys,validId,validate,schema,boundedText,response} from './validation.js';

export function createWorker({fetcher=(...args)=>fetch(...args),cryptoAPI=crypto,clock=()=>Date.now(),reader=readArticle}={}) {
  // Only public data and conservative in-isolate guards, never secrets/prompts or
  // promises owned by a different request. KV is eventually consistent: see docs.
  const publicCache=new Map(), busy=new Set(), localUsage=new Map();
  async function publicJSON(path, optional=false) {
    const hit=publicCache.get(path);
    if(hit && hit.until>clock()) return hit.value;
    const controller=new AbortController(), timer=setTimeout(()=>controller.abort(),15000);
    try {
      const r=await fetcher(BASE+path,{redirect:'manual',signal:controller.signal,cache:'no-store'});
      if(optional && r.status===404) return {};
      if(!r.ok) {await r.body?.cancel();throw new Error('Pages unavailable');}
      const value=strictJSON(await boundedText(r,8_000_000,controller.signal));
      publicCache.set(path,{value,until:clock()+300000});
      return value;
    } finally {clearTimeout(timer);}
  }
  async function authorized(provided,expected) {
    const encoder=new TextEncoder();
    const hashes=await Promise.all([provided,expected].map(x=>cryptoAPI.subtle.digest('SHA-256',encoder.encode(x))));
    return cryptoAPI.subtle.timingSafeEqual(hashes[0],hashes[1]);
  }
  function eligible(item,source) {
    if(!source || source.enabled!==true) return false;
    return !trusted.exclude_keywords.some(word=>{
      const escaped=word.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
      const uppercase=word===word.toUpperCase() && /\p{L}/u.test(word);
      return new RegExp('(?<![\\p{L}\\p{N}_])'+escaped+'(?![\\p{L}\\p{N}_])',uppercase?'u':'iu').test(item.title+' '+item.excerpt);
    });
  }
  async function attemptCount(kv,day) {
    let count=0,cursor;
    do {
      const list=await kv.list({prefix:'attempt:'+day+':',...(cursor?{cursor}:{})});
      count+=list.keys.length;cursor=list.list_complete?null:list.cursor;
      if(!list.list_complete && !cursor) throw new Error('Invalid KV listing');
    } while(cursor);
    return count;
  }
  async function dispatch(env,id,value) {
    if(!env.GITHUB_TOKEN_NOVICE) return false;
    const previous=await env.SUMMARIES.get('dispatch:'+id,'json');
    if(previous?.ok) return true;
    if(previous && clock()-previous.at<90000) return false;
    const controller=new AbortController(), timer=setTimeout(()=>controller.abort(),10000);
    let ok=false;
    try {
      const payload={id,neutral:value.neutral,mine:value.mine,topics:value.topics,basis:value.basis,model:value.model,created_at:value.created_at};
      const r=await fetcher('https://api.github.com/repos/Freeky7819/novice/dispatches',{
        method:'POST',redirect:'manual',signal:controller.signal,
        headers:{'Authorization':'Bearer '+env.GITHUB_TOKEN_NOVICE,'Accept':'application/vnd.github+json',
          'X-GitHub-Api-Version':'2022-11-28','User-Agent':'Novice-Worker','Content-Type':'application/json'},
        body:JSON.stringify({event_type:'povzetek',client_payload:payload})});
      ok=r.status===204;await r.body?.cancel();
    } catch { /* Keep the valid summary; a later click can retry dispatch. */ }
    finally {clearTimeout(timer);}
    await env.SUMMARIES.put('dispatch:'+id,JSON.stringify({ok,at:clock()}));
    return ok;
  }
  async function summarize(id,env) {
    const [feed,config]=await Promise.all([publicJSON('data/feed.json'),publicJSON('data/config.json')]);
    const item=feed.items?.find(i=>i.id===id);
    if(!item) throw new Failure(404,'unknown_article','Ta članek ni več v izboru novic.');
    const source=config.sources?.find(s=>s.id===item.source_id);
    if(!eligible(item,source)) throw new Failure(403,'excluded','Povzemanje tega članka je izključeno.');
    const allowed=trusted.topics.filter(t=>config.topics?.some(x=>x.id===t));
    const cached=await env.SUMMARIES.get('summary:'+id,'json');
    if(cached) {
      const value=validate(JSON.stringify({neutral:cached.neutral,mine:cached.mine,topics:cached.topics}),allowed);
      if(!BASES.has(cached.basis)) throw new Error('Invalid cache');
      const git_saved=await dispatch(env,id,cached).catch(()=>false);
      return {id,...value,basis:cached.basis,cached:true,git_saved};
    }
    const previous=await publicJSON('data/summaries.json',true);
    if(previous[id]?.status==='ok') {
      try {
        const value=validate(JSON.stringify(previous[id].result),allowed);
        return {id,...value,basis:BASES.has(previous[id].basis)?previous[id].basis:item.excerpt?'excerpt':'title',cached:true,git_saved:true};
      } catch { /* An invalid legacy result must never reach the page. */ }
    }
    if(!env.ANTHROPIC_API_KEY || !env.GITHUB_TOKEN_NOVICE) throw new Failure(503,'not_configured');
    const now=clock(), day=new Date(now).toISOString().slice(0,10);
    const max=env.AI_MAX_PER_DAY??'50';
    if(!/^\d+$/.test(String(max)) || !Number.isSafeInteger(Number(max))) throw new Failure(503,'configuration');
    const last=await env.SUMMARIES.get('last:'+id,'json');
    if(last && (!Number.isFinite(last.at) || now-last.at<90000)) throw new Failure(429,'cooldown','Poskusi znova čez minuto in pol.');
    const used=Math.max(localUsage.get(day)||0,await attemptCount(env.SUMMARIES,day));
    if(used>=Number(max)) throw new Failure(429,'daily_limit','Današnji limit povzetkov je dosežen. Shranjeni povzetki ostajajo na voljo.');
    localUsage.clear();localUsage.set(day,used+1);
    // Unique immutable ledger keys avoid lost increments from overwriting a KV
    // counter. KV has no atomic compare-and-set, so this is not a global hard cap.
    await env.SUMMARIES.put('attempt:'+day+':'+id+':'+cryptoAPI.randomUUID(),JSON.stringify({id,at:now}),{expirationTtl:259200});
    await env.SUMMARIES.put('last:'+id,JSON.stringify({at:now}),{expirationTtl:86400});
    const {text,basis}=await reader(item,source,{fetcher});
    const controller=new AbortController(), timer=setTimeout(()=>controller.abort(),45000);
    let result;
    try {
      const r=await fetcher('https://api.anthropic.com/v1/messages',{
        method:'POST',redirect:'manual',signal:controller.signal,
        headers:{'Authorization':'Bearer '+env.ANTHROPIC_API_KEY,'anthropic-version':'2026-10-21','Content-Type':'application/json'},
        body:JSON.stringify({model:trusted.model,max_tokens:trusted.max_tokens,system:trusted.system,
          messages:[{role:'user',content:JSON.stringify({title:item.title.slice(0,500),excerpt:(item.excerpt||'').slice(0,400),source:source.name.slice(0,150),article_text:text.slice(0,12000)})}],
          output_config:{format:{type:'json_schema',schema:schema(allowed)}}})});
      if(!r.ok) {await r.body?.cancel();throw new Error('AI unavailable');}
      const message=strictJSON(await boundedText(r,65536,controller.signal));
      if(message.stop_reason!=='end_turn') throw new Error('Incomplete answer');
      result=validate(message.content.filter(c=>c.type==='text').map(c=>c.text).join(''),allowed);
    } catch {throw new Failure(502,'summary_failed','Povzetka trenutno ni bilo mogoče pripraviti. Poskusi pozneje.');}
    finally {clearTimeout(timer);}
    const value={...result,basis,model:trusted.model,created_at:new Date(clock()).toISOString()};
    await env.SUMMARIES.put('summary:'+id,JSON.stringify(value));
    const git_saved=await dispatch(env,id,value).catch(()=>false);
    return {id,...result,basis,cached:false,git_saved};
  }
  return {
    async fetch(request,env) {
      const origin=request.headers.get('Origin');
      if(origin!==ORIGIN) return response(403,{error:'forbidden'});
      try {
        if(new URL(request.url).pathname!=='/api/summary') return response(404,{error:'not_found'},true);
        if(request.method==='OPTIONS') {
          const headers=(request.headers.get('Access-Control-Request-Headers')||'').toLowerCase().split(',').map(x=>x.trim()).filter(Boolean);
          if(request.headers.get('Access-Control-Request-Method')!=='POST' || headers.some(h=>!['content-type','x-novice-koda'].includes(h))) return response(403,{error:'forbidden'},true);
          const r=response(204,null,true);
          r.headers.set('Access-Control-Allow-Methods','POST');r.headers.set('Access-Control-Allow-Headers','Content-Type, X-Novice-Koda');r.headers.set('Access-Control-Max-Age','600');
          return r;
        }
        if(request.method!=='POST') return response(405,{error:'method_not_allowed'},true);
        if(!env.NOVICE_KODA) throw new Failure(503,'not_configured');
        if(!await authorized(request.headers.get('X-Novice-Koda')||'',env.NOVICE_KODA)) return response(401,{error:'unauthorized'},true);
        if((request.headers.get('Content-Type')||'').split(';')[0].trim().toLowerCase()!=='application/json') return response(415,{error:'json_required'},true);
        let data;
        try {
          data=strictJSON(await boundedText(request,4096,AbortSignal.timeout(5000)));
          if(!exactKeys(data,['id']) || !validId(data.id)) throw new Error('Invalid id');
        } catch {return response(400,{error:'invalid_request'},true);}
        if(busy.has(data.id)) throw new Failure(429,'cooldown','Povzetek se že pripravlja. Poskusi čez minuto in pol.');
        busy.add(data.id);
        try {return response(200,await summarize(data.id,env),true);}
        finally {busy.delete(data.id);}
      } catch(error) {
        return response(error instanceof Failure?error.status:503,
          {error:error instanceof Failure?error.code:'unavailable',message:error instanceof Failure?error.message:'Povzemanje trenutno ni na voljo. Poskusi pozneje.'},true);
      }
    }
  };
}
export default createWorker();
