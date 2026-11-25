'use strict';
const $=(s,r=document)=>r.querySelector(s);
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function h(tag,attrs={},...kids){const e=document.createElement(tag);for(const[k,v]of Object.entries(attrs||{})){if(v==null||v===false)continue;if(k==='class')e.className=v;else if(k.startsWith('on'))e.addEventListener(k.slice(2),v);else if(k==='html')e.innerHTML=v;else if(k==='style')e.setAttribute('style',v);else e.setAttribute(k,v===true?'':v)}for(const c of kids.flat()){if(c==null||c===false)continue;e.append(c.nodeType?c:document.createTextNode(c))}return e}
const css=v=>getComputedStyle(document.documentElement).getPropertyValue(v).trim();
const fmt=(n,d)=>n==null?'':Number(n).toLocaleString('en-US',d!=null?{maximumFractionDigits:d}:{maximumSignificantDigits:4});
const S={meta:null,filters:{},page:'overview',view:{},charts:[],src:'project'};
const lt=()=>'<'+(S.meta?.privacy?.k??5);
const count=n=>n==null?lt():Number(n).toLocaleString('en-US');
const palette=()=>[1,2,3,4,5,6,7,8].map(i=>css('--s'+i));
const SLIDE=['#3987e5','#d95926','#199e70','#c98500','#d55181','#2fa52f','#9085e9','#e66767'];

async function api(path,params={}){
  const u=new URLSearchParams();for(const[k,v]of Object.entries(params))if(v!=null&&v!==''&&!k.startsWith('__'))u.append(k,v);
  if(S.src==='mine'&&!params.__project)u.append('src','mine');
  const only=params.__only;
  if(!params.__nofilter){const f={...S.filters,...(only||{})};for(const[k,vals]of Object.entries(f))for(const v of[].concat(vals))u.append('f.'+k,v)}
  const r=await fetch(path+'?'+u);
  if(r.status===401){location.href='/login';throw new Error('401')}
  const j=await r.json().catch(()=>({}));
  if(r.status===409&&j.code==='mine_missing'&&S.myFile&&!params.__retry){
    // The server copy that answered does not hold the file: repeat the request with the file attached.
    if(!S.myPacked)S.myPacked=await packFile(S.myFile);
    u.set('carry',S.myPacked.name);const r2=await fetch(path+'?'+u,{method:'POST',body:S.myPacked.blob});const j2=await r2.json().catch(()=>({}));
    if(!r2.ok){const e=new Error(j2.detail||'The request could not be completed.');e.code=j2.code;e.status=r2.status;throw e}
    return j2}
  if(!r.ok){const e=new Error(j.detail||'The request could not be completed.');e.code=j.code;e.status=r.status;throw e}
  return j;
}
/* Own file: kept in this tab, compressed and sent again whenever the server no longer holds it. */
async function packFile(f){
  if(!('CompressionStream' in window))return{blob:f,name:f.name};
  const b=await new Response(f.stream().pipeThrough(new CompressionStream('gzip'))).blob();return{blob:b,name:f.name+'.gz'}}
async function sendMine(f){
  const p=await packFile(f);const max=S.meta?.my_max_send;
  if(max&&p.blob.size>max)throw new Error(`This file is too large to send here: ${(p.blob.size/1e6).toFixed(1)} MB after compression, and the limit is ${(max/1e6).toFixed(1)} MB. Try a smaller extract of the file.`);
  const fd=new FormData();fd.append('file',p.blob,p.name);
  const r=await fetch('/api/mydata',{method:'POST',body:fd});const j=await r.json().catch(()=>({}));
  if(!r.ok)throw new Error(j.detail||'The upload did not work.');
  for(let i=0;i<120&&j.status!=='ready';i++){const m=await fetch('/api/meta?src=mine').then(x=>x.json()).catch(()=>({}));if(['ready','mapping','error'].includes(m.status)){if(m.status==='error')throw new Error(m.error||'The file could not be used.');break}await new Promise(z=>setTimeout(z,1500))}
  S.myFile=f;S.myPacked=p}
function disposeCharts(){S.charts.forEach(c=>c.dispose());S.charts=[]}
function chart(el,opt){const c=echarts.init(el,null,{renderer:'canvas'});c.setOption(Object.assign({animation:false,textStyle:{fontFamily:'Instrument Sans,system-ui',color:css('--ink-2')}},opt));S.charts.push(c);return c}
window.addEventListener('resize',()=>S.charts.forEach(c=>c.resize()));
const tt=()=>({backgroundColor:css('--surface'),borderColor:css('--line'),textStyle:{color:css('--ink'),fontSize:13},extraCssText:'border-radius:6px;box-shadow:0 6px 20px rgb(0 20 25/.18)',confine:true});
const axisStyle=()=>({axisLine:{lineStyle:{color:css('--line')}},axisTick:{show:false},axisLabel:{color:css('--ink-2'),fontSize:12},splitLine:{lineStyle:{color:css('--line'),opacity:.55}}});
const seq=()=>[css('--seq-0'),css('--seq-1'),css('--seq-2'),css('--seq-3'),css('--seq-4')];

const PAGES=[['overview','Overview'],['profile','Drug profile'],['dictionary','Data dictionary'],['coverage','Coverage'],['distribution','Distribution studio'],['clusters','Clusters'],['compare','Compare'],['relationships','Relationships'],['samples','Sample records']];
const HIDDEN_PAGES=['mydata'];

function renderNav(){const n=$('#nav');n.replaceChildren(...PAGES.filter(([k])=>k!=='samples'||S.meta.sample_enabled).map(([k,l])=>h('a',{href:'#'+k,'aria-current':S.page===k?'page':null,class:k==='mydata'?'navsep':null},k==='profile'&&S.meta.n&&!S.meta.domain?'Group profile':l)));renderSource()}
function renderSource(){const box=$('#srcsw');if(!box)return;const mine=S.meta.mine||S.myFile;
  box.replaceChildren(S.src==='mine'?h('button',{class:'link',onclick:()=>switchSource('project')},'Back to project data'):h('a',{class:'link',href:'#mydata'},mine?'My own file':'Explore your own file'))}
async function switchSource(k){if(k==='mine'&&!S.meta.mine&&!S.myFile){location.hash='mydata';return}
  S.src=k;S.filters={};S.view={};S.meta=await api('/api/meta',{__nofilter:1});$('#dsname').textContent=k==='mine'?'Your own file':(S.meta.name||'');renderFilters();if(S.meta.status!=='ready')poll();
  if(k==='mine'&&location.hash==='#mydata')location.hash='overview';else route()}
function renderFilters(){
  const box=$('#filters');box.replaceChildren(S.meta.dims?.length?h('span',{},'Filter'):null);
  (S.meta.dims||[]).forEach(d=>{
    const sel=S.filters[d.key]||[];
    const det=h('details',{class:'fil'+(sel.length?' on':'')},h('summary',{},d.label+(sel.length?` (${sel.length})`:'')));
    det.append(h('div',{class:'pop'},d.options.filter(o=>o.value!=='Small groups').map(o=>{
      const cb=h('input',{type:'checkbox',checked:sel.includes(o.value)||null,onchange:()=>{const cur=new Set(S.filters[d.key]||[]);cb.checked?cur.add(o.value):cur.delete(o.value);if(cur.size)S.filters[d.key]=[...cur];else delete S.filters[d.key];renderFilters();$(`details[data-k="${d.key}"]`)?.setAttribute('open','');route(true)}});
      return h('label',{},cb,o.value,h('em',{},count(o.n)));
    })));
    det.dataset.k=d.key;box.append(det);
  });
  if(Object.keys(S.filters).length)box.append(h('button',{class:'link',onclick:()=>{S.filters={};renderFilters();route(true)}},'Clear filters'));
  const st=h('span',{class:'status',id:'fstatus'});box.append(st);
  document.addEventListener('click',closePops,{once:true});
}
function closePops(ev){document.querySelectorAll('details.fil[open]').forEach(d=>{if(!d.contains(ev.target))d.removeAttribute('open')});document.addEventListener('click',closePops,{once:true})}

const barList=(rows,opts={})=>{const max=opts.pct?100:Math.max(...rows.map(r=>r.n||0),1);return h('div',{class:'bars'+(opts.wide?' wide':'')},rows.map(r=>h('div',{class:'bar'},h('div',{class:'nm',title:r.title||r.value},opts.click&&!r.small?h('button',{class:'textlink',onclick:()=>opts.click(r.value)},r.value):r.value),h('div',{class:'tr'},h('div',{class:'fl',style:`width:${100*(r.n||0)/max}%;${r.small?'opacity:.45':''}`})),h('div',{class:'v'},opts.pct?`${fmt(r.n,0)}%`:count(r.n)))))};
function filtMsg(e,el){el.replaceChildren(h('div',{class:'notice',role:'status'},e.message||'This view could not be loaded.'))}
async function guarded(el,fn){try{await fn()}catch(e){if(e.message==='401')return;filtMsg(e,el)}}

function head(t,lead){return h('div',{class:'head'},h('h1',{},t),lead&&h('p',{class:'lead'},lead))}

