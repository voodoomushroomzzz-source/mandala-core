/* The rendering model never adds semantic nodes or edges to the source graph. */
const NeuralMap = (() => {
  const LABELS = {core_map:'Карта ядра',philosophy:'Философия',works:'Работы',fruits:'Продукты',
    knowledge:'Знания',akasha:'Память',personal:'Личное',protocols:'Протоколы',
    instructions:'Инструкции',boot_online:'Вход',seeds:'Семена',humor:'Юмор',sym:'Рост · SYM',
    sessions:'Преемственность',rose_world:'Роза Мира',directives:'Директивы',registry:'Реестр'};
  const TYPES = {honeycomb:'Сота',work:'Работа',fruit:'Продукт',knowledge:'Знание',missing:'Отсутствует',honeycomb_unregistered:'Не зарегистрировано'};
  const ANCHORS = {core_map:[0,0],works:[-510,-100],knowledge:[0,470],fruits:[520,-110],
    philosophy:[-650,-520],akasha:[650,420],personal:[-650,470],protocols:[-180,-540],
    instructions:[250,-560],boot_online:[-1000,-180],seeds:[-1050,250],humor:[980,-480],
    sym:[1060,-60],sessions:[1080,370],rose_world:[-140,840],directives:[470,800],registry:[-650,850]};
  const isHub = n => n.type === 'honeycomb' || n.type === 'honeycomb_unregistered';
  const label = n => LABELS[n.id] || n.name || n.id.replace(/^W-[TR]-\d+-/,'').replace(/__/g,' · ');
  const key = (a,b) => JSON.stringify([a,b].sort());
  function strength(count) {
    // A bounded logarithmic mapping preserves sparse paths and nucleus hierarchy.
    const t = Math.min(1, Math.log1p(Math.max(0,count-1))/Math.log(33));
    return {width:1.15 + t*7.3, opacity:.3 + t*.57, strands:Math.min(7,Math.max(1,Math.ceil(Math.sqrt(count))))};
  }
  function buildModel(graph) {
    const nodes = graph.nodes.map(n => ({...n, hub:isHub(n), group:n.id, neighbors:new Set(), degree:0}));
    const byId = new Map(nodes.map(n=>[n.id,n]));
    const seen = new Set();
    const edges = graph.edges.filter(e=>{
      const signature=JSON.stringify([e.from,e.to,e.type]);
      if(!byId.has(e.from)||!byId.has(e.to)||seen.has(signature)) return false;
      seen.add(signature); return true;
    }).map(e=>({...e}));
    edges.forEach(e=>{if(e.from!==e.to){byId.get(e.from).neighbors.add(e.to);byId.get(e.to).neighbors.add(e.from);}});
    nodes.forEach(n=>{
      n.degree=n.neighbors.size;
      if(!n.hub) {
        const owner=edges.find(e=>e.to===n.id&&['contains','children'].includes(e.type)&&byId.get(e.from)?.hub);
        const preferred={work:'works',fruit:'fruits',knowledge:'knowledge'}[n.type];
        n.group=owner?.from || (byId.has(preferred)?preferred:n.id);
      }
      n.radius=n.hub ? 12+Math.min(10,Math.log1p(n.degree)*2.5) : 3.8+Math.min(5.2,Math.log1p(n.degree)*1.5);
    });
    const groups=new Map();
    nodes.forEach(n=>{if(!groups.has(n.group))groups.set(n.group,[]);groups.get(n.group).push(n);});
    let extra=0;
    groups.forEach((members,id)=>{
      const pos=ANCHORS[id] || [Math.cos(extra*2.4)*1250,Math.sin(extra++*2.4)*950];
      const satellites=members.filter(n=>n.id!==id).sort((a,b)=>a.id.localeCompare(b.id));
      const owner=byId.get(id);
      if(owner){owner.x=pos[0];owner.y=pos[1];}
      satellites.forEach((n,i)=>{
        const angle=i*2.399963229728653;
        const r=72+Math.sqrt((i+1)/Math.max(1,satellites.length))*155;
        n.x=pos[0]+Math.cos(angle)*r; n.y=pos[1]+Math.sin(angle)*r*.82;
      });
    });
    return {nodes,byId,edges,groups};
  }
  function visibleModel(model,types) {
    const nodes=model.nodes.filter(n=>types.has(n.type) || (n.type==='honeycomb_unregistered'&&types.has('missing')));
    const ids=new Set(nodes.map(n=>n.id));
    const edges=model.edges.filter(e=>ids.has(e.from)&&ids.has(e.to));
    const bundles=new Map();
    edges.forEach(e=>{
      const a=model.byId.get(e.from), b=model.byId.get(e.to);
      if(a.group===b.group) return;
      const k=key(a.group,b.group);
      if(!bundles.has(k))bundles.set(k,{id:k,from:a.group,to:b.group,edges:[],count:0});
      const bundle=bundles.get(k);bundle.edges.push(e);bundle.count++;
    });
    bundles.forEach(b=>Object.assign(b,strength(b.count)));
    return {nodes,edges,bundles:[...bundles.values()],ids};
  }
  function init(graph) {
    const model=buildModel(graph), canvas=document.getElementById('network'), ctx=canvas.getContext('2d');
    const panel=document.getElementById('panel'), tooltip=document.getElementById('tooltip');
    const intro=panel.innerHTML, search=document.getElementById('search'), results=document.getElementById('search-results');
    let view, width=1,height=1,dpr=1, scale=1,panX=0,panY=0, selected=null, hover=null, bundleSelected=null;
    let bundlePaths=[],nodeHits=[],drag=null,moved=false,frame=0;
    const pointers=new Map();let pinch=null;
    function refresh() {
      const types=new Set([...document.querySelectorAll('#filters input:checked')].map(i=>i.value));
      view=visibleModel(model,types);
      if(selected&&!view.ids.has(selected)){selected=null;panel.innerHTML=intro;panel.className='intro';}
      if(bundleSelected&&!view.bundles.some(b=>b.id===bundleSelected)){bundleSelected=null;panel.innerHTML=intro;panel.className='intro';}
      document.getElementById('stat').textContent=`${view.nodes.length} узлов · ${view.edges.length} связей · ${(graph.analysis||{}).seeds_total||0} семян`;
      requestDraw();
    }
    function requestDraw(){if(!frame)frame=requestAnimationFrame(()=>{frame=0;draw();});}
    function fit() {
      const ns=view.nodes;if(!ns.length)return;
      const minX=Math.min(...ns.map(n=>n.x))-100,maxX=Math.max(...ns.map(n=>n.x))+180;
      const minY=Math.min(...ns.map(n=>n.y))-100,maxY=Math.max(...ns.map(n=>n.y))+100;
      const usable=width>760?Math.max(width-310,width*.7):width;
      scale=Math.max(.08,Math.min(1.6,(usable-40)/(maxX-minX),(height-150)/(maxY-minY)));
      panX=usable/2-(minX+maxX)/2*scale;panY=(height-50)/2-(minY+maxY)/2*scale+35;requestDraw();
    }
    function resize(){const r=canvas.getBoundingClientRect();width=r.width;height=r.height;dpr=Math.min(2,window.devicePixelRatio||1);canvas.width=Math.round(width*dpr);canvas.height=Math.round(height*dpr);fit();if(selected)selectNode(model.byId.get(selected),true);}
    function world(p){return{x:(p.x-panX)/scale,y:(p.y-panY)/scale};}
    function local(e){const r=canvas.getBoundingClientRect();return{x:e.clientX-r.left,y:e.clientY-r.top};}
    function zoom(factor,p={x:width/2,y:height/2}){const w=world(p);scale=Math.max(.08,Math.min(3.8,scale*factor));panX=p.x-w.x*scale;panY=p.y-w.y*scale;requestDraw();}
    function curve(a,b,bend=0){const dx=b.x-a.x,dy=b.y-a.y;return[a,{x:a.x+dx*.33-dy*.13+bend,y:a.y+dy*.33+dx*.13+bend},{x:a.x+dx*.67-dy*.13+bend,y:a.y+dy*.67+dx*.13+bend},b];}
    function path(points){ctx.beginPath();ctx.moveTo(points[0].x,points[0].y);ctx.bezierCurveTo(points[1].x,points[1].y,points[2].x,points[2].y,points[3].x,points[3].y);}
    function pointOn(points,t){const s=1-t;return{x:s*s*s*points[0].x+3*s*s*t*points[1].x+3*s*t*t*points[2].x+t*t*t*points[3].x,y:s*s*s*points[0].y+3*s*s*t*points[1].y+3*s*t*t*points[2].y+t*t*t*points[3].y};}
    function relevant(n){return !selected||n.id===selected||model.byId.get(selected)?.neighbors.has(n.id);}
    function stroke(points,color,lineWidth,glow=0){ctx.strokeStyle=color;ctx.lineWidth=lineWidth;ctx.shadowColor=color;ctx.shadowBlur=glow;path(points);ctx.stroke();ctx.shadowBlur=0;}
    function draw() {
      ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,width,height);
      const bg=ctx.createRadialGradient(width*.42,height*.4,0,width*.42,height*.4,width*.7);bg.addColorStop(0,'#172519');bg.addColorStop(1,'#080f0b');ctx.fillStyle=bg;ctx.fillRect(0,0,width,height);
      ctx.translate(panX,panY);ctx.scale(scale,scale);bundlePaths=[];nodeHits=[];
      // Only real graph edges generate branches. Curved routing is visual, not new data.
      view.bundles.forEach(b=>{
        const a=model.byId.get(b.from),z=model.byId.get(b.to);if(!a||!z)return;
        const active=b.id===bundleSelected||hover?.bundle?.id===b.id||b.edges.some(e=>e.from===selected||e.to===selected);
        const alpha=selected&&!active ? b.opacity*.25:b.opacity;
        const c=curve(a,z);
        stroke(c,`rgba(193,202,126,${alpha*.11})`,b.width*3.2,12);
        for(let i=0;i<b.strands;i++){
          const offset=(i-(b.strands-1)/2)*2.2;
          stroke(curve(a,z,offset),active?'rgba(244,218,147,.94)':`rgba(193,209,140,${alpha})`,Math.max(.65,b.width/b.strands),active?8:3);
        }
        if(b.count>1||active){const p=pointOn(c,.53);const r=active?4:2.4;const g=ctx.createRadialGradient(p.x,p.y,0,p.x,p.y,r*6);g.addColorStop(0,'#f4d793');g.addColorStop(.2,'#c6ad6870');g.addColorStop(1,'#c6ad6800');ctx.fillStyle=g;ctx.beginPath();ctx.arc(p.x,p.y,r*6,0,Math.PI*2);ctx.fill();}
        bundlePaths.push({bundle:b,points:c});
      });
      view.edges.forEach((e,i)=>{
        const a=model.byId.get(e.from),b=model.byId.get(e.to),same=a.group===b.group;
        const active=e.from===selected||e.to===selected;
        const bad=['broken_link','unregistered'].includes(e.type);
        const opacity=selected&&!active ? .07 : same ? .42 : .19;
        const color=bad?'rgba(230,148,110,.8)':active?'rgba(242,218,156,.93)':`rgba(171,202,139,${opacity})`;
        ctx.setLineDash(bad?[5,5]:[]);
        if(same)stroke(curve(a,b,(i%5-2)*3),color,active?1.9:.85,active?5:0);
        else{
          // Individual axons meet the actual group's bundle; no extra nodes.
          const ga=model.byId.get(a.group),gb=model.byId.get(b.group);
          const points=curve(ga,gb);const p=pointOn(points,.28),q=pointOn(points,.72);
          if(a.id!==ga.id)stroke(curve(a,p),color,active?1.7:.65);
          if(b.id!==gb.id)stroke(curve(q,b),color,active?1.7:.65);
        }
        ctx.setLineDash([]);
      });
      view.nodes.forEach(n=>{
        const active=n.id===selected||n.id===hover?.node?.id, bad=['missing','honeycomb_unregistered'].includes(n.type);
        const alpha=relevant(n)?1:.35;
        const color=bad?'#e6a578':n.hub?'#f3dfa0':n.type==='fruit'?'#e4c985':'#c1daa0';
        const r=(n.hub?Math.max(n.radius,10/scale):Math.max(n.radius,2.5/scale))*(active?1.15:1);ctx.globalAlpha=alpha;
        const glow=ctx.createRadialGradient(n.x,n.y,0,n.x,n.y,r*4.5);glow.addColorStop(0,n.hub?'#d8c17c55':'#b8d89333');glow.addColorStop(1,'#a5c37d00');ctx.fillStyle=glow;ctx.beginPath();ctx.arc(n.x,n.y,r*4.5,0,Math.PI*2);ctx.fill();
        ctx.shadowColor=color;ctx.shadowBlur=n.hub?18:active?14:5;
        const core=ctx.createRadialGradient(n.x-r*.3,n.y-r*.3,0,n.x,n.y,r);core.addColorStop(0,'#ffffe1');core.addColorStop(1,color);ctx.fillStyle=core;ctx.beginPath();ctx.arc(n.x,n.y,r,0,Math.PI*2);ctx.fill();ctx.shadowBlur=0;
        if(active){ctx.strokeStyle='#f7e8bb';ctx.lineWidth=1.3/scale;ctx.beginPath();ctx.arc(n.x,n.y,r+5/scale,0,Math.PI*2);ctx.stroke();}
        const showLabel=n.hub||active||scale>1.1;
        if(showLabel){const text=label(n);const size=n.hub?14/scale:12/scale;ctx.font=`${n.hub?'500':'400'} ${size}px system-ui`;ctx.textBaseline='middle';ctx.fillStyle=n.hub?'#edf0ce':'#cfdbb8';ctx.shadowColor='#080f0b';ctx.shadowBlur=7;const clipped=text.length>38&&!n.hub?text.slice(0,35)+'…':text;const tx=n.x+r+9/scale;ctx.fillText(clipped,tx,n.y);ctx.shadowBlur=0;if(n.hub)nodeHits.push({node:n,x:tx,y:n.y,w:ctx.measureText(clipped).width,h:size});}
        nodeHits.push({node:n,x:n.x-r-7/scale,y:n.y,w:(r+7/scale)*2,h:(r+7/scale)*2,circle:true});ctx.globalAlpha=1;
      });
    }
    function nodeAt(p){const w=world(p);return [...nodeHits].reverse().find(h=>h.circle?Math.hypot(w.x-h.node.x,w.y-h.node.y)<h.node.radius+9/scale:w.x>=h.x&&w.x<=h.x+h.w&&Math.abs(w.y-h.y)<h.h)?.node;}
    function bundleAt(p){const w=world(p);let found=null,best=12/scale;bundlePaths.forEach(b=>{for(let i=1;i<40;i++){const q=pointOn(b.points,i/40),d=Math.hypot(q.x-w.x,q.y-w.y);if(d<best){best=d;found=b.bundle;}}});return found;}
    function el(tag,text,className){const e=document.createElement(tag);if(text!==undefined)e.textContent=text;if(className)e.className=className;return e;}
    function resetPanel(){selected=null;bundleSelected=null;panel.innerHTML=intro;panel.className='intro';requestDraw();}
    function selectNode(n,focus=false){
      selected=n.id;bundleSelected=null;panel.className='';panel.replaceChildren(el('div',TYPES[n.type]||n.type,'type'),el('h3',label(n)),el('p',n.description||'Описание доступно в исходном файле.'),el('div',String(n.degree),'metric'),el('p','Связанных соседей · без учёта приоритета'));
      for(const [k,title] of [['status','Статус'],['deadline','Срок'],['progress','Прогресс'],['version','Версия']])if(n[k]!==undefined&&n[k]!==null)panel.append(el('p',`${title}: ${n[k]}`));
      const detail=el('div',undefined,'details');detail.append(el('p',n.id,'path'));
      if(n.path&&!n.path.split('/').includes('..')&&!/^[a-z]+:/i.test(n.path)){const a=el('a','Открыть исходник ↗');a.href='https://github.com/voodoomushroomzzz-source/mandala-core/blob/main/'+n.path.split('/').map(encodeURIComponent).join('/');a.target='_blank';a.rel='noopener noreferrer';detail.append(a);}
      const close=el('button','Снять выделение');close.onclick=resetPanel;detail.append(close);panel.append(detail);
      if(focus){scale=Math.max(scale,.9);panX=(width>760?(width-300)/2:width/2)-n.x*scale;panY=height*.42-n.y*scale;}
      requestDraw();
    }
    function selectBundle(b){
      selected=null;bundleSelected=b.id;panel.className='';panel.replaceChildren(el('div','Пучок связей','type'),el('h3',`${label(model.byId.get(b.from))} ↔ ${label(model.byId.get(b.to))}`),el('div',String(b.count),'metric'),el('p','Реальных связей между группами. Толщина и яркость растут плавно и ограничены.'));
      const list=el('div',undefined,'details');b.edges.forEach(e=>list.append(el('p',`${label(model.byId.get(e.from))} → ${label(model.byId.get(e.to))} · ${e.type}`)));panel.append(list);requestDraw();
    }
    canvas.addEventListener('pointerdown',e=>{const p=local(e);pointers.set(e.pointerId,p);canvas.setPointerCapture(e.pointerId);moved=false;if(pointers.size===1)drag={...p,panX,panY};if(pointers.size===2){const [a,b]=[...pointers.values()];pinch={distance:Math.hypot(a.x-b.x,a.y-b.y)};drag=null;moved=true;}canvas.classList.add('dragging');});
    canvas.addEventListener('pointermove',e=>{
      const p=local(e);
      if(pointers.has(e.pointerId)){pointers.set(e.pointerId,p);if(pointers.size===2){const [a,b]=[...pointers.values()],d=Math.hypot(a.x-b.x,a.y-b.y);if(pinch?.distance)zoom(d/pinch.distance,{x:(a.x+b.x)/2,y:(a.y+b.y)/2});pinch={distance:d};moved=true;return;}if(drag){const dx=p.x-drag.x,dy=p.y-drag.y;if(Math.hypot(dx,dy)>4)moved=true;panX=drag.panX+dx;panY=drag.panY+dy;requestDraw();}return;}
      const node=nodeAt(p),bundle=node?null:bundleAt(p);hover={node,bundle};canvas.style.cursor=node||bundle?'pointer':'grab';tooltip.hidden=!node&&!bundle;
      if(!tooltip.hidden){tooltip.textContent=node?`${label(node)} · ${node.degree} соседей`:`${label(model.byId.get(bundle.from))} ↔ ${label(model.byId.get(bundle.to))} · ${bundle.count} связей`;tooltip.style.left=Math.max(8,Math.min(width-315,p.x+15))+'px';tooltip.style.top=Math.max(8,Math.min(height-50,p.y+16))+'px';}requestDraw();
    });
    function release(e){const p=local(e),wasPinching=!!pinch;pointers.delete(e.pointerId);if(!moved&&!wasPinching){const node=nodeAt(p);if(node)selectNode(node);else{const bundle=bundleAt(p);if(bundle)selectBundle(bundle);else resetPanel();}}if(pointers.size===0){drag=null;pinch=null;canvas.classList.remove('dragging');}else{const p=[...pointers.values()][0];drag={...p,panX,panY};pinch=null;moved=true;}}
    canvas.addEventListener('pointerup',release);canvas.addEventListener('pointercancel',()=>{pointers.clear();drag=null;pinch=null;canvas.classList.remove('dragging');});
    canvas.addEventListener('pointerleave',()=>{tooltip.hidden=true;hover=null;requestDraw();});
    canvas.addEventListener('wheel',e=>{e.preventDefault();zoom(Math.exp(-e.deltaY*.001),local(e));},{passive:false});
    canvas.addEventListener('keydown',e=>{if(e.key==='Escape')resetPanel();else if(e.key==='+'||e.key==='=')zoom(1.2);else if(e.key==='-')zoom(1/1.2);else if(e.key==='0')fit();else if(['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(e.key)){e.preventDefault();panX+=e.key==='ArrowLeft'?40:e.key==='ArrowRight'?-40:0;panY+=e.key==='ArrowUp'?40:e.key==='ArrowDown'?-40:0;requestDraw();}});
    document.getElementById('zoom-in').onclick=()=>zoom(1.25);document.getElementById('zoom-out').onclick=()=>zoom(.8);document.getElementById('fit').onclick=fit;
    document.querySelectorAll('#filters input').forEach(i=>i.addEventListener('change',()=>{refresh();search.dispatchEvent(new Event('input'));}));
    search.addEventListener('input',()=>{results.replaceChildren();const q=search.value.trim().toLocaleLowerCase('ru');if(!q)return;const found=view.nodes.filter(n=>`${label(n)} ${n.id} ${n.description||''}`.toLocaleLowerCase('ru').includes(q)).slice(0,8);if(!found.length)results.append(el('p','Узлы не найдены среди выбранных типов.'));found.forEach(n=>{const b=el('button',label(n));b.onclick=()=>{selectNode(n,true);results.replaceChildren();search.value=label(n);};results.append(b);});});
    search.addEventListener('keydown',e=>{if(e.key==='Enter')results.querySelector('button')?.click();if(e.key==='Escape'){results.replaceChildren();search.value='';}});
    const a=graph.analysis||{},warnings=[];if(a.broken_refs?.length)warnings.push(`Битые ссылки: ${a.broken_refs.length}`);if(a.unregistered_honeycombs?.length)warnings.push(`Незарегистрированные соты: ${a.unregistered_honeycombs.length}`);if(a.missing_honeycombs?.length)warnings.push(`Отсутствующие соты: ${a.missing_honeycombs.length}`);if(a.islands?.length)warnings.push(`Отдельные группы: ${a.islands.length}`);if(a.id_format_mismatches?.length)warnings.push(`Формат ID: ${a.id_format_mismatches.length}`);document.getElementById('diagnostics').textContent=warnings.join(' · ');
    refresh();new ResizeObserver(resize).observe(canvas);resize();
    const query=new URLSearchParams(location.search).get('node');if(model.byId.has(query))selectNode(model.byId.get(query),true);
    // Public, read-only inspection surface for integration tests and diagnostics.
    return {model,getVisible:()=>view,selectNode:id=>{const n=model.byId.get(id);if(n&&view.ids.has(id))selectNode(n,true);},fit};
  }
  return {buildModel,visibleModel,strength,init};
})();
if(typeof module!=='undefined'&&module.exports)module.exports=NeuralMap;
if(typeof document!=='undefined')window.mandalaMap=NeuralMap.init(GRAPH);
