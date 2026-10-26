import {boundedText} from './validation.js';
const AGENT='Novice/3.0 (personal news reader)';

export function allowedURL(raw, domains) {
  const u=new URL(raw);
  if(!['http:','https:'].includes(u.protocol) || u.username || u.password || u.port || !domains.includes(u.hostname) ||
     u.hostname==='localhost' || !u.hostname.includes('.') || /^[\d.]+$/.test(u.hostname) || u.hostname.includes(':')) throw new Error('URL not allowed');
  return u.href;
}

export function robotsAllowed(text,url) {
  const groups=[];let group=null,hasRules=false;
  for(const raw of text.split(/\r?\n/)) {
    const line=raw.split('#')[0].trim(), colon=line.indexOf(':');
    if(colon<0) continue;
    const key=line.slice(0,colon).trim().toLowerCase(), value=line.slice(colon+1).trim();
    if(key==='user-agent') {
      if(!group || hasRules) {group={agents:[],rules:[],delay:false};groups.push(group);hasRules=false;}
      group.agents.push(value.toLowerCase());
    } else if(group) {
      hasRules=true;
      if(key==='crawl-delay' || key==='request-rate') group.delay=true;
      if(['allow','disallow'].includes(key) && value) group.rules.push({allow:key==='allow',path:value});
    }
  }
  const specific=groups.filter(g=>g.agents.some(a=>a!=='*' && 'novice'.startsWith(a)));
  const best=specific.length?Math.max(...specific.map(g=>Math.max(...g.agents.filter(a=>a!=='*' && 'novice'.startsWith(a)).map(a=>a.length)))):0;
  const active=best?specific.filter(g=>g.agents.some(a=>a.length===best && 'novice'.startsWith(a))):groups.filter(g=>g.agents.includes('*'));
  if(active.some(g=>g.delay)) return false;
  const u=new URL(url), target=u.pathname+u.search;
  let winner={length:-1,allow:true};
  for(const rule of active.flatMap(g=>g.rules)) {
    const end=rule.path.endsWith('$'), path=end?rule.path.slice(0,-1):rule.path;
    const pattern=path.split('*').map(p=>p.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')).join('.*');
    const length=path.replaceAll('*','').length;
    if(new RegExp('^'+pattern+(end?'$':'')).test(target) && (length>winner.length || (length===winner.length && rule.allow))) winner={length,allow:rule.allow};
  }
  return winner.allow;
}

async function get(fetcher,url,domains,signal,limit) {
  const safe=allowedURL(url,domains);
  const result=await fetcher(safe,{redirect:'manual',signal,headers:{'User-Agent':AGENT,'Accept':'text/html,text/plain;q=0.9'}});
  if(result.status>=300 && result.status<400) {await result.body?.cancel();return {status:result.status,location:result.headers.get('location')};}
  const body=await boundedText(result,limit,signal);
  return {status:result.status,body,type:result.headers.get('content-type')||''};
}

async function robots(fetcher,url,domains,signal) {
  let address=new URL('/robots.txt',url).href;
  for(let i=0;i<3;i++) {
    const r=await get(fetcher,address,domains,signal,65536);
    if(r.location) {address=new URL(r.location,address).href;continue;}
    if([404,410].includes(r.status)) return true;
    return r.status===200 && !r.type.includes('html') && robotsAllowed(r.body,url);
  }
  return false;
}

export async function extractHTML(html) {
  // Collect article/main paragraphs only, omitting scripts, menus, ads and hidden
  // descendants. No guessed full-body fallback that could summarize navigation.
  const buffers={article:'',main:''};let article=0,main=0,skip=0;
  const enter=(name)=>({element(el){
    if(['area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr'].includes(el.tagName)) return;
    if(name==='article') article++; else if(name==='main') main++; else skip++;
    el.onEndTag(()=>{if(name==='article')article--;else if(name==='main')main--;else skip--;});
  }});
  const rewriter=new HTMLRewriter()
    .on('article',enter('article')).on('main, [role="main"]',enter('main'))
    .on('script, style, noscript, nav, header, footer, aside, form, [hidden], [aria-hidden="true"]',enter('skip'))
    .on('p, h1, h2, h3, li',{text(chunk){
      if(skip) return;
      const key=article?'article':main?'main':null;
      if(key && buffers[key].length<14000) buffers[key]+=chunk.text.slice(0,14000-buffers[key].length)+(chunk.lastInTextNode?' ':'');
    }});
  await rewriter.transform(new Response(html)).arrayBuffer();
  return (buffers.article || buffers.main).replace(/\s+/g,' ').trim().slice(0,12000);
}

export async function readArticle(item,source,{fetcher=fetch,extract=extractHTML}={}) {
  const fallback={text:'',basis:item.excerpt?'excerpt':'title'};
  const controller=new AbortController(), timer=setTimeout(()=>controller.abort(),15000);
  try {
    let url=allowedURL(item.url,source.domains||[]);
    for(let i=0;i<4;i++) {
      if(!await robots(fetcher,url,source.domains,controller.signal)) return fallback;
      const r=await get(fetcher,url,source.domains,controller.signal,1_000_000);
      if(r.location) {url=allowedURL(new URL(r.location,url).href,source.domains);continue;}
      if(r.status!==200 || !r.type.toLowerCase().includes('html') || /["']isAccessibleForFree["']\s*:\s*(?:false|["']false["'])/i.test(r.body) || /<[^>]+(?:id|class)=["'][^"']*paywall/i.test(r.body)) return fallback;
      const text=(await extract(r.body)).slice(0,12000);
      controller.signal.throwIfAborted();
      return text?{text,basis:text.length<800?'public_part':'article'}:fallback;
    }
  } catch {return fallback;} finally {clearTimeout(timer);}
  return fallback;
}
