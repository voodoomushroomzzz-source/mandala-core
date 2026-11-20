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
  const TONES = {
    core:{hex:'#56d364',rgb:'86,211,100'},
    hub:{hex:'#a371f7',rgb:'163,113,247'},
    small:{hex:'#7989ef',rgb:'121,137,239'}
  };
  const tone = n => n.id==='core_map' ? TONES.core : n.hub ? TONES.hub : TONES.small;
  function fiberGeometry(id,detail=140) {
    // Stable seeded fibers: no random flicker while nodes move or zoom.
    let seed=2166136261;
    for(const char of id)seed=Math.imul(seed^char.charCodeAt(0),16777619);
    const random=()=>{seed|=0;seed=seed+0x6D2B79F5|0;let t=Math.imul(seed^seed>>>15,1|seed);t^=t+Math.imul(t^t>>>7,61|t);return ((t^t>>>14)>>>0)/4294967296;};
    const phases=[random()*6.28,random()*6.28,random()*6.28];
    const boundary=a=>.91+.035*Math.sin(a*3+phases[0])+.024*Math.sin(a*7+phases[1])+.012*Math.sin(a*13+phases[2]);
    const point=()=>{const a=random()*Math.PI*2,r=Math.sqrt(random())*.94;return{x:Math.cos(a)*r,y:Math.sin(a)*r};};
    const outline=Array.from({length:96},(_,i)=>{const a=i/96*Math.PI*2,r=boundary(a);return{x:Math.cos(a)*r,y:Math.sin(a)*r};});
    const fibers=Array.from({length:detail},()=>{
      const a=random()*Math.PI*2,r=.4+random()*.55,span=.8+random()*3.5;
      const start={x:Math.cos(a)*r,y:Math.sin(a)*r};
      const end={x:Math.cos(a+span)*r,y:Math.sin(a+span)*r};
      return {points:[start,point(),point(),end],light:random(),width:(detail<80 ? .018 : .009)+random()*.01};
    });
    const tips=Array.from({length:24},()=>{
      const a=random()*Math.PI*2,r=boundary(a),out=r+.025+random()*.12;
      return {points:[{x:Math.cos(a)*r*.88,y:Math.sin(a)*r*.88},
        {x:Math.cos(a+.08)*out,y:Math.sin(a+.08)*out},
        {x:Math.cos(a-.09)*out,y:Math.sin(a-.09)*out},
        {x:Math.cos(a+.04)*out,y:Math.sin(a+.04)*out}],light:random(),width:.004};
    });
    return {outline,fibers,tips};
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
  function createPhysics(model,{reducedMotion=false}={}) {
    // Springs preserve the original relative layout and transmit displacement
    // over real links only. Nodes near the grab respond before distant nodes.
    const bodies=new Map(model.nodes.map(n=>[n.id,{
      x:n.x,y:n.y,vx:0,vy:0,mass:1+Math.sqrt(n.degree||0)+(n.hub?1:0)
    }]));
    const pairs=new Map();
    model.edges.forEach(e=>{
      if(e.from===e.to)return;
      const k=key(e.from,e.to);
      if(!pairs.has(k)){
        const a=model.byId.get(e.from),b=model.byId.get(e.to);
        pairs.set(k,{a,b,dx:b.x-a.x,dy:b.y-a.y});
      }
    });
    let active=false,pinned=null,age=0;
    function stop(){active=false;pinned=null;model.nodes.forEach(n=>{const b=bodies.get(n.id);b.vx=0;b.vy=0;});}
    return {
      get active(){return active;},
      pin(id,x,y){
        const n=model.byId.get(id);
        if(!n||!Number.isFinite(x)||!Number.isFinite(y))return;
        n.x=x;n.y=y;pinned=id;active=true;age=0;
        const b=bodies.get(id);b.vx=0;b.vy=0;
      },
      release(){pinned=null;age=0;},
      stop,
      step(dt=1,visible=null){
        if(!active)return false;
        dt=Math.max(.1,Math.min(1.5,Number.isFinite(dt)?dt:1));
        const forces=new Map();
        model.nodes.forEach(n=>{
          const b=bodies.get(n.id);
          forces.set(n.id,{x:(b.x-n.x)*.009,y:(b.y-n.y)*.009});
        });
        pairs.forEach(({a,b,dx,dy})=>{
          if(visible&&(!visible.has(a.id)||!visible.has(b.id)))return;
          const fx=((b.x-a.x)-dx)*.065,fy=((b.y-a.y)-dy)*.065;
          forces.get(a.id).x+=fx;forces.get(a.id).y+=fy;
          forces.get(b.id).x-=fx;forces.get(b.id).y-=fy;
        });
        let motion=0;
        model.nodes.forEach(n=>{
          const b=bodies.get(n.id),f=forces.get(n.id);
          if(n.id===pinned||(visible&&!visible.has(n.id))){b.vx=0;b.vy=0;return;}
          const damping=Math.pow(reducedMotion ? .62 : .86,dt);
          b.vx=(b.vx+f.x/b.mass*dt)*damping;
          b.vy=(b.vy+f.y/b.mass*dt)*damping;
          const speed=Math.hypot(b.vx,b.vy);
          if(speed>16){b.vx*=16/speed;b.vy*=16/speed;}
          n.x+=b.vx*dt;n.y+=b.vy*dt;
          motion=Math.max(motion,Math.hypot(b.vx,b.vy),Math.hypot(f.x,f.y)/b.mass);
        });
        age+=dt;
        if(!pinned&&(motion<.035||age>(reducedMotion?100:600)))stop();
        return active;
      }
    };
  }
  function init(graph) {
    const model=buildModel(graph), canvas=document.getElementById('network'), ctx=canvas.getContext('2d');
    const simulation=createPhysics(model,{reducedMotion:window.matchMedia?.('(prefers-reduced-motion: reduce)').matches||false});
    const panel=document.getElementById('panel'), tooltip=document.getElementById('tooltip');
    const intro=panel.innerHTML, search=document.getElementById('search'), results=document.getElementById('search-results');
    const fiberSprites=new Map();
    function fiberSprite(n,color) {
      const cacheKey=n.id+color;
      if(fiberSprites.has(cacheKey))return fiberSprites.get(cacheKey);
      const sprite=document.createElement('canvas');sprite.width=sprite.height=n.hub?256:128;
      const c=sprite.getContext('2d'),mid=sprite.width/2,unit=sprite.width/2.6;
      const rgb=color.match(/[a-f0-9]{2}/gi).map(v=>parseInt(v,16));
      const shade=(factor,alpha=1)=>`rgba(${rgb.map(v=>Math.min(255,Math.round(v*factor))).join(',')},${alpha})`;
      const geometry=fiberGeometry(n.id,n.hub?190:55);
      c.translate(mid,mid);c.scale(unit,unit);
      const silhouette=()=>{c.beginPath();geometry.outline.forEach((p,i)=>i?c.lineTo(p.x,p.y):c.moveTo(p.x,p.y));c.closePath();};
      const haze=c.createRadialGradient(0,0,.45,0,0,1.25);haze.addColorStop(0,shade(.8,.12));haze.addColorStop(1,shade(.8,0));c.fillStyle=haze;c.fillRect(-1.3,-1.3,2.6,2.6);
      // A dark, diffuse body under the threads; no specular white highlight.
      const body=c.createRadialGradient(-.2,-.25,.05,0,0,1.05);body.addColorStop(0,shade(.95,.96));body.addColorStop(.65,shade(.72,.96));body.addColorStop(1,shade(.38,.9));c.fillStyle=body;silhouette();c.fill();
      c.save();silhouette();c.clip();c.lineCap='round';
      geometry.fibers.forEach(f=>{
        const [a,b,d,e]=f.points;
        c.beginPath();c.moveTo(a.x,a.y);c.bezierCurveTo(b.x,b.y,d.x,d.y,e.x,e.y);
        c.lineWidth=f.width*2.5;c.strokeStyle=shade(.12,.42);c.stroke();
        c.lineWidth=f.width;c.strokeStyle=shade(.95+f.light*.42,.45+f.light*.4);c.stroke();
      });
      c.restore();
      geometry.tips.forEach(f=>{const [a,b,d,e]=f.points;c.beginPath();c.moveTo(a.x,a.y);c.bezierCurveTo(b.x,b.y,d.x,d.y,e.x,e.y);c.lineWidth=f.width;c.strokeStyle=shade(.9,.32);c.stroke();});
      fiberSprites.set(cacheKey,sprite);return sprite;
    }

    let view, width=1,height=1,dpr=1, scale=1,panX=0,panY=0, selected=null, hover=null, bundleSelected=null;
    let bundlePaths=[],nodeHits=[],drag=null,moved=false,frame=0,lastFrame=0;
    const pointers=new Map();let pinch=null;
    document.addEventListener('visibilitychange',()=>{if(document.hidden)simulation.stop();});
    function refresh() {
      const types=new Set([...document.querySelectorAll('#filters input:checked')].map(i=>i.value));
      view=visibleModel(model,types);
      if(selected&&!view.ids.has(selected)){selected=null;panel.innerHTML=intro;panel.className='intro';}
      if(bundleSelected&&!view.bundles.some(b=>b.id===bundleSelected)){bundleSelected=null;panel.innerHTML=intro;panel.className='intro';}
      document.getElementById('stat').textContent=`${view.nodes.length} узлов · ${view.edges.length} связей · ${(graph.analysis||{}).seeds_total||0} семян`;
      requestDraw();
    }
    function requestDraw(){if(!frame)frame=requestAnimationFrame(time=>{
      frame=0;
      const dt=lastFrame?Math.min(1.5,(time-lastFrame)/16.667):1;
      simulation.step(dt,view?.ids);draw();lastFrame=time;
      if(simulation.active)requestDraw();else lastFrame=0;
    });}
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
      const bg=ctx.createRadialGradient(width*.42,height*.4,0,width*.42,height*.4,width*.7);bg.addColorStop(0,'#19213a');bg.addColorStop(1,'#0d1117');ctx.fillStyle=bg;ctx.fillRect(0,0,width,height);
      ctx.translate(panX,panY);ctx.scale(scale,scale);bundlePaths=[];nodeHits=[];
      // Only real graph edges generate branches. Curved routing is visual, not new data.
      view.bundles.forEach(b=>{
        const a=model.byId.get(b.from),z=model.byId.get(b.to);if(!a||!z)return;
        const active=b.id===bundleSelected||hover?.bundle?.id===b.id||b.edges.some(e=>e.from===selected||e.to===selected);
        const alpha=selected&&!active ? b.opacity*.25:b.opacity;
        const c=curve(a,z);
        stroke(c,`rgba(${tone(a).rgb},${alpha*.11})`,b.width*3.2,12);
        for(let i=0;i<b.strands;i++){
          const offset=(i-(b.strands-1)/2)*2.2;
          stroke(curve(a,z,offset),active?'rgba(199,187,255,.94)':`rgba(${i%2?tone(z).rgb:tone(a).rgb},${alpha})`,Math.max(.65,b.width/b.strands),active?8:3);
        }
        if(b.count>1||active){const p=pointOn(c,.53);const r=active?4:2.4;const g=ctx.createRadialGradient(p.x,p.y,0,p.x,p.y,r*6);g.addColorStop(0,'#d4d6ff');g.addColorStop(.2,'#a371f770');g.addColorStop(1,'#a371f700');ctx.fillStyle=g;ctx.beginPath();ctx.arc(p.x,p.y,r*6,0,Math.PI*2);ctx.fill();}
        bundlePaths.push({bundle:b,points:c});
      });
      view.edges.forEach((e,i)=>{
        const a=model.byId.get(e.from),b=model.byId.get(e.to),same=a.group===b.group;
        const active=e.from===selected||e.to===selected;
        const bad=['broken_link','unregistered'].includes(e.type);
        const opacity=selected&&!active ? .07 : same ? .42 : .19;
        const color=bad?'rgba(230,148,110,.8)':active?'rgba(184,172,255,.93)':`rgba(${tone(a).rgb},${opacity})`;
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
        const color=bad?'#ffa657':tone(n).hex;
        const r=(n.hub?Math.max(n.radius,13/scale):Math.max(n.radius,2.5/scale))*(active?1.15:1);ctx.globalAlpha=alpha;
        const sprite=fiberSprite(n,color);
        ctx.drawImage(sprite,n.x-r*1.3,n.y-r*1.3,r*2.6,r*2.6);
        if(active){ctx.strokeStyle='#c4b5fd';ctx.lineWidth=1.3/scale;ctx.beginPath();ctx.arc(n.x,n.y,r+5/scale,0,Math.PI*2);ctx.stroke();}
        const showLabel=n.hub||active||scale>1.1;
        if(showLabel){const text=label(n);const size=n.hub?14/scale:12/scale;ctx.font=`${n.hub?'500':'400'} ${size}px system-ui`;ctx.textBaseline='middle';ctx.fillStyle=n.hub?'#dce3f1':'#bac9dc';ctx.shadowColor='#0d1117';ctx.shadowBlur=7;const clipped=text.length>38&&!n.hub?text.slice(0,35)+'…':text;const tx=n.x+r+9/scale;ctx.fillText(clipped,tx,n.y);ctx.shadowBlur=0;if(n.hub)nodeHits.push({node:n,x:tx,y:n.y,w:ctx.measureText(clipped).width,h:size});}
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
    canvas.addEventListener('pointerdown',e=>{const p=local(e);pointers.set(e.pointerId,p);canvas.setPointerCapture(e.pointerId);moved=false;if(pointers.size===1)drag={...p,panX,panY,node:nodeAt(p)?.id,lastX:p.x,lastY:p.y};if(pointers.size===2){const [a,b]=[...pointers.values()];pinch={distance:Math.hypot(a.x-b.x,a.y-b.y)};drag=null;simulation.release();moved=true;}canvas.classList.add('dragging');});
    canvas.addEventListener('pointermove',e=>{
      const p=local(e);
      if(pointers.has(e.pointerId)){pointers.set(e.pointerId,p);if(pointers.size===2){const [a,b]=[...pointers.values()],d=Math.hypot(a.x-b.x,a.y-b.y);if(pinch?.distance)zoom(d/pinch.distance,{x:(a.x+b.x)/2,y:(a.y+b.y)/2});pinch={distance:d};moved=true;return;}if(drag){const dx=p.x-drag.x,dy=p.y-drag.y;if(Math.hypot(dx,dy)>4)moved=true;
        if(moved){if(drag.node){const grabbed=model.byId.get(drag.node);simulation.pin(drag.node,grabbed.x+(p.x-drag.lastX)/scale,grabbed.y+(p.y-drag.lastY)/scale);drag.lastX=p.x;drag.lastY=p.y;}
        else{panX=drag.panX+dx;panY=drag.panY+dy;}tooltip.hidden=true;requestDraw();}}return;}
      const node=nodeAt(p),bundle=node?null:bundleAt(p);hover={node,bundle};canvas.style.cursor=node||bundle?'pointer':'grab';tooltip.hidden=!node&&!bundle;
      if(!tooltip.hidden){tooltip.textContent=node?`${label(node)} · ${node.degree} соседей`:`${label(model.byId.get(bundle.from))} ↔ ${label(model.byId.get(bundle.to))} · ${bundle.count} связей`;tooltip.style.left=Math.max(8,Math.min(width-315,p.x+15))+'px';tooltip.style.top=Math.max(8,Math.min(height-50,p.y+16))+'px';}requestDraw();
    });
    function release(e){simulation.release();requestDraw();const p=local(e),wasPinching=!!pinch;pointers.delete(e.pointerId);if(!moved&&!wasPinching){const node=nodeAt(p);if(node)selectNode(node);else{const bundle=bundleAt(p);if(bundle)selectBundle(bundle);else resetPanel();}}if(pointers.size===0){drag=null;pinch=null;canvas.classList.remove('dragging');}else{const p=[...pointers.values()][0];drag={...p,panX,panY};pinch=null;moved=true;}}
    canvas.addEventListener('pointerup',release);canvas.addEventListener('pointercancel',()=>{pointers.clear();drag=null;pinch=null;simulation.release();requestDraw();canvas.classList.remove('dragging');});
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
  return {buildModel,visibleModel,strength,tone,fiberGeometry,createPhysics,init};
})();
if(typeof module!=='undefined'&&module.exports)module.exports=NeuralMap;
if(typeof document!=='undefined')window.mandalaMap=NeuralMap.init(GRAPH);