/* ---------- Hexagon map ---------- */
function hexMap(el,data,{labels=true,legend=true}={}){
  el.replaceChildren();const cv=h('canvas',{role:'img','aria-label':'Two-dimensional density map of records by content similarity'});el.append(cv);
  const tip=h('div',{class:'maptip'});el.append(tip);
  const nm=data.names||[];const colorOf=n=>{if(data.color==='density')return null;if(n==='Other'||n==null)return'#6f8483';const i=nm.indexOf(n);return SLIDE[i%8]||'#6f8483'};
  let hi=null,geo=null;
  function draw(){
    const W=el.clientWidth,H=el.clientHeight,dpr=devicePixelRatio||1;cv.width=W*dpr;cv.height=H*dpr;const c=cv.getContext('2d');c.setTransform(dpr,0,0,dpr,0,0);c.clearRect(0,0,W,H);
    const[x0,x1,y0,y1]=data.extent;const pad=28;const pb=legend?46:24;const sc=Math.min((W-2*pad)/(x1-x0),(H-pad-pb)/(y1-y0));const ox=(W-sc*(x1-x0))/2,oy=pad+((H-pad-pb)-sc*(y1-y0))/2;
    const plotH=sc*(y1-y0);const top=pad+((H-pad-pb)-plotH)/2;const X=x=>ox+(x-x0)*sc,Y=y=>top+plotH-(y-y0)*sc;const R=data.r*sc*.97;geo={X,Y,R};
    const hexpath=(px,py,r)=>{c.beginPath();for(let i=0;i<6;i++){const a=Math.PI/3*i+Math.PI/6;const qx=px+r*Math.cos(a),qy=py+r*Math.sin(a);i?c.lineTo(qx,qy):c.moveTo(qx,qy)}c.closePath()};
    c.fillStyle='#14323a';for(const[x,y]of data.bg||[]){hexpath(X(x),Y(y),R);c.fill()}
    const maxn=Math.max(...data.hex.map(d=>d.n),1);
    for(const d of data.hex){const t=Math.log1p(d.n)/Math.log1p(maxn);hexpath(X(d.x),Y(d.y),R);
      if(data.color==='density'){const lo=[22,84,92],hi2=[176,240,232];c.fillStyle=`rgb(${lo.map((v,i)=>Math.round(v+(hi2[i]-v)*t)).join(',')})`;c.globalAlpha=1}
      else{c.fillStyle=colorOf(d.cat);c.globalAlpha=.42+.58*t;if(hi!=null&&d.cat!==hi)c.globalAlpha=.09}
      c.fill();c.globalAlpha=1}
    if(labels&&data.color==='cluster'){c.font='600 13px Instrument Sans,sans-serif';c.textAlign='center';c.textBaseline='middle';
      for(const k of data.clusters){if(k.cx==null||(hi&&hi!==k.name))continue;const t=k.name.replace('Cluster ','');const px=X(k.cx),py=Y(k.cy);c.fillStyle='#071a20';c.beginPath();c.arc(px,py,12,0,7);c.fill();c.strokeStyle='#dcebe9';c.lineWidth=1.5;c.stroke();c.fillStyle='#f0f8f7';c.fillText(t,px,py+.5)}}
  }
  cv.addEventListener('mousemove',e=>{if(!geo)return;const b=cv.getBoundingClientRect();const mx=e.clientX-b.left,my=e.clientY-b.top;let best=null,bd=1e9;for(const d of data.hex){const q=(geo.X(d.x)-mx)**2+(geo.Y(d.y)-my)**2;if(q<bd){bd=q;best=d}}
    if(!best||bd>geo.R*geo.R*1.4){tip.style.display='none';return}
    tip.replaceChildren(h('b',{},`About ${count(best.n)} records`),...(best.top||[]).map(t=>h('div',{},`${t.name}: ${count(t.n)}`)));tip.style.display='block';tip.style.left=Math.min(mx+14,el.clientWidth-250)+'px';tip.style.top=Math.max(my-18,4)+'px'});
  cv.addEventListener('mouseleave',()=>{tip.style.display='none'});
  if(legend&&data.color!=='density'){const items=data.color==='cluster'?data.clusters.filter(k=>k.n!=null).map(k=>k.name):nm;
    el.append(h('div',{class:'maplegend'},items.map(n=>h('span',{},h('i',{style:`background:${colorOf(n)}`}),n))))}
  if(legend&&data.color==='density')el.append(h('div',{class:'maplegend'},'Brightness shows record density'));
  if(S.meta.privacy.k>1)el.append(h('div',{class:'mapnote'},`Each hexagon holds at least ${S.meta.privacy.k} records`));
  draw();new ResizeObserver(draw).observe(el);
  return{highlight(n){hi=n;draw()}};
}

/* ---------- Pages ---------- */
const Views={};
Views.overview=async p=>{
  const o=await api('/api/overview');const m=S.meta;
  const hero=h('section',{class:'hero'});const slide=h('div',{class:'slide'},h('div',{class:'map',id:'heromap'}));
  const prim=o.dims[m.primary];const nprod=(prim?.rows||[]).length;
  const title=m.domain?`${m.n_products} nanomedicine products, ${fmt(m.sources,0)} sources, ${fmt(m.n,0)} records`:`${fmt(m.n,0)} records, ${m.n_cols} fields`;
  const say=h('div',{class:'say'},h('h1',{},title),
    h('p',{},m.domain?'Each record holds what one source says about one product. The map places records with similar content side by side, so neighbouring hexagons cover similar topics.':'The map places records with similar content side by side, so neighbouring hexagons are alike.'),
    h('ul',{},o.insights.map(t=>h('li',{},t))),
    m.bases.length?h('a',{class:'go',href:'#clusters'},'Explore the clusters'):null);
  hero.append(slide,say);p.append(hero);
  if(o.filtered)p.append(h('div',{class:'notice'},`Filter active: showing about ${count(o.n)} records (${o.share}% of the data). Filtered counts are rounded to multiples of ${m.privacy.round_to}.`));
  m.bases.length?api('/api/map',{basis:m.bases[0].key}).then(d=>hexMap($('#heromap'),d)).catch(e=>$('#heromap').append(h('p',{class:'empty'},e.message))):$('#heromap').append(h('div',{class:'empty',style:'color:#8fabaa;padding-top:180px'},m.map_note||'The map is being prepared. This can take a few minutes.'));
  if(o.tree.length){
    const pan=h('section',{class:'panel'},h('h2',{},'Where is the data concentrated?'),h('p',{class:'sub'},'Area is proportional to record count. Outer frames are drug classes, inner boxes are products. Click any box to open its profile.'));
    const c=h('div',{class:'chart',style:'height:420px'});pan.append(c);p.append(pan);
    const dark=css('color-scheme').includes('dark');const tone=dark?[css('--seq-1'),css('--seq-2')]:[css('--seq-3'),css('--seq-4')];
    const tree=o.tree.map((t,i)=>({...t,itemStyle:{color:tone[i%2]}}));
    const tm=chart(c,{tooltip:{...tt(),formatter:i=>`<b>${esc(i.name)}</b><br>${count(i.value)} records`},series:[{type:'treemap',data:tree,roam:false,nodeClick:false,breadcrumb:{show:false},width:'100%',height:'100%',left:0,top:0,leafDepth:2,
      levels:[{itemStyle:{gapWidth:4,borderWidth:0,borderColor:css('--surface')}},{itemStyle:{gapWidth:2,borderWidth:0,borderColor:css('--surface')},upperLabel:{show:true,height:24,color:css('--ink'),backgroundColor:css('--surface'),fontWeight:600,fontSize:13,overflow:'truncate'}},{itemStyle:{borderWidth:1,borderColor:css('--surface'),gapWidth:0},label:{color:'#fff',fontSize:12.5,overflow:'truncate',formatter:i=>i.value>=100?`${i.name}\n${fmt(i.value,0)}`:i.name}}],
      visibleMin:40}]});
    tm.on('click',i=>{if(i.treePathInfo?.length>=2&&i.data?.name)openProfile(i.data.children?'_class':'_product',i.data.name)});
  }
  const g=h('section',{class:'grid3'});
  for(const[k,d]of Object.entries(o.dims)){if(k===m.primary&&o.tree.length)continue;const rows=d.rows.slice(0,12);g.append(h('div',{class:'panel'},h('h3',{style:'margin-bottom:10px'},d.label),barList(rows,{click:v=>openProfile(k,v)})))}
  if(o.groups.length>1)g.append(h('div',{class:'panel'},h('h3',{},'How complete is each type of information?'),h('p',{class:'sub',style:'margin-bottom:9px'},'Average share of filled values across the fields of each type. ',h('a',{href:'#coverage'},'See it by group')),barList(o.groups.map(r=>({value:r.group,title:`${r.group}: ${r.n_cols} fields`,n:r.fill})),{pct:true,wide:true})));
  p.append(g);
};


