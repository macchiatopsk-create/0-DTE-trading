(()=>{
  const order=['ops','review','logs','system'];
  let current=0, startX=0, startY=0, tracking=false;
  function go(id,dir=0){
    const next=Math.max(0,order.indexOf(id));
    document.querySelectorAll('.screen').forEach(s=>{
      const on=s.id===id;
      s.classList.toggle('active',on);
      if(on){s.animate([{opacity:.25,transform:`translateX(${dir>0?'26px':dir<0?'-26px':'0'})`},{opacity:1,transform:'translateX(0)'}],{duration:180,easing:'cubic-bezier(.2,.8,.2,1)'});}
    });
    document.querySelectorAll('[data-tab]').forEach(b=>b.classList.toggle('active',b.dataset.tab===id));
    current=next;
  }
  document.querySelectorAll('[data-tab]').forEach(b=>b.addEventListener('click',()=>go(b.dataset.tab,order.indexOf(b.dataset.tab)>current?1:-1)));
  const main=document.querySelector('main');
  if(main){
    main.style.touchAction='pan-y';
    main.addEventListener('touchstart',e=>{if(e.touches.length!==1)return;startX=e.touches[0].clientX;startY=e.touches[0].clientY;tracking=true},{passive:true});
    main.addEventListener('touchend',e=>{if(!tracking)return;tracking=false;const t=e.changedTouches[0],dx=t.clientX-startX,dy=t.clientY-startY;if(Math.abs(dx)<55||Math.abs(dx)<Math.abs(dy)*1.25)return;if(dx<0&&current<order.length-1)go(order[current+1],1);if(dx>0&&current>0)go(order[current-1],-1)},{passive:true});
  }
  const heroMode=document.querySelector('.hero .mode'); if(heroMode) heroMode.textContent='현재 실행 클레임 없음';
  const heroP=document.querySelector('.hero p'); if(heroP) heroP.textContent='GitHub 기준 현재 실행 상태는 대기 큐와 분리해 표시합니다. 실제 로컬 프로세스 하트비트가 확인되기 전에는 실행 시간을 임의로 표시하지 않습니다.';
  const overlay=document.querySelector('.overlay'); const close=document.querySelector('.close');
  const dismiss=()=>{if(!overlay)return;overlay.classList.remove('open');document.body.style.overflow='';};
  if(close)close.addEventListener('click',e=>{e.preventDefault();e.stopPropagation();dismiss()},{capture:true});
  if(overlay)overlay.addEventListener('click',e=>{if(e.target===overlay)dismiss()});
  document.addEventListener('keydown',e=>{if(e.key==='Escape')dismiss()});
  window.addEventListener('popstate',()=>dismiss());
  if('serviceWorker' in navigator){window.addEventListener('load',()=>{navigator.serviceWorker.register('./sw.js',{scope:'./'}).catch(()=>{});});}
})();
