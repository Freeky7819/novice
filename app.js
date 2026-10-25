'use strict';
const $ = (id) => document.getElementById(id);
const readLocal = (key, fallback) => { try { return JSON.parse(localStorage.getItem(key)) ?? fallback; } catch { return fallback; } };
const writeLocal = (key, value) => { try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* Private mode still works. */ } };
const stored = readLocal('novice:preferences', {});
const modes = {official:'Uradno', neutral:'Povzeto', mine:'Po domače'};
const prefs = {theme:'system',mode:'official',topics:{},sources:{}, ...(stored && typeof stored === 'object' ? stored : {})};
if(!Object.hasOwn(modes,prefs.mode)) prefs.mode='official';
const cardModes = new Map();
const pendingSummaries = new Map(), summaryErrors = new Map(), summaryViews = new Map();
const savedSummaries = readLocal('novice:summaries', {});
const preparedSummaries = new Map();
const basisLabels = {article:'Povzetek dostopnega besedila članka',public_part:'Povzetek samo javno dostopnega dela',excerpt:'Povzetek iz naslova in izvlečka',title:'Povzetek samo iz naslova'};
if (!prefs.topics || typeof prefs.topics !== 'object') prefs.topics = {};
if (!prefs.sources || typeof prefs.sources !== 'object') prefs.sources = {};
let config = {topics:[],sources:[]}, feed = {items:[]}, status = null, selected = 'all', limit = 30;
function element(tag, cls, text) { const node = document.createElement(tag); if(cls) node.className = cls; if(text !== undefined) node.textContent = text; return node; }
function safeLink(url) { try { const u = new URL(url); return ['https:','http:'].includes(u.protocol) && !u.username && !u.password ? u.href : null; } catch { return null; } }
function link(title, url) { const a = element('a','',title); const safe = safeLink(url); if(safe) { a.href = safe; a.target = '_blank'; a.rel = 'noopener noreferrer'; } return a; }
function savePrefs() { writeLocal('novice:preferences',prefs); applyTheme(); }
function applyTheme() { if(['dark','light'].includes(prefs.theme)) document.documentElement.dataset.theme = prefs.theme; else delete document.documentElement.dataset.theme; }
applyTheme();
function relative(value) { const date = new Date(value); if(!Number.isFinite(date.getTime())) return ''; const seconds = Math.max(0,(Date.now()-date.getTime())/1000); if(seconds < 3600) return `pred ${Math.max(1,Math.floor(seconds/60))} min`; if(seconds < 86400) return `pred ${Math.floor(seconds/3600)} h`; return `pred ${Math.floor(seconds/86400)} d`; }
function source(id) { return config.sources.find(s=>s.id===id)?.name || id; }
function topic(id) { return config.topics.find(t=>t.id===id)?.label || id; }
function renderTopics() {
  const nav = $('topics'); nav.replaceChildren();
  for(const t of [{id:'all',label:'Vse'},...config.topics.filter(t=>prefs.topics[t.id] !== false)]) {
    const b = element('button','chip'+(selected===t.id?' active':''), t.id==='strojna-oprema'?'GPU':t.label);
    b.setAttribute('aria-pressed',String(selected===t.id));
    b.addEventListener('click',()=>{ selected=t.id; limit=30; renderTopics(); render(); }); nav.append(b);
  }
}
function articleImage(item, article) {
  const url = item.source_id === 'gnews-us' ? null : safeLink(item.image);
  if(!url) { article.classList.add('compact'); return null; }
  const frame = element('div','article-image');
  frame.setAttribute('aria-hidden','true');
  if(item.image_is_thumbnail) article.classList.add('thumb');
  const img = element('img');
  img.alt = '';
  img.loading = 'lazy';
  img.decoding = 'async';
  img.referrerPolicy = 'no-referrer';
  img.addEventListener('load',()=>{frame.classList.add('image-loaded');article.classList.toggle('thumb',img.naturalWidth < 400);});
  img.addEventListener('error',()=>{frame.remove();article.classList.remove('thumb');article.classList.add('compact');},{once:true});
  img.src = url;
  frame.append(img);
  return frame;
}
function publisherName(item) {
  if(item.source_id !== 'gnews-us') return source(item.source_id);
  return item.publisher || (item.title.includes(' - ') ? item.title.slice(item.title.lastIndexOf(' - ')+3) : 'Google News');
}
function articleTitle(item) {
  if(item.source_id !== 'gnews-us') return item.title;
  const suffix = ' - ' + publisherName(item);
  return item.title.endsWith(suffix) ? item.title.slice(0,-suffix.length) : item.title;
}
function validSummary(value) {
  return value && typeof value==='object' && ['neutral','mine'].every(k=>typeof value[k]==='string' && value[k].trim() && value[k].length<=600) && Array.isArray(value.topics) && value.topics.every(t=>config.topics.some(topic=>topic.id===t));
}
function cachedSummary(item) {
  const prepared=preparedSummaries.get(item.id) || (savedSummaries && savedSummaries[item.id]);
  return validSummary(prepared)?prepared:null;
}
function hasSummary(item,mode) {
  return Boolean(cachedSummary(item) || (mode==='neutral'?item.summary_neutral:item.summary_mine));
}
function requestSummary(item) {
  if(pendingSummaries.has(item.id)) return pendingSummaries.get(item.id);
  summaryErrors.delete(item.id);
  const promise=(async()=>{
    const controller=new AbortController();
    const timer=setTimeout(()=>controller.abort(),90000);
    try {
      const response=await fetch('api/summary',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:item.id}),signal:controller.signal});
      if([404,405,501].includes(response.status)) throw new Error('Povzemanje na tej strani še ni omogočeno. Za zdaj lahko bereš shranjene povzetke.');
      let result;
      try {result=await response.json();} catch {throw new Error('Povzemanje trenutno ni povezano s storitvijo.');}
      if(!response.ok) throw new Error(result.message || 'Povzetka trenutno ni mogoče pripraviti. Poskusi pozneje.');
      if(result.id!==item.id || !validSummary(result)) throw new Error('Povzetek ni bil veljaven. Poskusi pozneje.');
      const value={neutral:result.neutral,mine:result.mine,topics:result.topics,basis:result.basis};
      preparedSummaries.set(item.id,value);
      const cache=Object.fromEntries([...preparedSummaries.entries()]);
      // Keep at most the current feed's entries on this device.
      for(const entry of feed.items) {const previous=cachedSummary(entry);if(previous)cache[entry.id]=previous;}
      writeLocal('novice:summaries',cache);
    } catch(error) {
      summaryErrors.set(item.id,error.name==='AbortError'?'Povzemanje traja predolgo. Poskusi pozneje.':error.message || 'Povzemanje trenutno ni na voljo.');
    } finally {
      clearTimeout(timer);
    }
  })().finally(()=>{pendingSummaries.delete(item.id);summaryViews.get(item.id)?.();});
  pendingSummaries.set(item.id,promise);
  return promise;
}
function card(item) {
  const article = element('article','article');
  const top = element('div','article-top');
  const name = publisherName(item);
  top.append(element('span','source-mark',name.slice(0,1)),element('span','source-name',name));
  if(item.source_id==='gnews-us') top.append(element('span','via','· prek Google News'));
  top.append(element('span','','·'));
  const time = element('time','',relative(item.published)); time.dateTime = item.published; time.title = new Date(item.published).toLocaleString('sl-SI'); top.append(time);
  const heading = element('h3'); heading.append(link(articleTitle(item),item.url));
  const lead = element('div','article-lead');
  const picture = articleImage(item,article);
  if(picture) lead.append(picture);
  lead.append(heading);
  article.append(top,lead);
  const summary = element('p','excerpt');
  article.append(summary);
  const bottom = element('div','article-bottom'), tags = element('div','tags');
  for(const t of item.topics || []) tags.append(element('span','tag',topic(t)));
  const original=link('Preberi izvirnik ↗',item.url); original.className='original';
  bottom.append(tags,original); article.append(bottom);
  const toggle=element('div','summary-toggle');
  const availability=element('p','summary-availability');
  availability.setAttribute('role','status');
  toggle.setAttribute('role','group');
  toggle.setAttribute('aria-label','Način povzetka');
  const buttons=new Map();
  function updateSummary() {
    const chosen=cardModes.get(item.id) || prefs.mode;
    const cached=cachedSummary(item);
    const candidate=chosen==='neutral'?(cached?.neutral || item.summary_neutral):chosen==='mine'?(cached?.mine || item.summary_mine):null;
    const effective=chosen!=='official' && typeof candidate==='string' && candidate.trim() ? chosen : 'official';
    const busy=pendingSummaries.has(item.id);
    article.setAttribute('aria-busy',String(busy));
    if(chosen==='official') availability.textContent='';
    else if(busy) availability.textContent='Pripravljam povzetek …';
    else if(summaryErrors.has(item.id)) availability.textContent=summaryErrors.get(item.id);
    else if(effective==='official') availability.textContent='Klikni Povzeto ali Po domače in pripravil se bo povzetek tega članka.';
    else availability.textContent=basisLabels[cached?.basis] || (item.excerpt?basisLabels.excerpt:basisLabels.title);
    availability.hidden=!availability.textContent;
    summary.textContent=effective==='official'?(item.excerpt || ''):candidate;
    summary.hidden=!summary.textContent;
    article.classList.toggle('has-ai-summary',effective!=='official');
    for(const [mode,button] of buttons) button.setAttribute('aria-pressed',String(mode===effective));
  }
  for(const [mode,label] of Object.entries(modes)) {
    const button=element('button','',label);
    button.type='button';
    button.addEventListener('click',async()=>{
      cardModes.set(item.id,mode);
      if(mode!=='official' && !hasSummary(item,mode)) {
        const work=requestSummary(item);
        updateSummary();
        await work;
      }
      updateSummary();
    });
    buttons.set(mode,button);toggle.append(button);
  }
  summaryViews.set(item.id,updateSummary);
  updateSummary();article.append(toggle,availability);
  return article;
}
function render() {
  summaryViews.clear();
  $('mode-indicator').textContent='Privzeto · '+modes[prefs.mode];
  const filtered=feed.items.filter(i=>safeLink(i.url) && prefs.sources[i.source_id]!==false && config.sources.some(s=>s.id===i.source_id && s.enabled!==false) && (i.topics||[]).some(t=>prefs.topics[t]!==false) && (selected==='all'||i.topics.includes(selected)));
  $('feed-title').textContent=selected==='all'?'Tvoj izbor':topic(selected);
  $('count').textContent=`${filtered.length} člankov`;
  $('feed').replaceChildren(...filtered.slice(0,limit).map(card));
  if(!filtered.length) $('feed').append(element('div','empty','Tu je za zdaj mirno. Izberi drugo temo ali v nastavitvah vključi več virov.'));
  $('feed').setAttribute('aria-busy','false'); $('more').hidden=filtered.length<=limit;
}
function toggleSettings(target, entries, pref) {
  target.replaceChildren();
  for(const entry of entries) { const label=element('label','toggle-row',entry.label||entry.name), input=element('input'); input.type='checkbox'; input.checked=pref[entry.id]!==false; input.addEventListener('change',()=>{pref[entry.id]=input.checked;savePrefs();if(selected!=='all'&&prefs.topics[selected]===false)selected='all';renderTopics();render();}); label.append(input);target.append(label); }
}
function settings() { toggleSettings($('topic-settings'),config.topics,prefs.topics); toggleSettings($('source-settings'),config.sources.filter(s=>s.enabled!==false),prefs.sources); $('theme').value=['dark','light'].includes(prefs.theme)?prefs.theme:'system'; $('default-mode').value=prefs.mode; const bad=(status?.sources||[]).filter(s=>!s.ok); $('source-status').textContent=bad.length?`Trenutno nedosegljivi viri: ${bad.map(s=>source(s.id)).join(', ')}. Ostale novice se osvežujejo normalno.`:'Viri se preverjajo ob vsakem zajemu.'; }
async function json(path) { const response=await fetch(path,{cache:'no-cache'}); if(!response.ok) throw new Error('Podatki niso dosegljivi'); return response.json(); }
async function refresh() {
  $('refresh').disabled=true;
  try {
    const [nextConfig,nextFeed,nextStatus]=await Promise.all([json('data/config.json'),json('data/feed.json'),json('data/status.json').catch(()=>null)]);
    if(!Array.isArray(nextFeed.items)||!Array.isArray(nextConfig.topics)||!Array.isArray(nextConfig.sources)) throw new Error('Neveljavni podatki');
    config=nextConfig; feed=nextFeed; status=nextStatus;
    $('connection').textContent='Preverjeno '+relative(status?.checked_at||feed.generated_at);
    $('notice').textContent=''; renderTopics();settings();render();
  } catch {
    $('connection').textContent='Povezava ni na voljo';
    $('notice').textContent='Novic trenutno ni mogoče naložiti. Preveri povezavo in poskusi znova.';
    if(!feed.items.length) { $('feed').replaceChildren(element('div','empty','Tvoj izbor čaka na prvi zajem novic.')); $('feed').setAttribute('aria-busy','false'); }
  } finally { $('refresh').disabled=false; }
}
$('today').textContent=new Intl.DateTimeFormat('sl-SI',{weekday:'long',day:'numeric',month:'long'}).format(new Date());
$('refresh').addEventListener('click',refresh);
$('settings').addEventListener('click',()=>{$('preferences').showModal();});
$('preferences').addEventListener('click',e=>{if(e.target===$('preferences')){const r=e.target.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)e.target.close();}});
$('theme').addEventListener('change',e=>{prefs.theme=e.target.value;savePrefs();});
$('default-mode').addEventListener('change',e=>{prefs.mode=e.target.value;savePrefs();render();});
$('more').addEventListener('click',()=>{limit+=30;render();});
window.addEventListener('online',refresh);
window.addEventListener('offline',()=>{$('connection').textContent='Povezava ni na voljo';});
refresh();
if('serviceWorker' in navigator) navigator.serviceWorker.register('sw.js').catch(()=>{});
