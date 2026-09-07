// Deployed Edge Function. Custom bearer authentication is enforced by the scoped RPC.
const ORIGIN='https://macchiatopsk-create.github.io';
const ACTIONS={client:new Set(['status','enqueue','cancel']),worker:new Set(['poll','started','complete'])};
export async function handle(req,env,transport=fetch){
 const origin=req.headers.get('origin');
 const headers={'content-type':'application/json; charset=utf-8','cache-control':'no-store','x-content-type-options':'nosniff','vary':'Origin',...(origin===ORIGIN?{'access-control-allow-origin':ORIGIN}:{})};
 const json=(status,v)=>new Response(JSON.stringify(v),{status,headers});
 if(origin&&origin!==ORIGIN)return json(403,{error:'ORIGIN_DENIED'});
 if(req.method==='OPTIONS')return new Response(null,{status:204,headers:{...headers,'access-control-allow-methods':'POST','access-control-allow-headers':'authorization,content-type','access-control-max-age':'600'}});
 if(req.method!=='POST')return json(405,{error:'POST_REQUIRED'});
 const bearer=req.headers.get('authorization')||'';
 if(!/^Bearer [A-Za-z0-9_-]{43}$/.test(bearer))return json(401,{error:'UNAUTHORIZED'});
 if(!req.headers.get('content-type')?.startsWith('application/json'))return json(415,{error:'JSON_REQUIRED'});
 if(Number(req.headers.get('content-length'))>300000)return json(413,{error:'TOO_LARGE'});
 try{
  const reader=req.body?.getReader();if(!reader)return json(400,{error:'BAD_BODY'});
  const chunks=[];let n=0;while(true){const {value,done}=await reader.read();if(done)break;n+=value.byteLength;if(n>300000){await reader.cancel();return json(413,{error:'TOO_LARGE'});}chunks.push(value);}
  const bytes=new Uint8Array(n);let p=0;for(const c of chunks){bytes.set(c,p);p+=c.length;}
  const v=JSON.parse(new TextDecoder().decode(bytes));
  if(!v||typeof v!=='object'||Array.isArray(v)||typeof v.room!=='string'||!/^[a-z0-9-]{1,64}$/.test(v.room)||!Object.hasOwn(ACTIONS,v.role)||!ACTIONS[v.role].has(v.action)||!v.body||typeof v.body!=='object'||Array.isArray(v.body))return json(400,{error:'BAD_REQUEST'});
  const hash=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(bearer.slice(7))))).map(x=>x.toString(16).padStart(2,'0')).join('');
  const base=env('SUPABASE_URL'),service=env('SUPABASE_SERVICE_ROLE_KEY');
  if(!base||!service)return json(503,{error:'NOT_CONFIGURED'});
  const res=await transport(base+'/rest/v1/rpc/hq9_gateway',{method:'POST',headers:{'content-type':'application/json',apikey:service,Authorization:'Bearer '+service},body:JSON.stringify({p_room:v.room,p_hash:hash,p_role:v.role,p_action:v.action,p_body:v.body}),signal:AbortSignal.timeout(10000)});
  if(!res.ok)return json(502,{error:'RELAY_UNAVAILABLE'});
  const out=await res.json();if(!out||!Number.isInteger(out.http)||out.http<200||out.http>599)return json(502,{error:'RELAY_INVALID'});
  const status=out.http;delete out.http;return json(status,out);
 }catch{return json(400,{error:'REQUEST_FAILED'});}
}
if(typeof Deno!=='undefined')Deno.serve(req=>handle(req,k=>Deno.env.get(k)));
