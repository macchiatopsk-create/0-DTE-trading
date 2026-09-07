/* HQ v10 presence overlay. Green is reserved for verified local process + fresh heartbeat. */
'use strict';
(function(){
 const COLORS={working:'작업중',claimed:'클레임됨',queued:'대기',review:'검토 대기',blocked:'차단',failed:'실패',idle:'대기',unknown:'미확인'};
 const OFFICE_IDS=['owner','codex','fable','claude','opus','studio','chief'];
 const MEETING_IDS=['owner','astra','fable','codex','chief'];
 const clean=s=>String(s||'').replace(/\s+/g,' ').trim();
 function laneTask(id){try{const list=Array.isArray(data?.issues)?data.issues:[];return list.find(t=>typeof laneOf==='function'&&laneOf(t)===id)||null;}catch{return null;}}
 function runner(id){try{return (Array.isArray(data?.runners)?data.runners:[]).find(r=>r?.lane===id)||null;}catch{return null;}}
 function fresh(r){const at=Date.parse(r?.observedAt);return Number.isFinite(at)&&Date.now()-at<90000;}
 function presence(id){
   if(id==='owner')return {kind:'idle',label:'대기',task:null,runner:null};
   const r=runner(id),t=laneTask(id);
   if(r&&fresh(r)&&r.processVerified===true&&r.heartbeatFresh===true&&r.status==='WORKING')return {kind:'working',label:'작업중',task:t,runner:r};
   const ls=t?.labels||[];
   if(ls.includes('blocked'))return {kind:'blocked',label:'차단',task:t,runner:r};
   if(ls.some(x=>String(x).endsWith('-review')))return {kind:'review',label:'검토 대기',task:t,runner:r};
   if(ls.some(x=>String(x).endsWith('-running')))return {kind:'claimed',label:'클레임됨',task:t,runner:r};
   if(ls.some(x=>String(x).endsWith('-ready')))return {kind:'queued',label:'대기',task:t,runner:r};
   if(t?.state==='closed'||ls.includes('done'))return {kind:'idle',label:'대기',task:t,runner:r};
   return {kind:'idle',label:'대기',task:t,runner:r};
 }
 function decorate(el,id){
   if(!el)return;const p=presence(id);el.dataset.presence=p.kind;
   let label=el.querySelector('strong,.seat-name,.tag')||el;
   if(!label.dataset.baseName)label.dataset.baseName=clean(label.textContent).replace(/^(●|•)\s*/,'').replace(/\s+(작업중|클레임됨|검토 대기|대기|차단|실패|미확인)$/,'');
   label.replaceChildren();
   const dot=document.createElement('i');dot.className='presence-dot';dot.setAttribute('aria-hidden','true');
   const name=document.createElement('span');name.className='presence-name';name.textContent=label.dataset.baseName;
   const state=document.createElement('small');state.className='presence-word';state.textContent=p.label;
   label.append(dot,name,state);
   const title=p.task?`#${p.task.number} ${p.task.title}`:p.label;
   el.setAttribute('aria-label',`${label.dataset.baseName} · ${p.label} · ${title}`);
 }
 function meetingId(el){
   const attr=el.dataset?.meeting||el.dataset?.meetingSeat||el.dataset?.seat||el.dataset?.person||'';
   if(MEETING_IDS.includes(attr))return attr;
   const text=clean(el.textContent).toLowerCase();
   if(text.includes('astra'))return'astra';if(text.includes('fable'))return'fable';if(text.includes('codex'))return'codex';if(text.includes('총지휘'))return'chief';if(text.includes('형님'))return'owner';return null;
 }
 function paint(){
   for(const id of OFFICE_IDS)decorate(document.getElementById('room-'+id),id);
   const root=document.getElementById('meeting-panel');if(root){
     const candidates=[...root.querySelectorAll('button.meeting-agent,button.meeting-seat,.meeting-agent button,.meeting-seat button,[data-meeting],[data-meeting-seat]')];
     for(const el of candidates){const id=meetingId(el);if(id)decorate(el,id);}
   }
   const note=document.getElementById('presence-summary-v10');if(note){const all=MEETING_IDS.map(presence);note.textContent=`작업중 ${all.filter(x=>x.kind==='working').length} · 클레임 ${all.filter(x=>x.kind==='claimed').length} · 검토 ${all.filter(x=>x.kind==='review').length} · 대기 ${all.filter(x=>x.kind==='idle'||x.kind==='queued').length}`;}
 }
 function addSummary(){const panel=document.getElementById('office-panel');if(!panel||document.getElementById('presence-summary-v10'))return;const bar=document.createElement('div');bar.id='presence-summary-v10';bar.className='source-pill';bar.style.cssText='position:absolute;left:12px;bottom:55px;z-index:8;max-width:78%;';panel.querySelector('.scene')?.append(bar);}
 addSummary();
 const prior=typeof refresh==='function'?refresh:null;if(prior){window.refresh=function(){const out=prior.apply(this,arguments);queueMicrotask(paint);return out;};}
 const priorClear=typeof clearPrivate==='function'?clearPrivate:null;if(priorClear){window.clearPrivate=function(){const out=priorClear.apply(this,arguments);queueMicrotask(paint);return out;};}
 document.addEventListener('visibilitychange',()=>{if(!document.hidden)paint();});
 setInterval(paint,10000);queueMicrotask(paint);
 window.HQPresence10={presence,paint};
})();