function openProfile(by,value){S.view.pro={by,value,tab:'summary'};if(location.hash==='#profile')route();else location.hash='profile'}
function compareBars(rows,name){
  const max=Math.max(...rows.flatMap(r=>[r.pct||0,r.all_pct||0]),1);
  return h('div',{class:'bars'},rows.map(r=>h('div',{class:'bar cmp',title:`${r.value}: ${name} ${r.pct??'very few'}${r.pct==null?'':'%'}, all records ${r.all_pct??'very few'}${r.all_pct==null?'':'%'}`},
    h('div',{class:'nm'},r.value),
    h('div',{class:'tr'},h('div',{class:'fl',style:`width:${100*(r.pct||0)/max}%`}),r.all_pct==null?null:h('i',{class:'tick',style:`left:${100*r.all_pct/max}%`})),
    h('div',{class:'v'},r.pct==null?'very few':r.pct>0&&r.pct<1||r.pct===0?'under 1%':`${fmt(r.pct,0)}%`))));
}
const cmpKey=name=>h('div',{class:'legendrow',style:'margin:0 0 10px'},h('span',{},h('i',{style:`background:${css('--accent')}`}),name),h('span',{},h('b',{class:'ticklg'}),'All records'));
function histCompare(el,f,name){
  const H=f.hist;const labels=H.bins.map(b=>fmt(b.a));
  chart(el,{grid:{left:38,right:8,top:10,bottom:38},legend:{show:false},
    tooltip:{...tt(),trigger:'axis',formatter:a=>{const b=H.bins[a[0].dataIndex];return`${fmt(b.a)} – ${fmt(b.b)}${f.unit?' '+esc(f.unit):''}<br>${esc(name)}: <b>${b.empty?'none':b.share==null?'very few':b.share+'%'}</b><br>All records: <b>${b.all_share==null?'very few':b.all_share+'%'}</b>`}},
    xAxis:{type:'category',data:labels,...axisStyle(),axisLabel:{...axisStyle().axisLabel,interval:Math.ceil(labels.length/4)-1,fontSize:11},splitLine:{show:false},name:(f.unit||'')+(H.log?' (log scale)':''),nameLocation:'middle',nameGap:24,nameTextStyle:{color:css('--ink-2'),fontSize:11}},
    yAxis:{type:'value',...axisStyle(),axisLabel:{...axisStyle().axisLabel,formatter:'{value}%',fontSize:11}},
    series:[{name,type:'bar',barCategoryGap:'8%',itemStyle:{color:css('--accent'),borderRadius:[2,2,0,0]},data:H.bins.map(b=>b.share)},{name:'All records',type:'line',symbol:'none',connectNulls:true,lineStyle:{width:2,color:css('--div-pos')},itemStyle:{color:css('--div-pos')},data:H.bins.map(b=>b.all_share)}]});
}
Views.profile=async p=>{
  const m=S.meta;if(!m.dims?.length){p.append(h('div',{class:'notice'},'This dataset has no grouping field.'));return}
  const usable=d=>d.options.filter(o=>o.value!=='Small groups'&&o.n>=m.privacy.min_cohort);
  if(!S.view.pro||!usable(m.dims.find(d=>d.key===S.view.pro.by)||{options:[]}).length){const d0=m.dims[0];S.view.pro={by:d0.key,value:usable(d0)[0]?.value,tab:'summary'}}
  const V=S.view.pro;const dim=m.dims.find(d=>d.key===V.by);const opts=usable(dim);
  if(!opts.some(o=>o.value===V.value))V.value=opts[0]?.value;
  const byS=h('select',{'aria-label':'View by'},m.dims.map(d=>h('option',{value:d.key,selected:d.key===V.by||null},d.label)));byS.onchange=()=>{V.by=byS.value;V.value=usable(m.dims.find(d=>d.key===V.by))[0]?.value;route()};
  const valS=h('select',{'aria-label':dim.label,style:'min-width:240px'},opts.map(o=>h('option',{value:o.value,selected:o.value===V.value||null},`${o.value} (${count(o.n)} records)`)));valS.onchange=()=>{V.value=valS.value;route()};
  p.append(h('div',{class:'controls',style:'margin:0'},h('label',{},'View by',byS),h('label',{},dim.label,valS)));
  const d=await api('/api/profile',{by:V.by,value:V.value});const name=d.value;
  const idline=[d.cls&&V.by!=='_class'?d.cls:null,d.platform&&V.by!=='_platform'?d.platform:null,d.api].filter(Boolean).join(', ');
  p.append(h('div',{class:'head'},h('h1',{},name),idline&&h('p',{class:'lead'},idline)));
  const tiles=[[count(d.n),'records'],[`${fmt(d.share,1)}%`,d.filtered?'of selected records':'of all records']];
  if(d.rank)tiles.push([`${d.rank} of ${d.n_groups}`,`${d.by_label.toLowerCase()} rank by records`]);
  if(d.sources&&d.n&&d.sources<.95*d.n)tiles.push([count(d.sources),'sources']);
  d.measurements.slice(0,4).filter(f=>!f.summary.suppressed).forEach(f=>tiles.push([`${fmt(f.summary.p50)}${f.unit&&f.unit!=='patients'?' '+f.unit:''}`,`median ${f.label[0].toLowerCase()+f.label.slice(1)}`]));
  p.append(h('section',{class:'panel facts wide'},tiles.map(([a,b])=>h('div',{},h('b',{},a),h('span',{},b)))));
  if(d.topic_pct!=null&&d.topic_pct<60)p.append(h('div',{class:'notice'},h('b',{},'Check the product label. '),`Only ${d.topic_pct}% of these records name the product or its active ingredient. The rest may come from sources about the general topic, so do not treat this profile as specific to ${name}.`));
  const TABS=[['summary','Summary'],['measurements',`Measurements (${d.measurements.length})`],['fields','All fields'],['relationships','Relationships']];
  p.append(h('div',{class:'seg',style:'align-self:flex-start'},TABS.map(([k,l])=>h('button',{'aria-pressed':V.tab===k?'true':'false',onclick:()=>{V.tab=k;route()}},l))));
  const body=h('div',{style:'display:contents'});p.append(body);
  const findGroup=g=>d.fields.find(x=>x.group===g);
  if(V.tab==='summary'){
    const grid=h('section',{class:'grid2'});
    for(const k of Object.keys(d.dims)){const dd=d.dims[k];if(dd.rows.length<2)continue;grid.append(h('div',{class:'panel'},h('h3',{style:'margin-bottom:8px'},`${dd.label}`),cmpKey(name),compareBars(dd.rows,name)))}
    if(d.coverage.length>1)grid.append(h('div',{class:'panel'},h('h3',{style:'margin-bottom:8px'},'Information coverage'),cmpKey(name),compareBars(d.coverage.map(r=>({value:r.group,pct:r.fill,all_pct:r.all})),name)));
    const safety=findGroup('Safety');if(safety)grid.append(h('div',{class:'panel'},h('h3',{},'Safety topics reported'),h('p',{class:'sub',style:'margin-bottom:8px'},'Share of records that mention each topic. This is how often sources discuss it, not how often it occurs in patients.'),cmpKey(name),compareBars(safety.rows.map(r=>({value:r.label,pct:r.pct,all_pct:r.all_pct})),name)));
    const eff=findGroup('Efficacy');if(eff)grid.append(h('div',{class:'panel'},h('h3',{},'Efficacy topics reported'),h('p',{class:'sub',style:'margin-bottom:8px'},'Share of records that mention each outcome, not the outcome value.'),cmpKey(name),compareBars(eff.rows.map(r=>({value:r.label,pct:r.pct,all_pct:r.all_pct})),name)));
    const dose=findGroup('Dosing and administration');if(dose){const routes=dose.rows.filter(r=>r.key.endsWith('_administration'));if(routes.length)grid.append(h('div',{class:'panel'},h('h3',{},'Administration routes reported'),h('p',{class:'sub',style:'margin-bottom:8px'},'Share of records that mention each route.'),cmpKey(name),compareBars(routes.map(r=>({value:r.label,pct:r.pct,all_pct:r.all_pct})),name)))}
    body.append(grid);
    if(d.terms.length)body.append(h('section',{class:'panel'},h('h2',{},`Phrases that set ${name} apart`),h('p',{class:'sub'},'Words much more common in these records than in the rest of the data, with the share of records using them.'),h('div',{},d.terms.map(t=>h('span',{class:'term',title:`All records: ${t.all_pct}%`},`${t.term} ${t.pct}%`)))));
  }else if(V.tab==='measurements'){
    if(!d.measurements.length){body.append(h('div',{class:'notice'},'No numeric field has enough values for this group.'));return}
    const ms=d.measurements;
    const fieldS=h('select',{},[...ms].sort((a,b)=>(b.summary.n??0)-(a.summary.n??0)).map(f=>h('option',{value:f.key,selected:f.key===(V.split_x||ms[0].key)||null},f.label)));
    const others=m.dims.filter(x=>x.key!==V.by);
    const splitS=h('select',{},others.map(x=>h('option',{value:x.key,selected:x.key===(V.split_y||others.find(o=>o.key==='_phase')?.key||others[0]?.key)||null},x.label)));
    const splitBody=h('div');
    const drawSplit=async()=>{V.split_x=fieldS.value;V.split_y=splitS.value;disposeIn(splitBody);splitBody.replaceChildren();await guarded(splitBody,async()=>{const e=await api('/api/explore',{x:fieldS.value,y:splitS.value,__only:{[V.by]:[V.value]}});renderExplore(splitBody,e)})};
    fieldS.onchange=drawSplit;splitS.onchange=drawSplit;
    body.append(h('section',{class:'panel'},h('h2',{},'Split a measurement'),h('p',{class:'sub'},`See how a measurement changes across subgroups within ${name}.`),h('div',{class:'controls'},h('label',{},'Measurement',fieldS),others.length?h('label',{},'Split by',splitS):null),splitBody));
    body.append(h('div',{class:'legendrow'},h('span',{},h('i',{style:`background:${css('--accent')}`}),name),h('span',{},h('b',{class:'lineLg'}),'All records'),h('span',{},'Bars show the share of values in each range. Ranges with few records are hidden.')));
    const strong=f=>!f.mixed&&(f.summary.n??0)>=30&&f.hist&&f.hist.bins.filter(b=>b.share!=null).length>=3;
    const grid=h('section',{class:'grid3'});body.append(grid);
    const weak=ms.filter(f=>!strong(f));const more=h('details',{class:'more'},h('summary',{},`${weak.length} more measurements with few values or mixed units`));const grid2=h('section',{class:'grid3',style:'margin-top:14px'});more.append(h('p',{class:'sub',style:'margin-top:8px'},'Shown separately because they rest on fewer than 30 values, have values spread too thinly to draw, or mix units that were not recorded. Read them with care.'),grid2);
    let drawnMore=false;more.addEventListener('toggle',()=>{if(more.open&&!drawnMore){drawnMore=true;weak.forEach(f=>card(f,grid2))}});
    if(weak.length)body.append(more);
    const card=(f,into)=>{const el=h('div',{class:'chart',style:'height:210px'});const s=f.summary,a=f.all_summary;
      into.append(h('div',{class:'panel'},h('h3',{},f.label),h('p',{class:'sub',style:'margin-bottom:6px'},s.suppressed?'Too few values for a summary.':`Median ${fmt(s.p50)}${a&&!a.suppressed?` vs ${fmt(a.p50)} overall`:''}, middle half ${fmt(s.p25)} – ${fmt(s.p75)}, n=${count(s.n)}${f.mixed?'. Units may be mixed.':''}`),f.hist&&f.hist.bins.some(b=>b.share!=null)?el:h('p',{class:'miss'},'Too few values in any one range to draw.')));
      if(f.hist&&f.hist.bins.some(b=>b.share!=null))requestAnimationFrame(()=>histCompare(el,f,name))};
    ms.filter(strong).forEach(f=>card(f,grid));
    if(!ms.some(strong))grid.append(h('p',{class:'miss'},'No measurement has enough values for a reliable chart. Open the section below to see the sparse ones.'));
    drawSplit();
  }else if(V.tab==='fields'){
    const groups=d.fields.map(x=>x.group);V.group=groups.includes(V.group)?V.group:(groups.includes('Safety')?'Safety':groups[0]);
    const q=h('input',{type:'search',placeholder:'Search fields','aria-label':'Search fields',style:'min-width:220px'});
    const gs=h('select',{'aria-label':'Information type'},h('option',{value:'*',selected:V.group==='*'||null},'All information types'),groups.map(g=>h('option',{selected:g===V.group||null},g)));
    const tb=h('tbody');
    const draw=()=>{tb.replaceChildren();const t=q.value.toLowerCase();d.fields.filter(x=>gs.value==='*'||x.group===gs.value).forEach(g=>{const rows=g.rows.filter(r=>!t||(r.label+' '+r.key).toLowerCase().includes(t));if(!rows.length)return;
      tb.append(h('tr',{class:'grp'},h('td',{colspan:4},`${g.group} (${rows.length})`)));
      rows.forEach(r=>tb.append(h('tr',{},h('td',{},r.label),h('td',{},r.pct==null?h('span',{class:'miss'},'very few'):h('div',{class:'fill'},h('u',{},h('b',{style:`width:${r.pct}%`})),h('span',{},`${fmt(r.pct,0)}%`))),h('td',{class:'num'},r.all_pct==null?'':`${fmt(r.all_pct,0)}%`),h('td',{},r.top?.length?r.top.map(x=>h('span',{class:'term',title:`${count(x.n)} records`},x.value)):r.kind==='num'?h('span',{class:'miss'},'See Measurements'):''))))})};
    q.oninput=draw;gs.onchange=()=>{V.group=gs.value;draw()};draw();
    body.append(h('div',{class:'controls',style:'margin:0'},q,gs),h('div',{class:'tablewrap',style:'max-height:74vh'},h('table',{},h('thead',{},h('tr',{},['Field',`Filled in ${name}`,'All records','Most common values'].map(x=>h('th',{},x)))),tb)));
  }else{
    const layout=h('section',{class:'maplayout'});const mapel=h('div',{class:'map'});const side=h('div',{class:'panel'});layout.append(mapel,side);body.append(layout);
    side.append(h('h2',{},`Where ${name} sits`),h('p',{class:'sub'},'Coloured hexagons hold these records. Dark ones are the rest of the data.'));
    if(d.clusters){side.append(h('h3',{style:'margin:6px 0'},'Share in each cluster'));side.append(h('div',{class:'clist',style:'max-height:280px'},d.clusters.rows.map(c=>h('div',{class:'crow'},h('i',{style:`background:${SLIDE[c.id]}`}),h('b',{},c.name),h('span',{class:'pct'},c.pct?`${c.pct}%`:'under 1%'),h('div',{class:'det'},c.terms.map(t=>h('span',{class:'term'},t)))))))}
    if(d.similar.length){side.append(h('h3',{style:'margin:14px 0 6px'},'Most similar by vocabulary'),barList(d.similar.map(x=>({value:x.name,n:Math.round(100*x.score)})),{pct:true,click:v=>openProfile(V.by,v)}))}
    if(m.bases.length)api('/api/map',{basis:d.clusters?.basis||m.bases[0].key,__only:{[V.by]:[V.value]}}).then(x=>hexMap(mapel,x)).catch(e=>mapel.append(h('p',{class:'empty',style:'color:#8fabaa'},e.message)));
    else mapel.append(h('p',{class:'empty',style:'color:#8fabaa'},'The map is being prepared.'));
    const nums=d.measurements;
    if(nums.length>=2){const X=V.rx||nums[0].key,Y=V.ry||nums[1].key;
      const xs=h('select',{},nums.map(f=>h('option',{value:f.key,selected:f.key===X||null},f.label)));const ys=h('select',{},nums.map(f=>h('option',{value:f.key,selected:f.key===Y||null},f.label)));
      const out=h('div');const go=async()=>{V.rx=xs.value;V.ry=ys.value;disposeIn(out);out.replaceChildren();await guarded(out,async()=>{const e=await api('/api/explore',{x:xs.value,y:ys.value,__only:{[V.by]:[V.value]}});renderExplore(out,e)})};xs.onchange=go;ys.onchange=go;
      body.append(h('section',{class:'panel'},h('h2',{},'Two measurements together'),h('div',{class:'controls',style:'margin-top:8px'},h('label',{},'First',xs),h('label',{},'Second',ys)),out));go()}
    const a=m.dims.find(x=>x.key==='_disease'&&x.key!==V.by),b=m.dims.find(x=>x.key==='_phase'&&x.key!==V.by);
    if(a&&b){const out=h('section',{class:'panel'});body.append(out);guarded(out,async()=>{renderExplore(out,await api('/api/explore',{x:a.key,y:b.key,__only:{[V.by]:[V.value]}}))})}
  }
};
function disposeIn(el){S.charts=S.charts.filter(c=>{if(el.contains(c.getDom())){c.dispose();return false}return true})}

