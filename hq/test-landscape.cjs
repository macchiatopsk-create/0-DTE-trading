// node hq/test-landscape.cjs — layout math and source contracts, no private data.
'use strict';
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const html=fs.readFileSync(path.join(__dirname,'index.html'),'utf8');
const source=[...html.matchAll(/<script>([\s\S]*?)<\/script>/g)][0][1];
const ctx=vm.createContext({window:{},document:{},location:{hash:'',search:''},URLSearchParams});
vm.runInContext(source.replace(/\ninit\(\);\s*$/,''),ctx);
const api=ctx.window.HQOffice;let count=0;
function test(name,fn){fn();count++;console.log('PASS '+name);}
for(const [w,h,request,rotated,wide] of [[390,844,true,true,true],[360,740,true,true,true],[338,705,true,true,true],[705,338,false,false,true],[844,390,true,false,true],[390,844,false,false,false],[1440,900,false,false,false],[1440,900,true,false,true]]){
 const v=api.layoutMetrics(w,h,request),label=`${w}x${h} requested=${request}`;
 test(label+' rotation',()=>assert.equal(v.rotated,rotated));
 test(label+' wide stage',()=>assert.equal(v.wide,wide));
 test(label+' preserves area',()=>assert.equal(v.width*v.height,w*h));
}
const rect={left:12,top:51,right:348,bottom:781};
test('normal pointer is viewport-local',()=>{const p=api.toLocalPoint(112,151,rect,false);assert.equal(p.x,100);assert.equal(p.y,100);});
test('rotated pointer uses inverse rotation',()=>{const p=api.toLocalPoint(248,151,rect,true);assert.equal(p.x,100);assert.equal(p.y,100);});
test('rotated horizontal gesture maps to local x',()=>{const a=api.toLocalPoint(248,151,rect,true),b=api.toLocalPoint(248,191,rect,true);assert.equal(b.x-a.x,40);assert.equal(b.y-a.y,0);});
test('rotated vertical gesture maps to local y',()=>{const a=api.toLocalPoint(248,151,rect,true),b=api.toLocalPoint(208,151,rect,true);assert.equal(b.x-a.x,0);assert.equal(b.y-a.y,40);});
test('default camera fits rather than crops',()=>assert.match(source,/function startCamera\(\)\{fitOffice\(false\);\}/));
test('logical dimensions do not swap with DOM rotation',()=>assert.match(source,/width:vp\.clientWidth,height:vp\.clientHeight/));
test('wide mode keeps only two visible grid rows',()=>assert.match(html,/#view-root\.wide-layout \.app\{grid-template-rows:48px minmax\(0,1fr\)\}/));
test('side detail stays in virtual height',()=>assert.match(html,/height:calc\(var\(--view-h\) - 48px\)/));
test('no native orientation or fullscreen promise',()=>assert.doesNotMatch(source,/screen\.orientation\.lock|requestFullscreen/));
test('gesture and wheel events use transformed coordinates',()=>{assert.equal((source.match(/pointers\.set\(e.pointerId,viewportPoint\(e\)\)/g)||[]).length,2);assert.match(source,/const p=viewportPoint\(e\);zoomBy/);});
test('toggle retains existing fragment while modifying query',()=>{assert.match(source,/new URL\(location\.href\)/);assert.match(source,/u\.searchParams\.set\('wide','1'\)/);assert.match(source,/history\.replaceState\(null,'',u\)/);});
test('modal logic follows virtual viewport too',()=>assert.match(source,/function isModalLayout\(\)\{return layout\.wide\|\|layout\.width<=1050;\}/));
test('all detail close controls remain at least 44 CSS pixels',()=>assert.match(html,/#view-root \.close\{width:44px\}/));
console.log(`LANDSCAPE: ${count}/${count} PASS`);
