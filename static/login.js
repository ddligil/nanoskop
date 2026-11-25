document.getElementById('f').addEventListener('submit',async ev=>{ev.preventDefault();const e=document.getElementById('e');e.textContent='';
const r=await fetch('/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({code:document.getElementById('c').value})});
if(r.ok){const j=await r.json();location.href=j.role==='admin'&&new URLSearchParams(location.search).has('admin')?'/admin':'/'}else{const j=await r.json().catch(()=>({}));e.textContent=j.detail||'Could not sign in.'}});