Views.dictionary=async p=>{
  p.append(head('Data dictionary','What each field is, how often it is filled and how it is distributed. Select a row to open its summary.'));
  const d=await api('/api/dictionary');
  const q=h('input',{type:'search',placeholder:'Search fields: zeta, toxicity, phase…','aria-label':'Search fields',style:'min-width:260px'});
  const groups=[...new Set(d.map(x=>x.group))];
  const gs=h('select',{'aria-label':'Information type'},h('option',{value:''},'All information types'),groups.map(g=>h('option',{},g)));
  const ks=h('select',{'aria-label':'Data type'},h('option',{value:''},'All data types'),[['num','Numeric'],['cat','Categorical'],['text','Free text'],['id','Identifier']].map(([v,l])=>h('option',{value:v},l)));
  const tb=h('tbody');
  const table=h('div',{class:'tablewrap',style:'max-height:72vh'},h('table',{},h('thead',{},h('tr',{},['Field','Type','Filled','Distinct values','Typical values'].map(t=>h('th',{},t)))),tb));
  const KN={num:'Numeric',cat:'Categorical',text:'Free text',id:'Identifier (fill rate only)'};
  const typical=x=>{const s=x.summary;if(s&&!s.suppressed)return h('span',{},`median ${fmt(s.p50)}${x.unit&&x.unit!=='patients'?' '+x.unit:''}`,h('span',{class:'kind'},`  middle half ${fmt(s.p25)} – ${fmt(s.p75)}`));
    if(x.top?.length)return x.top.map(t=>h('span',{class:'term',title:`${count(t.n)} records`},t.value));if(x.kind==='id')return h('span',{class:'miss'},'hidden');return h('span',{class:'miss'},s?.suppressed?'too few values':'')};
  function draw(){tb.replaceChildren();const term=q.value.toLowerCase();
    groups.filter(g=>!gs.value||g===gs.value).forEach(g=>{const rows=d.filter(x=>x.group===g&&(!ks.value||x.kind===ks.value)&&(!term||(x.name+' '+x.label).toLowerCase().includes(term)));if(!rows.length)return;
      tb.append(h('tr',{class:'grp'},h('td',{colspan:5},`${g} (${rows.length})`)));
      rows.forEach(x=>{const can=x.mode==='full';tb.append(h('tr',{class:can?'click':'',tabindex:can?0:null,onclick:()=>can&&openColumn(x.name),onkeydown:e=>{if(can&&e.key==='Enter')openColumn(x.name)}},
        h('td',{},h('div',{},x.label!==x.name?x.label:x.name.replace(/_/g,' ')),x.label!==x.name?h('div',{class:'kind'},x.name):null),h('td',{class:'kind'},KN[x.kind]),
        h('td',{},x.fill_pct==null?h('span',{class:'miss'},'very few'):h('div',{class:'fill'},h('u',{},h('b',{style:`width:${x.fill_pct}%`})),h('span',{},`${fmt(x.fill_pct,0)}%`))),
        h('td',{class:'num'},x.unique==null?'':fmt(x.unique,0)),h('td',{},typical(x))))})})}
  [q,gs,ks].forEach(e=>e.addEventListener('input',draw));draw();
  p.append(h('div',{class:'controls'},q,gs,ks),table);
};
async function openColumn(name){
  const d=$('#drawer');d.replaceChildren();
  try{const c=await api('/api/column/'+encodeURIComponent(name));
    const close=()=>{d.replaceChildren()};
    const dr=h('aside',{class:'drawer',role:'dialog','aria-label':c.label},h('button',{class:'btn ghost close',onclick:close},'Close'),h('h2',{style:'padding-right:70px'},c.label),h('div',{class:'kind'},name+(c.group?` · ${c.group}`:'')));
    const facts=h('div',{class:'facts'},h('div',{},h('b',{},c.fill_pct==null?'very few':`${fmt(c.fill_pct,0)}%`),h('span',{},'filled')),h('div',{},h('b',{},count(c.filled)),h('span',{},'filled records')));
    if(c.summary&&!c.summary.suppressed)facts.append(h('div',{},h('b',{},fmt(c.summary.p50)),h('span',{},'median'+(c.unit?` (${c.unit})`:''))),h('div',{},h('b',{},`${fmt(c.summary.p5)} – ${fmt(c.summary.p95)}`),h('span',{},'5–95% range')));
    dr.append(facts);
    if(c.mixed)dr.append(h('div',{class:'notice'},'Units were not recorded for this field, so different units may be mixed.'));
    if(c.invalid)dr.append(h('p',{class:'sub',style:'margin:0'},`${count(c.invalid)} values outside the valid range were left out.`));
    if(c.hist){const box=h('div',{class:'chart',style:'height:240px'});dr.append(h('h3',{},'Distribution'),box);d.append(dr);histChart(box,c.hist,c.unit);}
    else{d.append(dr)}
    if(c.top?.length)dr.append(h('h3',{},'Most common values'),barList(c.top.map(t=>({value:t.value,n:t.n}))),h('p',{class:'sub',style:'margin:0'},`Values found in fewer than ${S.meta.privacy.k} records are not listed. Upper and lower case are merged.`));
    if(c.by_primary?.length)dr.append(h('h3',{},`Groups that fill it most`),barList(c.by_primary.map(t=>({value:t.value,n:t.pct})),{pct:true}));
    document.addEventListener('keydown',function k(e){if(e.key==='Escape'){close();document.removeEventListener('keydown',k)}});
  }catch(e){alertMsg(e.message)}
}
function alertMsg(t){const f=$('#fstatus');if(f){f.textContent=t;setTimeout(()=>{if(f)f.textContent=''},6000)}}
function histChart(el,H,unit){
  const labels=H.bins.map(b=>fmt(b.a));
  chart(el,{grid:{left:48,right:12,top:12,bottom:46},tooltip:{...tt(),formatter:i=>{const b=H.bins[i.dataIndex];return`${fmt(b.a)} – ${fmt(b.b)}${unit?' '+esc(unit):''}<br><b>${b.empty?'no records':b.n==null?lt()+' records':count(b.n)+' records'}</b>`}},
    xAxis:{type:'category',data:labels,...axisStyle(),axisLabel:{...axisStyle().axisLabel,interval:Math.ceil(labels.length/6)-1},name:(unit||'')+(H.log?' (log scale)':''),nameLocation:'middle',nameGap:28,nameTextStyle:{color:css('--ink-2')},splitLine:{show:false}},
    yAxis:{type:'value',...axisStyle(),axisLabel:{...axisStyle().axisLabel,formatter:v=>fmt(v)},name:'records',nameTextStyle:{color:css('--ink-2'),align:'right'}},
    series:[{type:'bar',barCategoryGap:'6%',itemStyle:{color:css('--accent'),borderRadius:[3,3,0,0]},data:H.bins.map(b=>b.n)}]});
}

function shade(v){const st=seq();const t=Math.max(0,Math.min(1,(v||0)/100))*(st.length-1);const i=Math.min(Math.floor(t),st.length-2);
  const hx=c=>[1,3,5].map(j=>parseInt(c.slice(j,j+2),16));const A=hx(st[i]),B=hx(st[i+1]);const f=t-i;return`rgb(${A.map((x,j)=>Math.round(x+(B[j]-x)*f)).join(',')})`}
