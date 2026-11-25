'use strict';
const $=s=>document.querySelector(s);const T=(s)=>{const d=document.createElement('template');d.innerHTML=s;return d.content};const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
async function J(u,o={}){const r=await fetch(u,o);const j=await r.json().catch(()=>({}));if(!r.ok)throw new Error(j.detail||'The request could not be completed.');return j}
const put=b=>J('/admin/api/config',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)});
let cfg;
async function load(){cfg=await J('/admin/api/config');
 if(cfg.readonly&&!document.getElementById('ro')){document.querySelectorAll('#up,#pv,#cd,#smsave,#smnew,#colsave').forEach(e=>e.style.display='none');document.querySelectorAll('#cols select,#smen,#sample_n').forEach(e=>e.disabled=true);const n=document.createElement('p');n.id='ro';n.className='notice';n.textContent='This is the hosted version. Data and settings are fixed in the deployment: change the access codes and thresholds in the hosting dashboard (environment variables), and update the data with prepare.py and a new deployment.';document.querySelector('.adminwrap').insertBefore(n,document.querySelector('.adminwrap').children[1])}
 const STM={empty:'No data has been uploaded yet.',building:'Reading the CSV.',mapping:`Summaries are ready. Preparing the cluster map: ${cfg.progress||''}`,ready:`Ready: ${cfg.rows.toLocaleString('en-US')} records, ${cfg.columns.length} fields.`,error:`Error: ${cfg.error||''}`};
 $('#st').textContent=STM[cfg.status]||cfg.status;if(cfg.name)$('#nm').value=cfg.name;
 ['k','min_cohort','round_to','num_min','sample_n'].forEach(k=>{const e=$('#'+k);if(document.activeElement!==e)e.value=cfg[k]});$('#smen').checked=cfg.sample_enabled;
 $('#smst').textContent=cfg.sample?`Currently ${cfg.sample.n} real records across ${new Set(cfg.sample.rows.map(r=>r.group)).size} groups (drawn ${cfg.sample.drawn_at}). Review them before sharing access.`:'No sample has been drawn yet.';
 if(cfg.sample){const c=cfg.sample.columns;$('#smprev').innerHTML=`<table><thead><tr><th>Group</th>${c.map(x=>`<th>${esc(x.label)}</th>`).join('')}</tr></thead><tbody>${cfg.sample.rows.map(r=>`<tr><td>${esc(r.group)}</td>${c.map(x=>`<td>${esc(r.values[x.key]??'')}</td>`).join('')}</tr>`).join('')}</tbody></table>`}
 $('#cols').innerHTML=`<table><thead><tr><th>Field</th><th>Type</th><th>Group</th><th>Filled</th><th>Visibility</th></tr></thead><tbody>${cfg.columns.map(c=>`<tr><td>${esc(c.name)}</td><td>${esc(c.kind)}</td><td>${esc(c.group)}</td><td>${c.fill}</td><td><select data-c="${esc(c.name)}">${[['full','Full'],['stats','Fill rate only'],['hidden','Hidden']].map(([v,l])=>`<option value="${v}" ${c.mode===v?'selected':''}>${l}</option>`).join('')}</select></td></tr>`).join('')}</tbody></table>`;
 const l=await J('/admin/api/log');$('#log').innerHTML=`<table><thead><tr><th>Time</th><th>Role</th><th>Session</th><th>Address</th><th>Page</th><th>Query</th></tr></thead><tbody>${l.rows.slice(0,200).map(r=>`<tr><td>${esc(r.t)}</td><td>${esc(r.role)}</td><td>${esc(r.sid)}</td><td>${esc(r.ip)}</td><td>${esc(r.path)}</td><td>${esc(decodeURIComponent(r.q||''))}</td></tr>`).join('')}</tbody></table>`;
 if(['building','mapping'].includes(cfg.status))setTimeout(load,5000);
}
$('#up').addEventListener('submit',async e=>{e.preventDefault();$('#uerr').textContent='';const f=new FormData();f.append('file',$('#fl').files[0]);f.append('name',$('#nm').value);try{await J('/admin/api/upload',{method:'POST',body:f});load()}catch(x){$('#uerr').textContent=x.message}});
$('#pv').addEventListener('submit',async e=>{e.preventDefault();await put({k:+$('#k').value,min_cohort:+$('#min_cohort').value,round_to:+$('#round_to').value,num_min:+$('#num_min').value});load()});
$('#smsave').onclick=async()=>{await put({sample_enabled:$('#smen').checked,sample_n:+$('#sample_n').value});load()};
$('#smnew').onclick=async()=>{await put({sample_n:+$('#sample_n').value});await J('/admin/api/resample',{method:'POST'});load()};
$('#colsave').onclick=async()=>{const m={};document.querySelectorAll('#cols select').forEach(s=>{m[s.dataset.c]=s.value});await put({column_modes:m});load()};
$('#cd').addEventListener('submit',async e=>{e.preventDefault();$('#cerr').textContent='';try{await J('/admin/api/codes',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({viewer:$('#vc').value||null,admin:$('#ac').value||null})});location.href='/login?admin'}catch(x){$('#cerr').textContent=x.message}});
load();
