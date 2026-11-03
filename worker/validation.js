export const BASE = 'https://freeky7819.github.io/novice/';
export const ORIGIN = 'https://freeky7819.github.io';
export const BASES = new Set(['article','public_part','excerpt','title']);
export class Failure extends Error {
  constructor(status, code, message='Povzemanje trenutno ni na voljo. Poskusi pozneje.') {
    super(message); this.status=status; this.code=code;
  }
}
export function strictJSON(raw) {
  const value=JSON.parse(raw), stack=[];
  // JSON.parse validates grammar first; this second pass rejects duplicate keys,
  // including escaped keys, at every nesting level, like Python unique_object.
  const token=/"(?:[^"\\]|\\.)*"|[{}\[\]]/g;
  let match;
  while((match=token.exec(raw))) {
    const text=match[0];
    if(text==='{') stack.push(new Set());
    else if(text==='[') stack.push(null);
    else if(text==='}' || text===']') stack.pop();
    else if(/^\s*:/.test(raw.slice(token.lastIndex))) {
      const key=JSON.parse(text), keys=stack.at(-1);
      if(keys.has(key)) throw new Error('Duplicate key');
      keys.add(key);
    }
  }
  return value;
}
export function exactKeys(value, keys) {
  return value && typeof value==='object' && !Array.isArray(value) && Object.keys(value).length===keys.length && keys.every(k=>Object.hasOwn(value,k));
}
export function validId(id) { return typeof id==='string' && /^[0-9a-f]{40}$/.test(id); }
export function validate(raw, allowed) {
  if(typeof raw!=='string' || [...raw].length>8192) throw new Error('Invalid response');
  const value=strictJSON(raw);
  if(!exactKeys(value,['neutral','mine','topics'])) throw new Error('Invalid shape');
  for(const key of ['neutral','mine']) {
    if(typeof value[key]!=='string' || !value[key].trim() || [...value[key]].length>600 || /[<>]/.test(value[key])) throw new Error('Invalid summary');
    value[key]=value[key].trim();
  }
  if(!Array.isArray(value.topics) || value.topics.length>allowed.length || value.topics.some(t=>typeof t!=='string' || !allowed.includes(t))) throw new Error('Invalid topics');
  value.topics=[...new Set(value.topics)].sort();
  return value;
}
export function schema(allowed) {
  return {type:'object',additionalProperties:false,required:['neutral','mine','topics'],properties:{
    neutral:{type:'string'},mine:{type:'string'},topics:{type:'array',items:{type:'string',enum:allowed}}}};
}
export async function boundedText(response, max, signal) {
  if(Number(response.headers.get('content-length'))>max) throw new Error('Too large');
  if(!response.body) return '';
  const reader=response.body.getReader(), chunks=[];
  let size=0;
  const cancel=()=>{reader.cancel().catch(()=>{});};
  signal?.addEventListener('abort',cancel,{once:true});
  try {
    for(;;) {
      signal?.throwIfAborted();
      const {done,value}=await reader.read();
      signal?.throwIfAborted();
      if(done) break;
      size+=value.byteLength;
      if(size>max) throw new Error('Too large');
      chunks.push(value);
    }
    const buffer=new Uint8Array(size); let offset=0;
    for(const chunk of chunks) {buffer.set(chunk,offset);offset+=chunk.byteLength;}
    return new TextDecoder().decode(buffer);
  } finally {signal?.removeEventListener('abort',cancel);await reader.cancel().catch(()=>{});}
}
export function response(status,value,cors=false) {
  return new Response(status===204?null:JSON.stringify(value),{status,headers:{
    'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store','X-Content-Type-Options':'nosniff','Vary':'Origin',
    ...(cors?{'Access-Control-Allow-Origin':ORIGIN}:{})}});
}