function divShade(dpp){const t=Math.max(-1,Math.min(1,dpp/25));const hx=c=>[1,3,5].map(j=>parseInt(c.slice(j,j+2),16));const M=hx(css('--div-mid')),E=hx(t<0?css('--div-neg'):css('--div-pos'));const f=Math.abs(t);return`rgb(${M.map((x,j)=>Math.round(x+(E[j]-x)*f)).join(',')})`}
const inkOn=v=>v>55?(css('color-scheme').includes('dark')?'#06262a':'#fff'):css('--ink');
const pct=v=>v==null?'':`${fmt(v,0)}%`;
Views.coverage=async p=>{
  const m=S.meta;if(!m.dims?.length){p.append(head('Coverage'),h('div',{class:'notice'},'This file has no grouping field, so coverage cannot be shown by group. See the Data dictionary for overall fill rates.'));return}
  const V=S.view.cov||(S.view.cov={by:m.primary,order:'size',group:null,open:null});
  if(!m.dims.some(d=>d.key===V.by))V.by=m.primary;
  let d=await api('/api/completeness',{by:V.by,order:V.order,group:V.group||''});
  if(!V.group&&d.groups.length===1){V.group=d.groups[0].name;d=await api('/api/completeness',{by:V.by,order:V.order,group:V.group})}
  const level=V.group?'fields':'types';
  p.append(head('Coverage',level==='types'?'How complete is the information for each group? Each cell is the average share of a type’s fields that are filled in that group’s records.':`How often each field of “${V.group}” is filled, by group. Each cell is the share of that group’s records with the field filled.`));
  const byS=h('select',{},m.dims.map(x=>h('option',{value:x.key,selected:x.key===V.by||null},x.label)));byS.onchange=()=>{V.by=byS.value;V.open=null;route()};
  const ord=h('div',{class:'seg'},[['size','Most records'],['coverage','Most complete'],['name','Name'],['similar','Similar patterns']].map(([k,l])=>h('button',{'aria-pressed':V.order===k?'true':'false',title:k==='similar'?'Groups whose fields are filled in a similar way are placed next to each other':null,onclick:()=>{V.order=k;route()}},l)));
  p.append(h('div',{class:'controls'},h('label',{},'Groups',byS),h('label',{},'Order',ord)));
  const crumbs=h('div',{class:'crumbs'},level==='fields'&&d.groups.length>1?h('button',{class:'textlink',onclick:()=>{V.group=null;V.open=null;route()}},'All information types'):h('b',{},level==='types'?'All information types':V.group),level==='fields'&&d.groups.length>1?[h('span',{},' › '),h('b',{},`${V.group} (${d.cols.length} fields)`)]:null);
  const hint=h('p',{class:'sub',style:'margin:2px 0 0'},level==='types'?'Select a column heading to see its fields. Select a cell or a group name to see more.':'Select a group name to compare it with all records.');
  const legend=h('div',{class:'covlegend'},h('span',{},'0%'),h('i',{style:`background:linear-gradient(90deg,${seq().join(',')})`}),h('span',{},'100% filled'));
  if(!d.rows.length){p.append(h('div',{class:'notice'},'No group in this selection has enough records to show.'));return}
  const ncol=d.cols.length+2;const tb=h('tbody');
  const cell=(v,on)=>h('td',{class:'cv'+(on?' click':''),style:`background:${shade(v)};color:${inkOn(v)}`,onclick:on,tabindex:on?0:null,onkeydown:on?(e=>{if(e.key==='Enter')on()}):null},pct(v));
  const head2=h('tr',{},h('th',{class:'sticky'},d.by_label),h('th',{class:'num'},'Records'),d.cols.map(c=>h('th',{class:'colh',title:c.n_fields?`${c.label}: ${c.n_fields} fields`:c.label},level==='types'?h('button',{class:'textlink',onclick:()=>{V.group=c.key;V.open=null;route()}},c.label):c.label)));
  const all=d.all;
  async function detail(box,r,col){
    const prof=h('button',{class:'btn ghost',onclick:()=>openProfile(V.by,r.name)},`Open the ${r.name} profile`);
    const close=h('button',{class:'link',onclick:()=>{V.open=null;draw()}},'Close');
    if(col==null||level==='fields'){
      const rows=d.cols.map((c,j)=>({value:c.label,pct:r.values[j],all_pct:all[j]})).sort((a,b)=>(b.pct-b.all_pct)-(a.pct-a.all_pct));
      const ahead=rows.filter(x=>x.pct-x.all_pct>=5).slice(0,3).map(x=>x.value),behind=rows.filter(x=>x.all_pct-x.pct>=5).slice(-3).map(x=>x.value);
      box.append(h('div',{class:'detailhead'},h('h3',{},`${r.name} compared with all records`),h('div',{},prof,close)),
        h('p',{class:'sub'},[ahead.length?`More complete than average: ${ahead.join(', ')}.`:'',behind.length?` Less complete: ${behind.join(', ')}.`:''].join('')||'Close to the average everywhere.'),cmpKey(r.name),compareBars(rows,r.name));
    }else{
      const c=d.cols[col];box.append(h('div',{class:'detailhead'},h('h3',{},`${c.label} fields in ${r.name}`),h('div',{},prof,close)),h('p',{class:'sub'},'Loading…'));
      try{const e=await api('/api/completeness',{by:V.by,order:'name',group:c.key});const rr=e.rows.find(x=>x.name===r.name);
        box.querySelector('.sub').textContent=`Share of ${r.name} records that fill each ${c.label.toLowerCase()} field, against all records.`;
        box.append(cmpKey(r.name),compareBars(e.cols.map((f,j)=>({value:f.label,pct:rr.values[j],all_pct:e.all[j]})),r.name),h('button',{class:'link',style:'margin-top:8px',onclick:()=>{V.group=c.key;V.open=null;route()}},`Show every group for ${c.label.toLowerCase()}`))}
      catch(err){box.querySelector('.sub').textContent=err.message}}
  }
  const table=h('div',{class:'tablewrap covwrap'},h('table',{class:'cov'},h('thead',{},head2),tb));
  function draw(){const keep=table.scrollLeft;tb.replaceChildren();tb.append(h('tr',{class:'baseline'},h('td',{class:'sticky'},'All records'),h('td',{class:'num'},count(d.n_all)),d.all.map(v=>cell(v))));
    d.rows.forEach(r=>{const key=r.name;const isOpen=V.open&&V.open.row===key;const toggle=(colIdx)=>{V.open=isOpen&&V.open.col===colIdx?null:{row:key,col:colIdx};draw()};
      tb.append(h('tr',{class:isOpen?'opened':''},h('td',{class:'sticky'},h('button',{class:'textlink rowname','aria-expanded':isOpen?'true':'false',onclick:()=>toggle(null)},(isOpen?'▾ ':'▸ ')+key)),h('td',{class:'num'},count(r.n)),r.values.map((v,j)=>cell(v,level==='types'?()=>toggle(j):()=>toggle(null)))));
      if(isOpen){const box=h('div',{class:'covdetail'});tb.append(h('tr',{class:'detailrow'},h('td',{colspan:ncol},box)));detail(box,r,V.open.col)}});table.scrollLeft=keep}
  draw();
  p.append(h('section',{class:'panel'},h('div',{class:'covtop'},h('div',{},crumbs,hint),legend),table));
};

Views.distribution=async p=>{
  const V=S.view.dag||(S.view.dag={x:S.meta.domain?'particle_size_clean':(S.meta.columns.find(c=>c.kind==='num')||S.meta.columns[0]).name,y:S.meta.domain?'_platform':(S.meta.dims[0]?.key||'')});
  p.append(head('Distribution studio','Choose two fields and the chart type follows. Regions and summaries are shown rather than individual points.'));
  const allgr={};S.meta.columns.forEach(c=>{(allgr[c.group]=allgr[c.group]||[]).push(c)});
  const opts=(cur,empty)=>[empty&&h('option',{value:''},empty),h('optgroup',{label:'Derived dimensions'},S.meta.dims.map(d=>h('option',{value:d.key,selected:d.key===cur||null},d.label))),...Object.entries(allgr).map(([g,cs])=>h('optgroup',{label:g},cs.map(c=>h('option',{value:c.name,selected:c.name===cur||null},`${c.label}${c.kind==='num'?' (numeric)':''}`))))];
  const xs=h('select',{},opts(V.x));const ys=h('select',{},opts(V.y,'None'));
  xs.onchange=()=>{V.x=xs.value;route(true)};ys.onchange=()=>{V.y=ys.value;route(true)};
  const presets=S.meta.domain?[['Size by platform','particle_size_clean','_platform'],['Size and zeta','particle_size_clean','zeta_potential'],['Drug class and phase','_class','_phase'],['Disease and phase','_disease','_phase'],['PDI by platform','polydispersity','_platform'],['Patients by drug class','number_of_patients_clean','_class']]:[];
  p.append(h('div',{class:'controls'},h('label',{},'First field',xs),h('label',{},'Second field',ys),presets.length?h('div',{class:'chips'},presets.map(([l,x,y])=>h('button',{class:'chip',onclick:()=>{Object.assign(V,{x,y});route(true)}},l))):null));
  const d=await api('/api/explore',{x:V.x,y:V.y||''});
  const pan=h('section',{class:'panel'});p.append(pan);renderExplore(pan,d);
};
function renderExplore(pan,d){
  const u=(l,x)=>l+(x&&x!=='patients'?` (${x})`:'');
  if(d.mixed)pan.append(h('div',{class:'notice',style:'margin-bottom:12px'},'Units were not recorded for the selected field, so they may be mixed.'));
  const tableBtn=(rowsFn)=>{const b=h('button',{class:'btn ghost',style:'margin-top:12px'},'Show as table');const hold=h('div');b.onclick=()=>{if(hold.childElementCount){hold.replaceChildren();b.textContent='Show as table'}else{const[hd,rows]=rowsFn();hold.replaceChildren(h('div',{class:'tablewrap',style:'margin-top:10px;max-height:360px'},h('table',{},h('thead',{},h('tr',{},hd.map(t=>h('th',{},t)))),h('tbody',{},rows.map(r=>h('tr',{},r.map(v=>h('td',{},v))))))));b.textContent='Hide table'}};return[b,hold]};
  if(d.view==='hist'){pan.append(h('h2',{},u(d.xlabel,d.xunit)));if(!d.hist){pan.append(h('p',{class:'empty'},'There are not enough values for a distribution.'));return}
    const s=d.summary;pan.append(h('div',{class:'facts',style:'margin:10px 0 14px'},[['Values',count(s.n)],['Median',fmt(s.p50)],['Middle half',`${fmt(s.p25)} – ${fmt(s.p75)}`],['5–95%',`${fmt(s.p5)} – ${fmt(s.p95)}`]].map(([a,b])=>h('div',{},h('b',{},b),h('span',{},a)))));
    const c=h('div',{class:'chart'});pan.append(c);histChart(c,d.hist,d.xunit);pan.append(...tableBtn(()=>[['Range','Records'],d.hist.bins.map(b=>[`${fmt(b.a)} – ${fmt(b.b)}`,b.empty?'0':count(b.n)])]))}
  else if(d.view==='bars'){pan.append(h('h2',{},d.xlabel),h('p',{class:'sub'},`${count(d.filled)} filled records. Most common values.`),barList(d.top))}
  else if(d.view==='box'){pan.append(h('h2',{},`${u(d.xlabel,d.xunit)} by ${d.ylabel.toLowerCase()}`),h('p',{class:'sub'},`The box is the middle half of values, the line is the median and the whiskers are the 5th and 95th percentiles. Groups need at least ${S.meta.privacy.num_min} values.`));
    if(!d.groups.length){pan.append(h('p',{class:'empty'},'There are not enough values in this selection.'));return}
    const c=h('div',{class:'chart',style:`height:${Math.max(280,d.groups.length*36+70)}px`});pan.append(c);
    const pos=d.groups.every(g=>g.q[0]>0);const ratio=pos?d.groups.reduce((a,g)=>Math.max(a,g.q[4]),0)/Math.max(d.groups.reduce((a,g)=>Math.min(a,g.q[0]),1e12),1e-9):1;
    chart(c,{grid:{left:170,right:30,top:12,bottom:48},tooltip:{...tt(),formatter:i=>{const g=d.groups[i.dataIndex];return`<b>${esc(g.group)}</b> (${count(g.n)})<br>Median: ${fmt(g.q[2])}<br>Middle half: ${fmt(g.q[1])} – ${fmt(g.q[3])}<br>5–95%: ${fmt(g.q[0])} – ${fmt(g.q[4])}`}},
      yAxis:{type:'category',inverse:true,data:d.groups.map(g=>g.group),...axisStyle(),axisLabel:{color:css('--ink'),width:155,overflow:'truncate',fontSize:12.5},splitLine:{show:false}},
      xAxis:{type:ratio>200?'log':'value',...axisStyle(),axisLabel:{...axisStyle().axisLabel,formatter:v=>fmt(v)},name:u(d.xlabel,d.xunit)+(ratio>200?' (log scale)':''),nameLocation:'middle',nameGap:30,nameTextStyle:{color:css('--ink-2')}},
      series:[{type:'boxplot',data:d.groups.map(g=>g.q),itemStyle:{color:css('--seq-1'),borderColor:css('--accent'),borderWidth:1.5},boxWidth:[8,20]}]});
    pan.append(...tableBtn(()=>[['Group','Records','5%','25%','Median','75%','95%'],d.groups.map(g=>[g.group,count(g.n),...g.q.map(v=>fmt(v))])]))}
  else if(d.view==='grid'){pan.append(h('h2',{},`${u(d.xlabel,d.xunit)} and ${u(d.ylabel,d.yunit)}`));
    if(d.too_few){pan.append(h('p',{class:'empty'},'Too few records have both fields filled.'));return}
    pan.append(h('p',{class:'sub'},`${count(d.n)} records have both. Spearman correlation: ${d.rho==null?'not calculated':fmt(d.rho)}${d.rho!=null&&Math.abs(d.rho)<.2?' (no clear joint trend)':''}. Cells with few records are hidden${d.hidden_points?`, so about ${count(d.hidden_points)} records are not drawn`:''}.`));
    const c=h('div',{class:'chart',style:'height:480px'});pan.append(c);
    chart(c,{grid:{left:70,right:20,top:12,bottom:70},tooltip:{...tt(),formatter:i=>{const[a,b,n]=i.value;return`${esc(d.xlabel)}: ${fmt(d.xe[a])} – ${fmt(d.xe[a+1])}<br>${esc(d.ylabel)}: ${fmt(d.ye[b])} – ${fmt(d.ye[b+1])}<br><b>${count(n)} records</b>`}},
      xAxis:{type:'category',data:d.xe.slice(0,-1).map(v=>fmt(v)),...axisStyle(),name:u(d.xlabel,d.xunit)+(d.xlog?' (log scale)':''),nameLocation:'middle',nameGap:32,nameTextStyle:{color:css('--ink-2')},splitLine:{show:false},axisLabel:{...axisStyle().axisLabel,interval:3}},
      yAxis:{type:'category',data:d.ye.slice(0,-1).map(v=>fmt(v)),...axisStyle(),name:u(d.ylabel,d.yunit)+(d.ylog?' (log scale)':''),nameLocation:'middle',nameGap:48,nameTextStyle:{color:css('--ink-2')},splitLine:{show:false},axisLabel:{...axisStyle().axisLabel,interval:4}},
      visualMap:{min:S.meta.privacy.k,max:Math.max(...d.cells.map(x=>x[2]),S.meta.privacy.k+1),orient:'horizontal',left:70,bottom:0,itemWidth:12,itemHeight:140,textStyle:{color:css('--ink-2'),fontSize:12},text:['more','fewer'],inRange:{color:seq().slice(1)}},
      series:[{type:'heatmap',data:d.cells,itemStyle:{borderRadius:2}}]})}
  else{pan.append(h('h2',{},`${d.xlabel} and ${d.ylabel}`),h('p',{class:'sub'},`Cell colour shows what share of each row falls in that column. ${count(d.n)} records have both.`));
    const c=h('div',{class:'chart',style:`height:${Math.max(320,d.rows.length*32+130)}px`});pan.append(c);
    chart(c,{grid:{left:170,right:14,top:90,bottom:40},tooltip:{...tt(),formatter:i=>`<b>${esc(d.rows[i.value[1]])}</b> and ${esc(d.cols[i.value[0]])}<br>${count(i.value[2])} records, ${i.value[3]}% of the row`},
      xAxis:{type:'category',position:'top',data:d.cols,axisLabel:{color:css('--ink-2'),rotate:30,interval:0,width:110,overflow:'truncate'},axisLine:{show:false},axisTick:{show:false}},
      yAxis:{type:'category',inverse:true,data:d.rows,axisLabel:{color:css('--ink'),width:155,overflow:'truncate',fontSize:12.5},axisLine:{show:false},axisTick:{show:false}},
      visualMap:{dimension:3,min:0,max:100,orient:'horizontal',left:170,bottom:0,itemWidth:12,itemHeight:150,textStyle:{color:css('--ink-2'),fontSize:12},text:['100%','0%'],inRange:{color:seq()}},
      series:[{type:'heatmap',data:d.cells.map(x=>({value:x,label:{color:x[3]>55?(css('color-scheme').includes('dark')?'#06262a':'#fff'):css('--ink')}})),label:{show:d.cols.length<=8,formatter:i=>`${i.value[3]}%`,fontSize:11},itemStyle:{borderColor:css('--surface'),borderWidth:2,borderRadius:2}}]});
    pan.append(...tableBtn(()=>[['Row','Column','Records','Share of row'],d.cells.map(x=>[d.rows[x[1]],d.cols[x[0]],count(x[2]),`${x[3]}%`])]))}
}

Views.clusters=async p=>{
  const m=S.meta;
  p.append(head('Clusters','Groups similar records automatically. The map shows regions of at least '+m.privacy.k+' records rather than individual records. Change the features used at the top.'));
  if(!m.bases.length){p.append(h('div',{class:'notice'},'The map is being prepared. Refresh in a few minutes.'));return}
  const V=S.view.kum||(S.view.kum={basis:m.bases[0].key,k:0,color:'cluster'});
  const basis=m.bases.find(b=>b.key===V.basis)||m.bases[0];
  const seg=h('div',{class:'seg'},m.bases.map(b=>h('button',{'aria-pressed':b.key===basis.key?'true':'false',title:b.desc,onclick:()=>{V.basis=b.key;V.k=0;route(true)}},b.label)));
  const d=await api('/api/map',{basis:basis.key,k:V.k,color:V.color});
  const ks=h('select',{},basis.ks.map(k=>h('option',{value:k,selected:k===d.k||null},`${k} clusters${k===d.best?' (best separation)':''}`)));ks.onchange=()=>{V.k=+ks.value;route(true)};
  const cs=h('select',{},[['cluster','Cluster'],['density','Density'],...m.dims.map(x=>[x.key,x.label])].map(([v,l])=>h('option',{value:v,selected:v===V.color||null},l)));cs.onchange=()=>{V.color=cs.value;route(true)};
  p.append(h('div',{class:'controls'},h('label',{},'Cluster by',seg),h('label',{},'Number of clusters',ks),h('label',{},'Map colour',cs)));
  p.append(h('p',{class:'sub',style:'margin:-16px 0 -12px'},basis.desc+'.'));
  const mapel=h('div',{class:'map'});const list=h('div',{class:'clist'});
  const silword=d.silhouette>=.5?'strong':d.silhouette>=.25?'moderate':'weak';
  const side=h('div',{class:'panel'},h('h2',{},'Phrases that define each cluster'),h('p',{class:'sub'},`Separation is ${silword} (silhouette ${fmt(d.silhouette,2)}). ${d.silhouette<.25?'Clusters overlap, so read them as topic tendencies rather than strict classes. ':''}The map covers about ${d.coverage}% of records.`),list);
  p.append(h('section',{class:'maplayout'},mapel,side));
  const mp=hexMap(mapel,d);
  const firstDim=m.dims[0]?.key;
  d.clusters.forEach((k,i)=>{const top=(k.dims?.[S.meta.domain?'_class':firstDim]||[]).slice(0,3).map(x=>`${x.value} ${x.pct}%`).join(', ');
    list.append(h('div',{class:'crow',onmouseenter:()=>mp.highlight(V.color==='cluster'?k.name:null),onmouseleave:()=>mp.highlight(null)},h('i',{style:`background:${SLIDE[i]}`}),h('b',{},k.name),h('span',{class:'pct'},k.n==null?'very few':`${count(k.n)} records, ${k.pct}%`),h('div',{class:'det'},h('div',{},k.terms.slice(0,6).map(t=>h('span',{class:'term'},t))),top&&h('div',{},top))))});
  const sb=h('div',{class:'chart',style:'height:170px'});
  p.append(h('section',{class:'panel'},h('h3',{},'How many clusters fit best?'),h('p',{class:'sub'},'A taller bar means better separation. If every value is low, the data does not naturally split into distinct groups.'),sb));
  const ksk=Object.keys(d.sil);chart(sb,{grid:{left:44,right:10,top:10,bottom:28},tooltip:{...tt(),formatter:i=>`${esc(i.name)} clusters: silhouette ${fmt(i.value,3)}`},xAxis:{type:'category',data:ksk,...axisStyle(),splitLine:{show:false}},yAxis:{type:'value',...axisStyle(),min:0,axisLabel:{...axisStyle().axisLabel,formatter:v=>fmt(v)}},series:[{type:'bar',barWidth:30,data:ksk.map(q=>({value:d.sil[q],itemStyle:{color:+q===d.k?css('--accent'):css('--seq-1'),borderRadius:[3,3,0,0]}}))}]});
};

Views.compare=async p=>{
  const m=S.meta;const V=S.view.cmp||(S.view.cmp={by:m.primary,items:m.dims.find(d=>d.key===m.primary)?.options.slice(0,2).map(o=>o.value)||[]});
  p.append(head('Compare','Put up to four groups side by side. In numeric rows the thin line is the 5–95% range, the thick line the middle half and the dot the median.'));
  const dim=m.dims.find(d=>d.key===V.by);
  const byS=h('select',{},m.dims.map(d=>h('option',{value:d.key,selected:d.key===V.by||null},d.label)));byS.onchange=()=>{V.by=byS.value;const o=m.dims.find(d=>d.key===V.by).options.filter(x=>x.value!=='Small groups'&&x.value!=='Not specified');V.items=o.slice(0,2).map(x=>x.value);route(true)};
  const add=h('select',{},h('option',{value:''},'Add a group'),dim.options.filter(o=>!V.items.includes(o.value)&&o.value!=='Small groups').map(o=>h('option',{value:o.value},`${o.value} (${count(o.n)})`)));add.onchange=()=>{if(add.value&&V.items.length<4){V.items.push(add.value);route(true)}};
  p.append(h('div',{class:'controls'},h('label',{},'Compare by',byS),h('label',{},'Groups',add),h('div',{class:'chips'},V.items.map(i=>h('button',{class:'chip',title:'Remove',onclick:()=>{V.items=V.items.filter(x=>x!==i);route(true)}},`${i}  ×`)))));
  if(!V.items.length){p.append(h('div',{class:'empty'},'Add a group to begin.'));return}
  const d=await api('/api/compare',{items:V.items.join('||'),by:V.by});
  const items=d.items;const n=items.length;const pan=h('section',{class:'panel'});const g=h('div',{class:'cmpgrid'});pan.append(g);p.append(pan);
  const row=(lab,sub,cells)=>h('div',{class:'cmprow',style:`--n:${n}`},h('div',{class:'lab'},lab,sub&&h('small',{},sub)),cells);
  g.append(h('div',{class:'cmprow',style:`--n:${n};border-top:0`},h('div',{}),items.map(i=>h('div',{},h('h2',{},h('button',{class:'textlink',style:'font:inherit',onclick:()=>openProfile(V.by,i.name)},i.name)),h('div',{class:'kind'},i.too_small?'Too few records':`${count(i.n)} records`),i.platform&&h('div',{class:'kind'},`${i.cls}, ${i.platform}`)))));
  const ok=items.filter(i=>!i.too_small);
  d.numeric.forEach(nm=>{
    const ss=ok.map(i=>i.num[nm.key]).filter(s=>s&&!s.suppressed);if(!ss.length)return;
    const lo=Math.min(...ss.map(s=>s.p5)),hi=Math.max(...ss.map(s=>s.p95));const lg=lo>0&&hi/lo>100;
    const pos=v=>{if(hi===lo)return 50;return lg?100*(Math.log10(v)-Math.log10(lo))/(Math.log10(hi)-Math.log10(lo)):100*(v-lo)/(hi-lo)};
    g.append(row(nm.label,(nm.unit&&nm.unit!=='patients'?nm.unit:'')+(nm.mixed?' units may be mixed':''),items.map(i=>{const s=i.too_small?null:i.num[nm.key];if(!s||s.suppressed)return h('div',{class:'miss'},'not enough values');
      const col=css('--accent');const sv=`<svg width="100%" height="26" aria-hidden="true"><line x1="${pos(s.p5)}%" x2="${pos(s.p95)}%" y1="13" y2="13" stroke="${col}" stroke-width="1.5" opacity=".55"/><line x1="${pos(s.p25)}%" x2="${pos(s.p75)}%" y1="13" y2="13" stroke="${col}" stroke-width="6" stroke-linecap="round" opacity=".55"/><circle cx="${pos(s.p50)}%" cy="13" r="5.5" fill="${col}" stroke="${css('--surface')}" stroke-width="2"/></svg>`;
      return h('div',{},h('div',{html:sv}),h('div',{class:'kind'},`median ${fmt(s.p50)}, ${fmt(s.p25)} – ${fmt(s.p75)} (n=${count(s.n)})`))})))});
  d.dims.forEach(dm=>{
    const names=[];ok.forEach(i=>(i.dims[dm.key]||[]).forEach(r=>{if(!names.includes(r.value))names.push(r.value)}));
    if(names.length<2||ok.every(i=>(i.dims[dm.key]||[]).length===1))return;names.sort((a,b)=>a.localeCompare(b,'en'));const pal=palette();const colr=v=>{if(v==='Not specified')return css('--other');const ix=names.filter(x=>x!=='Not specified').indexOf(v);return ix<7?pal[ix]:css('--other')};
    g.append(row(dm.label,'share of records',items.map(i=>{if(i.too_small)return h('div',{class:'miss'},'');const rs=i.dims[dm.key]||[];
      return h('div',{},h('div',{class:'stack',role:'img','aria-label':rs.map(r=>`${r.value} ${r.pct}%`).join(', ')},rs.map(r=>h('i',{title:`${r.value}: ${r.pct}%`,style:`width:${r.pct}%;background:${colr(r.value)}`}))),h('div',{class:'legendrow'},rs.slice(0,4).map(r=>h('span',{},h('i',{style:`background:${colr(r.value)}`}),`${r.value} ${r.pct}%`))))})))});
  d.text.forEach(t=>g.append(row(t.label,'most common phrases',items.map(i=>i.too_small?h('div'):h('div',{},(i.tops[t.key]||[]).map(x=>h('span',{class:'term',title:`${count(x.n)} records`},x.value)))))));
  const grps=ok[0]?.groups.map(x=>x.group)||[];
  g.append(row('Information coverage','average by field type',items.map(i=>i.too_small?h('div'):barList([...i.groups].sort((a,b)=>grps.indexOf(a.group)-grps.indexOf(b.group)).map(r=>({value:r.group,n:r.fill})),{pct:true}))));
};

Views.relationships=async p=>{
  const V=S.view.ili||(S.view.ili={tab:'flow',group:'',unspec:false});
  p.append(head('Relationships','How groups connect, which fields are reported together and which numbers move together.'));
  p.append(h('div',{class:'seg',style:'align-self:flex-start'},[['flow','How groups connect'],['cooc','Reported together'],['corr','Numbers that move together']].map(([k,l])=>h('button',{'aria-pressed':V.tab===k?'true':'false',onclick:()=>{V.tab=k;route(true)}},l))));
  if((S.meta.dims||[]).length<2){p.append(h('div',{class:'notice'},'This view needs at least two grouping fields.'));V.tab='cooc'}
  if(V.tab==='flow'){const d=await api('/api/flow',{unspecified:V.unspec?'true':'false'});
    const pan=h('section',{class:'panel'},h('h2',{},d.dims.map(x=>x.label).join(', ')),h('p',{class:'sub'},'Band width is record count. A record joins the flow when it states both neighbouring columns. Bands with few records are not drawn.'));
    const cb=h('input',{type:'checkbox',checked:V.unspec||null,onchange:()=>{V.unspec=cb.checked;route(true)}});pan.append(h('label',{style:'display:flex;gap:7px;font-size:13.5px;margin-bottom:10px'},cb,'Also show “Not specified” records'));
    const c=h('div',{class:'chart',style:'height:640px'});pan.append(c);p.append(pan);
    const pal=palette();
    chart(c,{tooltip:{...tt(),formatter:i=>i.dataType==='edge'?`${esc(i.data.source.split('§')[1])} to ${esc(i.data.target.split('§')[1])}<br><b>${count(i.data.value)} records</b>`:`${esc(i.data.label)}<br><b>${count(i.value)} records</b>`},
      series:[{type:'sankey',left:8,right:190,top:10,bottom:10,nodeWidth:12,nodeGap:7,nodeAlign:'justify',layoutIterations:32,emphasis:{focus:'adjacency'},
        data:d.nodes.map(n=>({...n,depth:n.depth,itemStyle:{color:pal[n.depth],borderWidth:0,borderRadius:2}})),links:d.links,
        label:{color:css('--ink'),fontSize:12.5,formatter:i=>i.data.label},lineStyle:{color:'gradient',opacity:.3,curveness:.5}}]});
  }else if(V.tab==='cooc'){const d=await api('/api/cooccurrence',{group:V.group});
    const sel=h('select',{},h('option',{value:''},'Most filled fields'),d.groups.map(g=>h('option',{selected:g===V.group||null},g)));sel.onchange=()=>{V.group=sel.value;route(true)};
    const pan=h('section',{class:'panel'},h('h2',{},'When a record reports one field, what else does it report?'),
      h('p',{class:'sub'},'Read across a row: of the records that report the row field, the share that also report the column field. Colour compares that share with the column’s overall share (under each heading): orange means the two are reported together more often than usual, blue less often.'),h('div',{class:'controls'},h('label',{},'Information type',sel)));
    if(d.cols.length<2){pan.append(h('p',{class:'empty'},'This type has too few filled fields to compare.'));p.append(pan);return}
    const tb=h('tbody');
    d.cols.forEach((rlab,i)=>{const vals={};d.cells.filter(c=>c[1]===i).forEach(c=>vals[c[0]]=c);
      tb.append(h('tr',{},h('td',{class:'sticky'},rlab),d.cols.map((c,j)=>{if(i===j)return h('td',{class:'cv self'},'');const x=vals[j];if(!x)return h('td',{class:'cv'},'');const lift=d.base[j]?x[2]/d.base[j]:1;
        const dpp=x[2]-d.base[j];return h('td',{class:'cv',style:`background:${divShade(dpp)};color:${Math.abs(dpp)>18?'#fff':css('--ink')}`,title:`${rlab} reported: ${c} also reported in ${x[2]}% (${count(x[3])} records). Overall: ${d.base[j]}%.${lift>=1.3?' Clearly more often together.':lift<=.75?' Clearly less often together.':''}`},`${x[2]}%`)}))) });
    pan.append(h('div',{class:'covlegend',style:'margin-bottom:10px'},h('span',{},'Less often than usual'),h('i',{style:`background:linear-gradient(90deg,${divShade(-25)},${divShade(0)},${divShade(25)})`}),h('span',{},'More often than usual')));
    pan.append(h('div',{class:'tablewrap covwrap'},h('table',{class:'cov'},h('thead',{},h('tr',{},h('th',{class:'sticky'},'Records that report…'),d.cols.map((c,j)=>h('th',{class:'colh'},h('div',{},c),h('div',{class:'kind'},`${d.base[j]}% overall`))))),tb)));
    p.append(pan)}
  else{const d=await api('/api/correlation');const pan=h('section',{class:'panel'},h('h2',{},'Do numeric fields rise and fall together?'),h('p',{class:'sub'},'Spearman rank correlation, from −1 (one rises as the other falls) to 1 (they rise together), for pairs with at least 30 shared values. Values near 0 mean no relationship. The data comes from many sources, so these are associations, not causes.'));
    if(d.top?.length)pan.append(h('h3',{style:'margin:4px 0 8px'},'Strongest pairs'),h('div',{class:'pairs'},d.top.map(t=>h('div',{class:'pair'},h('b',{},fmt(t.rho,2)),h('span',{},`${t.a} and ${t.b}`),h('span',{class:'kind'},`${Math.abs(t.rho)>=.5?'Strong':Math.abs(t.rho)>=.3?'Moderate':'Weak'}, ${count(t.n)} records${t.mixed?', units may be mixed':''}`)))),h('h3',{style:'margin:18px 0 4px'},'All pairs'));
    const c=h('div',{class:'chart',style:'height:560px'});pan.append(c);p.append(pan);heatDiv(c,d.cols,d.cells,-1,0,1,v=>fmt(v,2),'ρ')}
};
function heatDiv(el,cols,cells,lo,mid,hi,f,name){
  chart(el,{grid:{left:170,right:20,top:120,bottom:50},tooltip:{...tt(),formatter:i=>`${esc(cols[i.value[1]])}<br>${esc(cols[i.value[0]])}<br><b>${name}: ${f(i.value[2])}</b> (${count(i.value[3])} records)`},
    xAxis:{type:'category',position:'top',data:cols,axisLabel:{color:css('--ink-2'),rotate:38,interval:0,width:130,overflow:'truncate',fontSize:12},axisLine:{show:false},axisTick:{show:false}},
    yAxis:{type:'category',inverse:true,data:cols,axisLabel:{color:css('--ink'),width:155,overflow:'truncate',fontSize:12.5},axisLine:{show:false},axisTick:{show:false}},
    visualMap:{dimension:2,min:lo,max:hi,orient:'horizontal',left:170,bottom:0,itemWidth:12,itemHeight:170,text:[String(hi),String(lo)],textStyle:{color:css('--ink-2')},inRange:{color:[css('--div-neg'),css('--div-mid'),css('--div-pos')]}},
    series:[{type:'heatmap',data:cells,label:{show:cols.length<=12,fontSize:11,color:css('--ink'),formatter:i=>f(i.value[2])},itemStyle:{borderColor:css('--surface'),borderWidth:2,borderRadius:2}}]});
}

Views.samples=async p=>{
  const d=await api('/api/sample',{__nofilter:1});
  p.append(head(`${d.n} sample records`,S.src==='mine'?'A selection from your file, spread across its groups. Filters do not change it.':'A fixed selection across drug classes that shows what the data looks like. Filters do not change it. Source details and trial numbers are not included.'));
  p.append(h('div',{class:'notice'},'The selection favours fuller records in each group, so empty fields are far more common in the full data. For real rates, see Overview and Data dictionary.'));
  const tb=h('tbody');let g=null;
  d.rows.forEach(r=>{if(r.group!==g){g=r.group;tb.append(h('tr',{class:'grp'},h('td',{colspan:d.columns.length},g)))}
    tb.append(h('tr',{},d.columns.map(c=>{const v=r.values[c.key];return h('td',{class:c.unit?'num':'',title:v==null?'':String(v)},v==null?h('span',{class:'miss'},'empty'):typeof v==='number'?fmt(v):v)})))});
  p.append(h('div',{class:'tablewrap',style:'max-height:74vh'},h('table',{},h('thead',{},h('tr',{},d.columns.map(c=>h('th',{class:c.unit?'num':''},c.label+(c.unit&&c.unit!=='patients'?` (${c.unit})`:''))))),tb)));
};

Views.mydata=async p=>{
  const st=await api('/api/meta',{__nofilter:1,__project:1});
  // On hosted platforms this request may reach a server copy that never saw the file; the tab's own copy counts too.
  const mine=st.mine||(S.myFile?{status:'ready',name:S.myFile.name}:null);
  p.append(head('Explore your own file','Upload your own CSV to explore it with the same views as the project data: overview, profiles, distributions, clusters and more.'));
  const pan=h('section',{class:'panel'});p.append(pan);
  const err=h('p',{class:'err',role:'alert'});
  const file=h('input',{type:'file',accept:'.csv,.tsv,.txt','aria-label':'CSV file'});
  const go=h('button',{class:'btn'},mine?'Replace with this file':'Upload and analyze');
  go.onclick=async()=>{err.textContent='';if(!file.files[0]){err.textContent='Choose a CSV file first.';return}go.disabled=true;go.textContent='Analyzing…';
    try{await sendMine(file.files[0])}catch(e){err.textContent=e.message;go.disabled=false;go.textContent='Upload and analyze';return}
    S.view={};S.meta.mine=(await api('/api/meta',{__nofilter:1,__project:1})).mine||{status:'ready',name:file.files[0].name};route()};
  if(mine){
    const STM={building:'Reading the file…',mapping:`Ready to explore. The cluster map is still being built${mine.progress?': '+mine.progress:''}.`,ready:'Ready to explore.',error:`This file could not be used: ${mine.error||'unknown error'}`};
    pan.append(...[h('h2',{},mine.name),h('p',{class:mine.status==='error'?'err':'sub'},STM[mine.status]||mine.status),mine.rows?h('div',{class:'facts',style:'margin:10px 0 14px'},h('div',{},h('b',{},fmt(mine.rows,0)),h('span',{},'rows')),h('div',{},h('b',{},fmt(mine.cols,0)),h('span',{},'columns'))):null,
      mine.map_note?h('p',{class:'sub'},mine.map_note):null,
      h('div',{class:'formrow'},['mapping','ready'].includes(mine.status)?h('button',{class:'btn',onclick:()=>switchSource('mine')},S.src==='mine'?'Back to the overview':'Explore my data'):null,
        h('button',{class:'btn ghost',onclick:async()=>{await fetch('/api/mydata',{method:'DELETE'});S.myFile=null;S.myPacked=null;if(S.src==='mine'){S.src='project';S.filters={};S.view={};}S.meta=await api('/api/meta',{__nofilter:1});$('#dsname').textContent=S.meta.name||'';renderFilters();route()}},'Remove my file'))].filter(Boolean));
    if(['building','mapping'].includes(mine.status)){const was=mine.status+mine.progress;const tick=async()=>{if(S.page!=='mydata')return;const n=await api('/api/meta',{__nofilter:1,__project:1});const now=n.mine?n.mine.status+n.mine.progress:'';if(now!==was){S.meta.mine=n.mine;route()}else setTimeout(tick,4000)};setTimeout(tick,4000)}
    pan.append(h('h3',{style:'margin-top:22px'},'Upload a different file'));
  }
  pan.append(h('div',{class:'formrow',style:'margin-top:8px'},file,go),err);
  p.append(h('section',{class:'rules'},[
    ['Only you can see it','Your file is tied to this sign-in. Other people using Nanoskop cannot see or reach it.'],
    st.hosted?['Not stored','Your file stays in this browser tab and is sent to the server only to be analyzed. It is not saved. If you reload the page, upload it again.']:['Not saved to disk','It is kept in the server’s memory and removed when you sign out, when you remove it, or after 12 hours without use.'],
    ['Full detail','Because it is your own data, small groups and exact counts are shown. The project data keeps its protections.'],
    ['What works best',`A CSV with one row per record${st.hosted?'. Files are compressed before sending, so most CSVs up to about 15 MB fit':`, up to ${st.my_max_mb} MB and 200,000 rows`}. Text columns with a few repeated values become filters. If your file uses the project’s columns (drug_name, api_norm and so on), you also get the drug views.`]].map(([a,b])=>h('div',{},h('h3',{},a),h('p',{},b)))));
};

/* ---------- Routing ---------- */
let renderToken=0;
async function route(){
  S.page=(location.hash||'#overview').slice(1);if(!PAGES.some(([k])=>k===S.page)&&!HIDDEN_PAGES.includes(S.page))S.page='overview';
  renderNav();disposeCharts();$('#drawer').replaceChildren();const page=$('#page');page.replaceChildren();page.setAttribute('aria-busy','true');
  const my=++renderToken;const box=h('div',{style:'display:contents'});page.append(box);
  if(S.src==='mine'&&S.page!=='mydata')box.append(h('div',{class:'srcbar'},h('span',{},'You are viewing your own file',(S.meta.mine||S.myFile)?h('b',{},` ${(S.meta.mine||S.myFile).name}`):null,'.'),h('button',{class:'link',onclick:()=>switchSource('project')},'Back to project data')));
  if(!S.meta.n&&S.page!=='mydata'){box.append(h('div',{class:'panel empty'},S.src==='mine'?(S.meta.status==='error'?`Your file could not be used: ${S.meta.error||''}`:'Your file is still being read.'):S.meta.status==='building'?'The data is being prepared.':S.meta.role==='admin'?'No data yet. Upload a CSV from the admin page.':'No project data has been uploaded yet.'));page.removeAttribute('aria-busy');return}
  try{await Views[S.page](box)}catch(e){if(my===renderToken&&e.message!=='401'){box.append(h('div',{class:'notice',role:'status'},e.message));}}
  page.removeAttribute('aria-busy');window.scrollTo(0,0);
}
async function boot(){
  const stored=(()=>{try{return localStorage.getItem('nanoskop-theme')}catch{return null}})();
  if(stored)document.documentElement.dataset.theme=stored;
  const isDark=()=>document.documentElement.dataset.theme?document.documentElement.dataset.theme==='dark':matchMedia('(prefers-color-scheme:dark)').matches;
  const tb=$('#theme');const lab=()=>tb.textContent=isDark()?'Switch to light theme':'Switch to dark theme';lab();
  tb.onclick=()=>{const v=isDark()?'light':'dark';document.documentElement.dataset.theme=v;try{localStorage.setItem('nanoskop-theme',v)}catch{}lab();route()};
  $('#logout').onclick=async()=>{await fetch('/api/logout',{method:'POST'});location.href='/login'};
  S.meta=await api('/api/meta',{__nofilter:1});
  if(S.meta.role==='admin')$('#adminlink').hidden=false;
  $('#dsname').textContent=S.meta.name||'';
  renderFilters();window.addEventListener('hashchange',route);await route();
  if(S.meta.status!=='ready')poll();
}
function poll(){const src=S.src;setTimeout(async()=>{if(S.src!==src)return;const m=await api('/api/meta',{__nofilter:1});const f=$('#fstatus');if(m.status==='ready'||m.status==='error'){const was=!S.meta.n;S.meta=m;if(f)f.textContent='';if(was)renderFilters();if(S.page!=='mydata')route()}else{if(m.n&&!S.meta.n){S.meta=m;renderFilters();route()}if(f)f.textContent=m.n?`Preparing the cluster map: ${m.progress||''}`:'Reading the data…';poll()}},5000)}
boot();
