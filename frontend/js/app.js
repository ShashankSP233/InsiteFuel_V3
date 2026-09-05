'use strict';

// ── State ──────────────────────────────────────────────────────────────────
let me=null, master=null, currentDetails=null;
let chartJs=null, chartInstances={};
let logsPage=1, logsTotal=0, logsLimit=100;

// ── Helpers ────────────────────────────────────────────────────────────────
const $=id=>document.getElementById(id);
const today=()=>new Date().toISOString().slice(0,10);
const firstOfMonth=()=>new Date(new Date().getFullYear(),new Date().getMonth(),1).toISOString().slice(0,10);
const fmt=(n,d=1)=>n!=null&&Number.isFinite(+n)?(+n).toFixed(d):'—';
const fmtInt=n=>n!=null&&Number.isFinite(+n)?Math.round(+n).toLocaleString():'—';

// DD-MM-YYYY display
function fmtDate(isoDate){
  if(!isoDate)return '';
  const[y,m,d]=isoDate.split('-');
  return `${d}-${m}-${y}`;
}

async function api(url,opts={}){
  const o={...opts};
  if(!(o.body instanceof FormData)) o.headers={'Content-Type':'application/json',...(o.headers||{})};
  const r=  await fetch(url,{...o,cache:'no-store'});
  if(r.status===401){
    me=null;
    $('appWrap').classList.add('hidden');
    $('loginWrap').classList.remove('hidden');
    showMsg('loginMsg','<span style="color:var(--yellow)">⚠️ Session expired. Please sign in again.</span>','warn');
    throw new Error('Session expired');
  }
  const data=await r.json().catch(()=>({error:r.statusText}));
  if(!r.ok) throw new Error(data.error||'Request failed');
  return data;
}

function fill(id,arr,sub='',blank=false,label='name'){
  const s=$(id);if(!s)return;
  s.innerHTML=blank?'<option value="">— None —</option>':'';
  arr.forEach(x=>s.innerHTML+=`<option value="${x.id}">${x[label]}${sub&&x[sub]?' – '+x[sub]:''}</option>`);
}
function showMsg(id,html,type='info'){
  const el=$(id);if(!el)return;
  const cls=type==='ok'?' note-ok':type==='err'?' note-err':type==='warn'?' note-warn':'';
  el.innerHTML=`<div class="note${cls}">${html}</div>`;
}
function clearMsg(id){const el=$(id);if(el)el.innerHTML='';}

// ── Chart.js loader ────────────────────────────────────────────────────────
function loadChartJs(){
  return new Promise((resolve,reject)=>{
    if(typeof Chart!=='undefined'){chartJs=Chart;return resolve();}
    const s=document.createElement('script');
    s.src='/js/chart.umd.js';
    s.onload=()=>{if(typeof Chart!=='undefined'){chartJs=Chart;resolve();}else reject(new Error('Chart.js failed to load'));};
    s.onerror=()=>reject(new Error('Chart.js file not found. Run npm install and restart.'));
    document.head.appendChild(s);
  });
}

// ── Vessel checkbox builder ────────────────────────────────────────────────
function buildVesselCheckboxes(containerId, vessels, allChecked=false){
  const el=$(containerId);if(!el)return;
  // Group by project
  const groups={};
  vessels.forEach(v=>{
    if(!groups[v.project_name])groups[v.project_name]=[];
    groups[v.project_name].push(v);
  });
  el.innerHTML=Object.entries(groups).map(([proj,vs])=>`
    <div class="check-group-label">${proj}</div>
    ${vs.map(v=>`<label>
      <input type="checkbox" value="${v.id}" class="vessel-cb-${containerId}" ${allChecked?'checked':''}>
      ${v.name}
    </label>`).join('')}
  `).join('');
}

function getCheckedVessels(containerId){
  return [...document.querySelectorAll(`.vessel-cb-${containerId}:checked`)].map(cb=>cb.value).join(',');
}

// ── Login / Init ───────────────────────────────────────────────────────────
async function login(){
  try{
    await api('/api/auth/login',{method:'POST',body:JSON.stringify({username:$('loginUser').value,password:$('loginPass').value})});
    await init();
  }catch(e){showMsg('loginMsg',e.message,'err');}
}
async function logout(){await api('/api/auth/logout',{method:'POST'});location.reload();}

async function init(){
  const r=await api('/api/auth/me');
  me=r;
  if(!me){$('loginWrap').classList.remove('hidden');$('appWrap').classList.add('hidden');return;}
  $('loginWrap').classList.add('hidden');$('appWrap').classList.remove('hidden');
  $('userChip').innerHTML=`<b>${me.username}</b>&nbsp;·&nbsp;${me.role}`;
  document.querySelectorAll('.manager-only').forEach(el=>el.style.display=me.role==='operator'?'none':'');
  document.querySelectorAll('.admin-only').forEach(el=>el.style.display=me.role==='admin'?'':'none');
  await loadMaster();
  const t=today(),fm=firstOfMonth();
  $('date').value=t;updateDateDisplay();
  $('prodDate').value=t;
  $('dashFrom').value=fm;$('dashTo').value=t;
  $('hoFrom').value=fm;$('hoTo').value=t;
  $('chartFrom').value=fm;$('chartTo').value=t;
  $('effFrom').value=fm;$('effTo').value=t;
  await onDateVesselChange();
  if(me.role!=='operator'){await loadLogs();await loadMissingSoundings();await loadComparison();await checkAlertBell();}
}

function updateDateDisplay(){
  const el=$('dateFmt');const d=$('date').value;
  if(el&&d)el.textContent=fmtDate(d);
}

// ── Tabs ───────────────────────────────────────────────────────────────────
function showTab(id,btn){
  document.querySelectorAll('.tabPage').forEach(x=>x.classList.add('hidden'));
  $(id).classList.remove('hidden');
  document.querySelectorAll('.tab-btn').forEach(x=>x.classList.remove('active'));
  if(btn)btn.classList.add('active');
  if(id==='dashboard'){loadLogs();loadMissingSoundings();loadComparison();}
  if(id==='audit')    loadAudit();
  if(id==='users')    loadUsers();
  if(id==='hoSummary')loadHoSummary();
  if(id==='charts')   {/* user clicks Load Charts manually */}
  if(id==='efficiency')loadEfficiency();
  if(id==='masters')  loadMasterTab();
}

// ── Master data ────────────────────────────────────────────────────────────
async function loadMaster(){
  master=await api('/api/master-data');
  fill('prodProject',master.projects);
  fill('newVesselProject',master.projects);
  fill('linkVessel',master.vessels,'project_name');
  fill('linkEquipment',master.equipment);
  syncProdVessels();
  // Operator vessel dropdown — only vessels in operator's project
  const opVessels=me.role==='admin'?master.vessels:master.vessels.filter(v=>String(v.project_id)===String(me.project_id));
  fill('vessel',opVessels,'vessel_type');
  fill('toVessel',master.vessels,'project_name',true);
  // Build vessel checkboxes for Dashboard, HO, Charts
  buildVesselCheckboxes('dashVesselChecks',master.vessels,true);
  buildVesselCheckboxes('hoVesselChecks',master.vessels,true);
  buildVesselCheckboxes('chartVesselChecks',master.vessels,false);
}

function syncProdVessels(){const pid=$('prodProject').value||master.projects[0]?.id;fill('prodVessel',master.vessels.filter(v=>String(v.project_id)===String(pid)),'vessel_type');}

// ── Vessel equipment ───────────────────────────────────────────────────────
async function loadVesselEquipmentForStock(vesselId){
  if(!vesselId){$('equipmentSelect').innerHTML='<option value="">— Select Equipment —</option>';return;}
  try{
    const rows=await api(`/api/equipment/vessel/${vesselId}`);
    const sel=$('equipmentSelect');
    sel.innerHTML='<option value="">— Select Equipment —</option>';
    rows.forEach(e=>sel.innerHTML+=`<option value="${e.id}" data-type="${e.engine_type}">${e.name} (${e.engine_type})</option>`);
  }catch(e){console.warn(e);}
}
function onEquipmentChange(){
  const sel=$('equipmentSelect');
  const opt=sel.options[sel.selectedIndex];
  // Store engine type silently — no display needed
  sel.dataset.engineType=opt?.dataset?.type||'';
}

// ── Alert bell ─────────────────────────────────────────────────────────────
async function checkAlertBell(){
  try{
    const rows=await api(`/api/dashboard/missing-soundings?date=${today()}`);
    const missing=rows.filter(r=>r.missing).length;
    const bell=$('alertBell');
    if(bell){bell.classList.toggle('hidden',missing===0);bell.title=`${missing} vessel(s) missing sounding`;}
    const banners=[];
    if(missing>0)banners.push(`<div class="note note-warn">🔔 <b>${missing} vessel(s)</b> missing sounding photo for today.</div>`);
    $('opAlerts').innerHTML=banners.join('');
  }catch(e){}
}
async function sendSoundingAlert(){
  try{await api('/api/admin/send-sounding-alert',{method:'POST'});showMsg('stockMsg','<span class="pill pill-ok">Alert sent</span>','ok');}
  catch(e){alert(e.message);}
}

// ── Engine form reset ──────────────────────────────────────────────────────
function resetEngineForm(){
  const sel=$('equipmentSelect');if(sel){sel.value='';sel.dataset.engineType='';}
  $('startTime').value='';$('stopTime').value='';
  $('consumption').value=0;$('engineRemarks').value='';
  clearMsg('engineMsg');
}

// ── Stock entry ────────────────────────────────────────────────────────────
async function onDateVesselChange(){
  updateDateDisplay();
  try{
    const vesselId=$('vessel').value;
    if(!$('date').value||!vesselId)return;
    await loadVesselEquipmentForStock(vesselId);
    const shift=$('shift').value;
    const ex=await api(`/api/stock/find?date=${$('date').value}&vessel_id=${vesselId}&shift=${shift}`);
    if(ex.stock){
      $('stockId').value=ex.stock.id;$('opening').value=ex.stock.opening_balance;
      $('received').value=ex.stock.received_fuel;$('fuelSource').value=ex.stock.fuel_source||'';
      showMsg('stockMsg',`<span class="pill pill-info">Existing ${ex.stock.shift} shift stock loaded — ID ${ex.stock.id}</span>`,'info');
      resetEngineForm();await loadDetails(ex.stock.id);return;
    }
    const r=await api(`/api/previous-closing?date=${$('date').value}&vessel_id=${vesselId}&shift=${shift}`);
    $('opening').value=r.opening_suggestion||0;$('received').value=0;$('fuelSource').value='';
    $('stockId').value='';$('details').innerHTML='';resetEngineForm();
    showMsg('stockMsg',r.previous_date
      ?`Opening: <b>${r.opening_suggestion} L</b> — ${r.note}`
      :'No previous closing — enter opening balance manually.','info');
  }catch(e){if(e.message!=='Session expired')console.warn(e);}
}

async function createOrLoadStock(){
  try{
    const r=await api('/api/stock',{method:'POST',body:JSON.stringify({
      date:$('date').value,shift:$('shift').value,vessel_id:$('vessel').value,
      opening_balance:+$('opening').value,received_fuel:+$('received').value,
      fuel_source:$('fuelSource').value
    })});
    $('stockId').value=r.stock_id;
    showMsg('stockMsg',r.existing?`<span class="pill pill-warn">${r.warning}</span>`:`<span class="pill pill-ok">Stock created — ID ${r.stock_id}</span>`,'ok');
    resetEngineForm();await loadDetails(r.stock_id);
    if(me.role!=='operator')loadLogs();
  }catch(e){showMsg('stockMsg',e.message,'err');}
}

function refreshDetails(){const sid=$('stockId').value;if(sid)loadDetails(sid);}

async function addEngineEvent(){
  const sid=$('stockId').value;
  if(!sid)return showMsg('engineMsg','Create or load daily stock first','err');
  const sel=$('equipmentSelect');
  const equipment_id=sel.value||null;
  const engine_type=sel.dataset.engineType||sel.options[sel.selectedIndex]?.dataset?.type||'';
  if(!engine_type)return showMsg('engineMsg','Select equipment first','err');
  try{
    const r=await api('/api/engine-events',{method:'POST',body:JSON.stringify({
      stock_id:sid,equipment_id,engine_type,
      start_time:$('startTime').value,stop_time:$('stopTime').value,
      consumption:+$('consumption').value,remarks:$('engineRemarks').value
    })});
    showMsg('engineMsg',r.warnings?.length
      ?`<span class="pill pill-warn">Saved with warning: ${r.warnings.join(', ')} · ${fmt(r.lhr,1)} L/hr</span>`
      :`<span class="pill pill-ok">Saved — ${fmt(r.hours,2)} hrs · ${fmt(r.lhr,1)} L/hr</span>`,'ok');
    resetEngineForm();await loadDetails(sid);
    if(me.role!=='operator')loadLogs();
  }catch(e){showMsg('engineMsg',e.message,'err');}
}

async function addTransfer(){
  const sid=$('stockId').value;
  if(!sid)return showMsg('transferMsg','Create or load daily stock first','err');
  try{
    const tr=await api('/api/transfers',{method:'POST',body:JSON.stringify({
      from_vessel_id: currentDetails.stock.vessel_id,
      to_vessel_id: $('toVessel').value,
      quantity: +$('transferQty').value,
      date: $('date').value,
      notes: $('transferRemarks').value
    })});
    if(tr.warning){
      showMsg('transferMsg',`<div class="note note-ok" style="margin-bottom:6px">✅ Transfer recorded — receiving vessel operator alerted</div><div class="note note-warn">⚠️ ${tr.warning}</div>`,'ok');
    }else{showMsg('transferMsg','<span class="pill pill-ok">Transfer recorded</span>','ok');}
    $('transferQty').value=0;$('transferRemarks').value='';
    await loadDetails(sid);if(me.role!=='operator')loadLogs();
  }catch(e){showMsg('transferMsg',e.message,'err');}
}

async function uploadFile(type,inputId){
  const sid=$('stockId').value;
  if(!sid)return alert('Create or load stock first');
  const f=$(inputId).files[0];if(!f)return alert('Select a file first');
  const fd=new FormData();fd.append('file',f);
  if(type==='bill'){const bn=$('billNumber').value;if(bn)fd.append('bill_number',bn);}
  try{
    const r=await fetch(`/api/attachments/${sid}/${type}`,{method:'POST',body:fd});
    if(!r.ok)throw new Error((await r.json()).error);
    $(inputId).value='';if(type==='bill')$('billNumber').value='';
    await loadDetails(sid);
    if(me.role!=='operator'){loadMissingSoundings();checkAlertBell();}
  }catch(e){alert(e.message);}
}

async function submitStock(){
  const sid=$('stockId').value;if(!sid)return alert('Create or load stock first');
  if(!confirm('Submit this shift for manager review?'))return;
  try{await api(`/api/stock/${sid}/submit`,{method:'POST'});await loadDetails(sid);showMsg('stockMsg','<span class="pill pill-submit">Shift submitted</span>','ok');}
  catch(e){alert(e.message);}
}
async function unlockStock(sid){
  if(!confirm('Unlock for editing?'))return;
  try{await api(`/api/stock/${sid}/unlock`,{method:'POST'});await loadDetails(sid);}catch(e){alert(e.message);}
}

// ── Manager: edit received fuel ────────────────────────────────────────────
function openEditReceivedModal(stockId,currentVal,currentSource){
  const ov=document.createElement('div');ov.className='modal-overlay';ov.id='editRcvModal';
  ov.innerHTML=`<div class="modal">
    <div class="modal-title">Edit Received Fuel — Stock ID ${stockId}</div>
    <div class="note note-warn" style="margin-bottom:12px">A comment is required for audit trail.</div>
    <div class="grid">
      <div><label>Received Fuel (L)</label><input type="number" id="rcvQty" step="0.01" value="${currentVal||0}"></div>
      <div><label>Source of Fuel</label><input id="rcvSource" value="${currentSource||''}"></div>
    </div>
    <div class="mt8"><label>Comment / Reason for Edit *</label><input id="rcvComment" placeholder="e.g. Correcting typo error — actual received was 850L"></div>
    <div id="rcvMsg" class="mt8"></div>
    <div class="flex mt12">
      <button class="btn btn-primary" onclick="saveEditReceived(${stockId})">Save Changes</button>
      <button class="btn btn-ghost" onclick="closeModal('editRcvModal')">Cancel</button>
    </div>
  </div>`;
  document.body.appendChild(ov);ov.addEventListener('click',ev=>{if(ev.target===ov)closeModal('editRcvModal');});
}

async function saveEditReceived(stockId){
  const comment=$('rcvComment').value;
  if(!comment.trim())return showMsg('rcvMsg','Comment is required','err');
  try{
    await api(`/api/stock/${stockId}/received`,{method:'PUT',body:JSON.stringify({
      received_fuel:+$('rcvQty').value,fuel_source:$('rcvSource').value,comment
    })});
    closeModal('editRcvModal');
    await loadDetails(stockId);
    if(currentDetails)$('correctionDetails').innerHTML=renderDetails(currentDetails);
    loadLogs();
  }catch(e){showMsg('rcvMsg',e.message,'err');}
}

// ── Details render ─────────────────────────────────────────────────────────
async function loadDetails(id){
  currentDetails=await api(`/api/stock/${id}`);
  const el=$('details')||$('correctionDetails');
  if($('details'))$('details').innerHTML=renderDetails(currentDetails);
  // Alerts
  const st=currentDetails.stock;
  const alerts=[];
  if(st.closing_balance<0)
    alerts.push(`<div class="note note-err">🚨 <b>Negative closing balance: ${fmt(st.closing_balance,1)} L</b></div>`);
  else if(st.fuel_threshold_litres>0&&st.closing_balance<=st.fuel_threshold_litres)
    alerts.push(`<div class="note note-warn">⚠️ <b>Low Fuel: ${fmt(st.closing_balance,1)} L</b> — Below threshold of ${st.fuel_threshold_litres} L</div>`);
  const opAlerts=$('opAlerts');
  if(opAlerts){const existing=opAlerts.innerHTML;opAlerts.innerHTML=existing+alerts.join('');}
}

function isManager(){return me&&['manager','admin'].includes(me.role);}

function renderDetails(d){
  const st=d.stock;
  const sums={ME:{h:0,c:0},AUX:{h:0,c:0},DG:{h:0,c:0}};
  d.events.forEach(e=>{sums[e.engine_type].h+=+e.running_hours;sums[e.engine_type].c+=+e.consumption;});
  const transOut=d.transfers.filter(t=>t.direction!=='in').reduce((a,t)=>a+ +t.quantity,0);
  const totalOut=sums.ME.c+sums.AUX.c+sums.DG.c+transOut;
  const submitted=st.submit_status==='SUBMITTED';
  const isNeg=st.closing_balance<0;
  const isLow=st.fuel_threshold_litres>0&&st.closing_balance<=st.fuel_threshold_litres&&st.closing_balance>=0;
  const canEdit=!submitted||isManager();

  const submitBar=submitted
    ?`<div class="submit-banner submitted"><span>🔒 ${st.shift} Shift submitted — ${fmtDate(st.submitted_at?.slice(0,10)||'')}</span>${isManager()?`<button class="btn btn-ghost btn-sm" onclick="unlockStock(${st.id})">Unlock</button>`:''}</div>`
    :`<div class="submit-banner open"><span>✏️ ${st.shift} Shift — Open</span><button class="btn btn-primary btn-sm" onclick="submitStock()">Submit Shift</button></div>`;

  const rcvRow=isManager()
    ?`<button class="btn btn-warn btn-sm" style="margin-left:8px" onclick="openEditReceivedModal(${st.id},${st.received_fuel},'${(st.fuel_source||'').replace(/'/g,"\\'")}')">Edit</button>`:'';

  return`${submitBar}
  <div class="stat-row">
    <div class="stat-block ${isNeg?'red':isLow?'':'green'}">
      <div class="stat-label">Closing</div>
      <div class="stat-val" ${isNeg?'style="color:var(--red)"':''}>${fmt(st.closing_balance)} L</div>
      ${isNeg?'<div class="muted" style="color:var(--red)">⚠ NEGATIVE</div>':isLow?`<div class="muted" style="color:var(--yellow)">⚠ LOW (thr: ${st.fuel_threshold_litres}L)</div>`:''}
    </div>
    <div class="stat-block"><div class="stat-label">Opening</div><div class="stat-val">${fmt(st.opening_balance)} L</div></div>
    <div class="stat-block"><div class="stat-label">Received ${rcvRow}</div><div class="stat-val">${fmt(st.received_fuel)} L</div><div class="muted">${st.fuel_source||''}</div></div>
    <div class="stat-block"><div class="stat-label">ME</div><div class="stat-val">${fmt(sums.ME.c)} L</div><div class="muted">${sums.ME.h>0?fmt(sums.ME.c/sums.ME.h,1)+' L/hr':''}</div></div>
    <div class="stat-block"><div class="stat-label">AUX</div><div class="stat-val">${fmt(sums.AUX.c)} L</div><div class="muted">${sums.AUX.h>0?fmt(sums.AUX.c/sums.AUX.h,1)+' L/hr':''}</div></div>
    <div class="stat-block"><div class="stat-label">DG</div><div class="stat-val">${fmt(sums.DG.c)} L</div><div class="muted">${sums.DG.h>0?fmt(sums.DG.c/sums.DG.h,1)+' L/hr':''}</div></div>
    <div class="stat-block"><div class="stat-label">Total Out</div><div class="stat-val">${fmt(totalOut)} L</div></div>
  </div>
  <div class="section-head mt12"><span class="dot"></span>Engine Events</div>
  <div class="table-wrap"><table>
    <thead><tr><th>Equipment</th><th>Type</th><th>Start</th><th>Stop</th><th>Hours</th><th>Litres</th><th>L/Hr</th><th>Warning</th>${canEdit?'<th>Actions</th>':''}</tr></thead>
    <tbody>${d.events.map(e=>`<tr class="${e.warning?'row-warn':''}">
      <td><b>${e.eq_name||'—'}</b></td><td class="mono">${e.engine_type}</td>
      <td class="mono">${e.start_time}</td><td class="mono">${e.stop_time}</td>
      <td class="mono">${fmt(e.running_hours,2)}</td><td class="mono">${e.consumption}</td>
      <td class="mono">${e.running_hours>0?fmt(e.consumption/e.running_hours,1):'—'}</td>
      <td>${e.warning?`<span class="pill pill-warn">${e.warning}</span>`:''}</td>
      ${canEdit?`<td><button class="btn btn-warn btn-sm" onclick="openEditEventModal(${e.id})">Edit</button>
        <button class="btn btn-danger btn-sm" onclick="deleteEvent(${e.id},${st.id})">Del</button></td>`:''}
    </tr>`).join('')||'<tr><td colspan="9" class="muted" style="padding:12px">No events yet</td></tr>'}</tbody>
  </table></div>
  <div class="section-head mt12"><span class="dot"></span>Transfers</div>
  <div class="table-wrap"><table>
    <thead><tr><th>Dir</th><th>To/From</th><th>Litres</th><th>Remarks</th>${canEdit?'<th>Del</th>':''}</tr></thead>
    <tbody>${d.transfers.map(t=>`<tr>
      <td><span class="pill ${t.direction==='in'?'pill-ok':'pill-info'}">${t.direction.toUpperCase()}</span></td>
      <td>${t.to_vessel||'—'}</td><td class="mono">${t.quantity}</td><td>${t.remarks||''}</td>
      ${canEdit?`<td>${t.direction==='out'?`<button class="btn btn-danger btn-sm" onclick="deleteTransfer(${t.id},${st.id})">Del</button>`:'—'}</td>`:''}
    </tr>`).join('')||'<tr><td colspan="5" class="muted" style="padding:12px">No transfers</td></tr>'}</tbody>
  </table></div>
  <div class="section-head mt12"><span class="dot"></span>Attachments</div>
  <div class="table-wrap"><table>
    <thead><tr><th>Type</th><th>Bill No.</th><th>File</th>${canEdit?'<th>Del</th>':''}</tr></thead>
    <tbody>${d.attachments.map(a=>`<tr>
      <td><span class="pill pill-gray">${a.attachment_type}</span></td>
      <td class="mono">${a.bill_number||'—'}</td>
      <td><a href="/uploads/${a.filename}" target="_blank" style="color:var(--accent)">${a.original_name}</a></td>
      ${canEdit?`<td><button class="btn btn-danger btn-sm" onclick="deleteAttachment(${a.id},${st.id})">Del</button></td>`:''}
    </tr>`).join('')||'<tr><td colspan="4" class="muted" style="padding:12px">No attachments — upload sounding photo!</td></tr>'}</tbody>
  </table></div>`;
}

// ── Edit event modal ───────────────────────────────────────────────────────
function openEditEventModal(id){
  const e=currentDetails?.events.find(x=>x.id===id);if(!e)return;
  const eqOptions=(master?.equipment||[]).map(eq=>`<option value="${eq.id}" data-type="${eq.engine_type}" ${e.equipment_id==eq.id?'selected':''}>${eq.name} (${eq.engine_type})</option>`).join('');
  const ov=document.createElement('div');ov.className='modal-overlay';ov.id='editModal';
  ov.innerHTML=`<div class="modal">
    <div class="modal-title">Edit Engine Event — ID ${e.id}</div>
    <div class="grid">
      <div><label>Equipment</label><select id="mEq">${eqOptions}</select></div>
      <div><label>Start Time</label><input type="time" id="mStart" value="${e.start_time}"></div>
      <div><label>Stop Time</label><input type="time" id="mStop" value="${e.stop_time}"></div>
      <div><label>Consumption (L)</label><input type="number" id="mCons" step="0.01" value="${e.consumption}"></div>
    </div>
    <div class="mt8"><label>Remarks</label><input id="mRemarks" value="${e.remarks||''}"></div>
    <div id="mMsg" class="mt8"></div>
    <div class="flex mt12">
      <button class="btn btn-primary" onclick="saveEditEvent(${e.id})">Save</button>
      <button class="btn btn-ghost" onclick="closeModal('editModal')">Cancel</button>
    </div>
  </div>`;
  document.body.appendChild(ov);ov.addEventListener('click',ev=>{if(ev.target===ov)closeModal('editModal');});
}

async function saveEditEvent(id){
  const sel=$('mEq');
  const opt=sel.options[sel.selectedIndex];
  try{
    await api(`/api/engine-events/${id}`,{method:'PUT',body:JSON.stringify({
      equipment_id:sel.value||null,
      engine_type:opt?.dataset?.type||'ME',
      start_time:$('mStart').value,stop_time:$('mStop').value,
      consumption:+$('mCons').value,remarks:$('mRemarks').value
    })});
    closeModal('editModal');await loadDetails(currentDetails.stock.id);
  }catch(e){showMsg('mMsg',e.message,'err');}
}

function closeModal(id='editModal'){const m=$(id);if(m)m.remove();}

async function deleteEvent(id,sid){if(!confirm('Delete event?'))return;try{await api(`/api/engine-events/${id}`,{method:'DELETE'});await loadDetails(sid);}catch(e){alert(e.message);}}
async function deleteTransfer(id,sid){if(!confirm('Delete transfer?'))return;try{await api(`/api/transfers/${id}`,{method:'DELETE'});await loadDetails(sid);}catch(e){alert(e.message);}}
async function deleteAttachment(id,sid){if(!confirm('Delete?'))return;try{await api(`/api/attachments/${id}`,{method:'DELETE'});await loadDetails(sid);checkAlertBell();}catch(e){alert(e.message);}}

// ── Dashboard logs ─────────────────────────────────────────────────────────
async function loadLogs(page=1){
  logsPage=page;
  const from=$('dashFrom')?.value,to=$('dashTo')?.value,shift=$('dashShift')?.value||'';
  const vessel_ids=getCheckedVessels('dashVesselChecks');
  let qs=`?page=${page}&limit=${logsLimit}`;
  if(from)qs+=`&from_date=${from}`;if(to)qs+=`&to_date=${to}`;
  if(shift)qs+=`&shift=${shift}`;if(vessel_ids)qs+=`&vessel_ids=${vessel_ids}`;
  const resp=await api('/api/stock'+qs);
  const rows=resp.data||[];logsTotal=resp.total||rows.length;
  const totalFuel=rows.reduce((a,r)=>a+(+r.fuel_only||0),0);
  const totalCost=rows.reduce((a,r)=>a+(+r.fuel_cost||0),0);
  const flagCount=rows.reduce((a,r)=>a+(r.flags?.length||0),0);
  const submitted=rows.filter(r=>r.submit_status==='SUBMITTED').length;
  $('kpis').innerHTML=`
    <div class="kpi"><div class="kpi-label">Total Fuel</div><div class="kpi-value">${fmtInt(totalFuel)} L</div></div>
    <div class="kpi"><div class="kpi-label">Total Cost</div><div class="kpi-value">₹${fmtInt(totalCost)}</div></div>
    <div class="kpi"><div class="kpi-label">Records</div><div class="kpi-value">${logsTotal}</div><div class="kpi-sub">${submitted} submitted</div></div>
    <div class="kpi"><div class="kpi-label">Flags</div><div class="kpi-value">${flagCount}</div></div>`;
  $('logsBody').innerHTML=rows.map(r=>{
    const negBal=r.closing_balance<0;
    const lowFuel=r.fuel_threshold_litres>0&&r.closing_balance<=r.fuel_threshold_litres&&r.closing_balance>=0;
    const mgrActions=isManager()?`<td>
      <button class="btn btn-warn btn-sm" onclick="openEditReceivedModal(${r.id},${r.received_fuel},'${(r.fuel_source||'').replace(/'/g,"\\'")}')">Edit Rcvd</button>
    </td>`:'<td></td>';
    return`<tr class="${negBal?'row-danger':lowFuel?'row-warn':r.flags?.length?'row-warn':''}">
      <td class="mono">${fmtDate(r.date)}<br><span class="muted">ID ${r.id}</span></td>
      <td><span class="pill ${r.shift==='DAY'?'pill-info':'pill-gray'}">${r.shift==='DAY'?'☀️':'🌙'} ${r.shift}</span></td>
      <td>${r.project_name}</td><td>${r.vessel_name}</td>
      <td class="mono">${fmt(r.opening_balance)}</td>
      <td class="mono">${fmt(r.received_fuel)}</td>
      <td class="muted" style="font-size:11px">${r.fuel_source||'—'}</td>
      <td class="mono">${fmt(r.me_consumption)}<br><span class="muted">${r.me_hours>0?fmt(r.me_consumption/r.me_hours,1)+' L/hr':'—'}</span></td>
      <td class="mono">${fmt(r.aux_consumption)}<br><span class="muted">${r.aux_hours>0?fmt(r.aux_consumption/r.aux_hours,1)+' L/hr':'—'}</span></td>
      <td class="mono">${fmt(r.dg_consumption)}<br><span class="muted">${r.dg_hours>0?fmt(r.dg_consumption/r.dg_hours,1)+' L/hr':'—'}</span></td>
      <td class="mono">${fmt(r.transfer_out)}</td>
      <td class="mono"><b>${fmt(r.total_out)}</b></td>
      <td class="mono"><b ${negBal?'style="color:var(--red)"':lowFuel?'style="color:var(--yellow)"':''}>${fmt(r.closing_balance)}</b></td>
      <td>${(r.flags||[]).map(f=>`<span class="pill ${f==='NEGATIVE_BALANCE'||f==='LOW_FUEL'?'pill-bad':'pill-warn'}">${f}</span>`).join(' ')||'<span class="pill pill-ok">OK</span>'}
          <br><span class="pill ${r.submit_status==='SUBMITTED'?'pill-submit':'pill-gray'}">${r.submit_status}</span></td>
      <td class="mono">${r.rate_as_per?fmt(r.rate_as_per,2):'—'}</td>
      ${mgrActions}
    </tr>`;
  }).join('');
  const pages=Math.ceil(logsTotal/logsLimit);
  $('logsPager').innerHTML=pages>1
    ?`<button class="btn btn-ghost btn-sm" ${page<=1?'disabled':''} onclick="loadLogs(${page-1})">← Prev</button>
       <span class="muted">Page ${page} of ${pages} (${logsTotal} records)</span>
       <button class="btn btn-ghost btn-sm" ${page>=pages?'disabled':''} onclick="loadLogs(${page+1})">Next →</button>`:'';
}

async function loadComparison(){
  const from=$('dashFrom')?.value,to=$('dashTo')?.value;
  const vessel_ids=getCheckedVessels('dashVesselChecks');
  let qs=from&&to?`?from_date=${from}&to_date=${to}`:'?';
  if(vessel_ids)qs+=`&vessel_ids=${vessel_ids}`;
  const rows=await api('/api/dashboard/comparison'+qs);
  $('comparisonBody').innerHTML=rows.map(r=>`<tr>
    <td>${r.project_name}</td><td><b>${r.vessel_name}</b></td>
    <td><span class="pill ${r.shift==='DAY'?'pill-info':'pill-gray'}">${r.shift==='DAY'?'☀️':'🌙'} ${r.shift}</span></td>
    <td class="mono">${r.records}</td>
    <td class="mono">${fmtInt(r.me_litres)}</td><td class="mono">${fmtInt(r.aux_litres)}</td><td class="mono">${fmtInt(r.dg_litres)}</td>
    <td class="mono"><b>${fmtInt(r.total_litres)}</b></td>
    <td class="mono">${r.me_lhr||'—'}</td><td class="mono">${r.aux_lhr||'—'}</td><td class="mono">${r.dg_lhr||'—'}</td>
    <td class="mono">${fmtInt(r.transfer_out)}</td>
  </tr>`).join('');
}

async function loadMissingSoundings(){
  const date=$('dashFrom')?.value||today();
  const rows=await api(`/api/dashboard/missing-soundings?date=${date}`);
  const mgr=isManager();
  $('missingBody').innerHTML=rows.map(r=>`<tr class="${r.missing?'row-danger':''}">
    <td class="mono">${r.stock_id||'—'}</td>
    <td class="mono">${fmtDate(r.stock_date||date)}</td>
    <td>${r.project_name}</td><td>${r.vessel_name}</td>
    <td>${r.missing?'<span class="pill pill-bad">MISSING</span>':'<span class="pill pill-ok">OK</span>'}</td>
    <td>${mgr&&r.missing&&r.stock_id?`
      <div class="sounding-upload-row">
        <input type="file" id="sndUpload_${r.stock_id}" accept="image/*" style="font-size:11px">
        <button class="btn btn-primary btn-sm" onclick="uploadMissingSounding(${r.stock_id})">Upload</button>
      </div>`:mgr?'<span class="muted">No stock entry</span>':''}
    </td>
  </tr>`).join('');
}

async function uploadMissingSounding(stockId){
  const input=$(`sndUpload_${stockId}`);
  if(!input?.files[0])return alert('Select an image first');
  const fd=new FormData();fd.append('file',input.files[0]);
  try{
    const r=await fetch(`/api/attachments/sounding/${stockId}`,{method:'POST',body:fd});
    if(!r.ok)throw new Error((await r.json()).error);
    await loadMissingSoundings();checkAlertBell();
    showMsg('stockMsg','<span class="pill pill-ok">Sounding uploaded</span>','ok');
  }catch(e){alert(e.message);}
}

// ── Clear log modal ────────────────────────────────────────────────────────
function openClearLogModal(){
  const id=$('detailStockId').value;if(!id)return alert('Load a stock first');
  const ov=document.createElement('div');ov.className='modal-overlay';ov.id='clearModal';
  ov.innerHTML=`<div class="modal">
    <div class="modal-title">Clear Log — Stock ID ${id}</div>
    <div class="note note-warn">This will mark the stock as deleted. A comment is required.</div>
    <div class="mt8"><label>Comment / Reason *</label><input id="clearComment" placeholder="e.g. Duplicate entry for this date/vessel"></div>
    <div id="clearMsg" class="mt8"></div>
    <div class="flex mt12">
      <button class="btn btn-danger" onclick="confirmClearLog(${id})">Confirm Clear</button>
      <button class="btn btn-ghost" onclick="closeModal('clearModal')">Cancel</button>
    </div>
  </div>`;
  document.body.appendChild(ov);ov.addEventListener('click',ev=>{if(ev.target===ov)closeModal('clearModal');});
}
async function confirmClearLog(id){
  const comment=$('clearComment').value;
  if(!comment.trim())return showMsg('clearMsg','Comment is required','err');
  try{
    await api(`/api/stock/${id}/clear`,{method:'POST',body:JSON.stringify({comment})});
    closeModal('clearModal');$('correctionDetails').innerHTML='';$('detailStockId').value='';
    showMsg('correctionMsg','<span class="pill pill-ok">Log cleared</span>','ok');
    loadLogs();
  }catch(e){showMsg('clearMsg',e.message,'err');}
}

// ── Export ─────────────────────────────────────────────────────────────────
function buildQs(){const from=$('dashFrom')?.value,to=$('dashTo')?.value;return from&&to?`?from_date=${from}&to_date=${to}`:'';}
function exportExcel(){window.open('/api/export/excel'+buildQs(),'_blank');}
function exportPdf()  {window.open('/api/export/pdf'+buildQs(),'_blank');}
function exportCsv()  {window.open('/api/export/csv'+buildQs(),'_blank');}

// ── Production ─────────────────────────────────────────────────────────────
async function saveProduction(){
  try{
    await api('/api/production',{method:'POST',body:JSON.stringify({
      date:$('prodDate').value,project_id:$('prodProject').value,vessel_id:$('prodVessel').value,
      as_per_qty:+$('asPerQty').value,true_qty:+$('trueQty').value,fuel_rate:+$('fuelRate').value
    })});
    showMsg('prodMsg','<span class="pill pill-ok">Saved</span>','ok');loadLogs();
  }catch(e){showMsg('prodMsg',e.message,'err');}
}

// ── HO Summary ─────────────────────────────────────────────────────────────
async function loadHoSummary(){
  const from=$('hoFrom').value,to=$('hoTo').value;
  const vessel_ids=getCheckedVessels('hoVesselChecks');
  if(!vessel_ids)return showMsg('masterMsg','Select at least one vessel','warn');
  let qs=from&&to?`?from_date=${from}&to_date=${to}`:'?';
  if(vessel_ids)qs+=`&vessel_ids=${vessel_ids}`;
  const data=await api('/api/dashboard/vessel-balances'+qs);
  $('hoProjectCards').innerHTML=data.byProject.map(p=>`
    <div class="kpi" style="border-top-color:${p.total_litres>0?'var(--accent)':'var(--border)'}">
      <div class="kpi-label">${p.project_name}</div>
      <div class="kpi-value">${fmtInt(p.total_litres)} L</div>
      <div class="kpi-sub">${p.vessels} vessels · ${p.days||0} days</div>
    </div>`).join('');
  $('hoVesselBody').innerHTML=data.byVessel.map(r=>{
    const isLow=r.fuel_threshold_litres>0&&r.latest_closing<=r.fuel_threshold_litres;
    return`<tr class="${isLow?'row-warn':''}">
      <td>${r.project_name}</td><td><b>${r.vessel_name}</b></td>
      <td class="mono">${r.fuel_threshold_litres>0?r.fuel_threshold_litres+' L':'—'}</td>
      <td class="mono">${r.latest_closing!=null?fmt(r.latest_closing)+' L':'—'}${isLow?' ⚠':''}</td>
      <td class="mono">${r.records}</td>
      <td class="mono">${fmtInt(r.me_litres)}</td><td class="mono">${fmtInt(r.aux_litres)}</td><td class="mono">${fmtInt(r.dg_litres)}</td>
      <td class="mono"><b>${fmtInt(r.total_litres)}</b></td>
      <td class="mono">${r.me_lhr||'—'}</td><td class="mono">${r.aux_lhr||'—'}</td><td class="mono">${r.dg_lhr||'—'}</td>
      <td class="mono">${fmt(r.total_hours,1)}</td>
    </tr>`;
  }).join('');
  $('hoSoundingBody').innerHTML=(data.missingSoundings||[]).map(r=>{
    const pct=r.total_days>0?Math.round(((r.total_days-r.missing_days)/r.total_days)*100):0;
    return`<tr class="${r.missing_days>0?'row-warn':''}">
      <td>${r.project_name}</td><td>${r.vessel_name}</td>
      <td class="mono">${r.total_days}</td>
      <td class="mono">${r.missing_days>0?`<span class="pill pill-bad">${r.missing_days}</span>`:'<span class="pill pill-ok">0</span>'}</td>
      <td><div style="background:var(--bg);border-radius:4px;overflow:hidden;height:14px;width:80px;display:inline-block;vertical-align:middle">
        <div style="background:${pct>=80?'var(--green)':'var(--red)'};height:100%;width:${pct}%"></div>
      </div> ${pct}%</td>
    </tr>`;
  }).join('');
}

// ── Charts ─────────────────────────────────────────────────────────────────
function destroyAllCharts(){Object.keys(chartInstances).forEach(k=>{if(chartInstances[k]){chartInstances[k].destroy();delete chartInstances[k];}});}

async function loadCharts(){
  const vessel_ids=getCheckedVessels('chartVesselChecks');
  if(!vessel_ids){$('chartArea').innerHTML='<div class="note note-warn">Select at least one vessel to load charts.</div>';return;}
  const from=$('chartFrom').value,to=$('chartTo').value;
  let qs=`?from_date=${from}&to_date=${to}&vessel_ids=${vessel_ids}`;

  // Load Chart.js
  try{ await loadChartJs(); }
  catch(e){ $('chartArea').innerHTML=`<div class="note note-err">❌ ${e.message}</div>`; return; }

  const rows=await api('/api/dashboard/consumption-trend'+qs);
  destroyAllCharts();

  if(!rows.length){
    $('chartArea').innerHTML='<div class="note" style="text-align:center;padding:32px">📭 <b>No data</b> for selected vessels and date range.</div>';
    return;
  }

  const selectedIds=vessel_ids.split(',').filter(Boolean);
  const multiVessel=selectedIds.length>1;

  // Build chart HTML
  const twoCharts=`
    <div class="grid2">
      <div class="card"><div class="section-head"><span class="dot"></span>Daily Fuel Consumption (L)</div><canvas id="cFuel" height="220"></canvas></div>
      <div class="card"><div class="section-head"><span class="dot"></span>Engine L/Hr Efficiency Trend</div><canvas id="cLhr" height="220"></canvas></div>
    </div>`;
  const fourCharts=twoCharts+`
    <div class="grid2">
      <div class="card"><div class="section-head"><span class="dot"></span>Closing Balance Trend (L)</div><canvas id="cBalance" height="220"></canvas></div>
      <div class="card"><div class="section-head"><span class="dot"></span>ME vs AUX vs DG Split</div><canvas id="cSplit" height="220"></canvas></div>
    </div>`;
  $('chartArea').innerHTML=multiVessel?twoCharts:fourCharts;

  // Group labels by date+shift+vessel
  const labels=rows.map(r=>`${fmtDate(r.date)} ${r.shift==='NIGHT'?'🌙':'☀️'}${multiVessel?' '+r.vessel_name:''}`);
  const C={ME:'#1054a0',AUX:'#0c6b3e',DG:'#854F0B',balance:'#0891b2'};

  // Chart 1: Fuel consumption
  chartInstances.fuel=new Chart($('cFuel'),{type:'bar',data:{labels,datasets:[
    {label:'ME (L)',data:rows.map(r=>+r.me||0),backgroundColor:C.ME+'99'},
    {label:'AUX (L)',data:rows.map(r=>+r.aux||0),backgroundColor:C.AUX+'99'},
    {label:'DG (L)',data:rows.map(r=>+r.dg||0),backgroundColor:C.DG+'99'}
  ]},options:{responsive:true,plugins:{legend:{position:'top'}},scales:{x:{stacked:true},y:{stacked:true}}}});

  // Chart 2: L/Hr trend
  chartInstances.lhr=new Chart($('cLhr'),{type:'line',data:{labels,datasets:[
    {label:'ME L/Hr',data:rows.map(r=>r.me_lhr?+r.me_lhr:null),borderColor:C.ME,tension:.3,fill:false},
    {label:'AUX L/Hr',data:rows.map(r=>r.aux_lhr?+r.aux_lhr:null),borderColor:C.AUX,tension:.3,fill:false},
    {label:'DG L/Hr',data:rows.map(r=>r.dg_lhr?+r.dg_lhr:null),borderColor:C.DG,tension:.3,fill:false}
  ]},options:{responsive:true,plugins:{legend:{position:'top'}},spanGaps:true}});

  // Charts 3+4 only for single vessel
  if(!multiVessel){
    chartInstances.balance=new Chart($('cBalance'),{type:'line',data:{labels,datasets:[
      {label:'Closing Balance (L)',data:rows.map(r=>+r.closing_balance||0),borderColor:C.balance,backgroundColor:C.balance+'22',tension:.3,fill:true}
    ]},options:{responsive:true,plugins:{legend:{position:'top'}}}});

    const totME=rows.reduce((a,r)=>a+(+r.me||0),0);
    const totAUX=rows.reduce((a,r)=>a+(+r.aux||0),0);
    const totDG=rows.reduce((a,r)=>a+(+r.dg||0),0);
    chartInstances.split=new Chart($('cSplit'),{type:'doughnut',data:{
      labels:['ME','AUX','DG'],
      datasets:[{data:[totME,totAUX,totDG],backgroundColor:[C.ME,C.AUX,C.DG],borderWidth:2}]
    },options:{responsive:true,plugins:{legend:{position:'bottom'}}}});
  }
}

// ── Efficiency (table only) ────────────────────────────────────────────────
async function loadEfficiency(){
  const from=$('effFrom').value,to=$('effTo').value;
  const qs=from&&to?`?from_date=${from}&to_date=${to}`:'';
  const rows=await api('/api/dashboard/efficiency'+qs);
  if(!rows.length){$('effBody').innerHTML='<tr><td colspan="14" class="muted" style="padding:24px;text-align:center">📭 No data — enter engine events first.</td></tr>';return;}
  $('effBody').innerHTML=rows.map(r=>`<tr>
    <td>${r.project_name}</td><td><b>${r.vessel_name}</b></td><td class="mono">${r.days}</td>
    <td class="mono">${fmtInt(r.me_litres)}</td><td class="mono">${fmt(r.me_hours,1)}</td>
    <td class="mono"><b ${r.me_lhr&&+r.me_lhr>500?'style="color:var(--red)"':''}>${r.me_lhr||'—'}</b></td>
    <td class="mono">${fmtInt(r.aux_litres)}</td><td class="mono">${fmt(r.aux_hours,1)}</td>
    <td class="mono"><b>${r.aux_lhr||'—'}</b></td>
    <td class="mono">${fmtInt(r.dg_litres)}</td><td class="mono">${fmt(r.dg_hours,1)}</td>
    <td class="mono"><b>${r.dg_lhr||'—'}</b></td>
    <td class="mono"><b>${fmtInt(r.total_litres)}</b></td><td class="mono">${fmt(r.total_hours,1)}</td>
  </tr>`).join('');
}

// ── Masters ────────────────────────────────────────────────────────────────
async function loadMasterTab(){
  await loadMaster();
  const allP=master.allProjects||[];
  $('projectList').innerHTML=`<table><thead><tr><th>Project</th><th>Status</th>${me.role==='admin'?'<th>Actions</th>':''}</tr></thead><tbody>
    ${allP.map(p=>`<tr class="${!p.active?'row-danger':''}">
      <td><b>${p.name}</b></td>
      <td>${p.active?'<span class="pill pill-ok">Active</span>':'<span class="pill pill-bad">Inactive</span>'}</td>
      ${me.role==='admin'?`<td>
        ${p.active?`<button class="btn btn-danger btn-sm" onclick="toggleProject(${p.id},0)">Deactivate</button>`:`<button class="btn btn-success btn-sm" onclick="toggleProject(${p.id},1)">Activate</button>`}
        <button class="btn btn-warn btn-sm" onclick="renameProject(${p.id},'${p.name}')">Rename</button>
      </td>`:''}
    </tr>`).join('')}
  </tbody></table>`;
  $('equipmentList').innerHTML=`<table><thead><tr><th>Name</th><th>Type</th><th>Category</th>${isManager()?'<th>Del</th>':''}</tr></thead><tbody>
    ${master.equipment.map(e=>`<tr>
      <td><b>${e.name}</b></td><td><span class="pill pill-info">${e.engine_type}</span></td><td>${e.equipment_type||'—'}</td>
      ${isManager()?`<td><button class="btn btn-danger btn-sm" onclick="deleteEquipment(${e.id})">Del</button></td>`:''}
    </tr>`).join('')}
  </tbody></table>`;
  await loadVesselEquipment();
}

async function loadVesselEquipment(){
  const vid=$('linkVessel')?.value;if(!vid)return;
  const rows=await api(`/api/equipment/vessel/${vid}`);
  const vessel=master.vessels.find(v=>String(v.id)===String(vid));
  if(vessel&&$('vesselThreshold'))$('vesselThreshold').value=vessel.fuel_threshold_litres||0;
  $('vesselEquipmentList').innerHTML=`<table><thead><tr><th>Equipment</th><th>Type</th><th>Actions</th></tr></thead><tbody>
    ${rows.length?rows.map(r=>`<tr><td><b>${r.name}</b></td><td><span class="pill pill-info">${r.engine_type}</span></td>
      <td><button class="btn btn-danger btn-sm" onclick="unlinkEquipment(${r.link_id})">Unlink</button></td>
    </tr>`).join(''):'<tr><td colspan="3" class="muted" style="padding:10px">No equipment linked</td></tr>'}
  </tbody></table>`;
}

async function addProject(){const name=$('newProjectName').value;if(!name)return;try{await api('/api/projects',{method:'POST',body:JSON.stringify({name})});$('newProjectName').value='';await loadMasterTab();showMsg('masterMsg','<span class="pill pill-ok">Project added</span>','ok');}catch(e){showMsg('masterMsg',e.message,'err');}}
async function toggleProject(id,active){if(!confirm(`${active?'Activate':'Deactivate'}?`))return;try{await api(`/api/projects/${id}`,{method:'PUT',body:JSON.stringify({active})});await loadMasterTab();}catch(e){alert(e.message);}}
async function renameProject(id,current){const name=prompt('New name:',current);if(!name||name===current)return;try{await api(`/api/projects/${id}`,{method:'PUT',body:JSON.stringify({name})});await loadMasterTab();}catch(e){alert(e.message);}}
async function addEquipment(){try{await api('/api/equipment',{method:'POST',body:JSON.stringify({name:$('eqName').value,engine_type:$('eqEngineType').value,equipment_type:$('eqType').value})});$('eqName').value='';$('eqType').value='';await loadMasterTab();showMsg('masterMsg','<span class="pill pill-ok">Added</span>','ok');}catch(e){showMsg('masterMsg',e.message,'err');}}
async function deleteEquipment(id){if(!confirm('Delete?'))return;try{await api(`/api/equipment/${id}`,{method:'DELETE'});await loadMasterTab();}catch(e){showMsg('masterMsg',e.message,'err');}}
async function addVessel(){try{await api('/api/vessels',{method:'POST',body:JSON.stringify({name:$('newVesselName').value,vessel_type:$('newVesselType').value,project_id:$('newVesselProject').value})});$('newVesselName').value='';await loadMasterTab();showMsg('masterMsg','<span class="pill pill-ok">Vessel added</span>','ok');}catch(e){showMsg('masterMsg',e.message,'err');}}
async function linkEquipment(){const vid=$('linkVessel').value,eid=$('linkEquipment').value;if(!vid||!eid)return alert('Select both');try{await api('/api/vessel-equipment',{method:'POST',body:JSON.stringify({vessel_id:vid,equipment_id:eid})});await loadVesselEquipment();showMsg('masterMsg','<span class="pill pill-ok">Linked</span>','ok');}catch(e){showMsg('masterMsg',e.message,'err');}}
async function unlinkEquipment(id){if(!confirm('Unlink?'))return;try{await api(`/api/vessel-equipment/${id}`,{method:'DELETE'});await loadVesselEquipment();}catch(e){alert(e.message);}}
async function saveThreshold(){const vid=$('linkVessel').value,val=$('vesselThreshold').value;if(!vid)return alert('Select vessel');try{await api(`/api/vessels/${vid}/threshold`,{method:'PUT',body:JSON.stringify({fuel_threshold_litres:+val})});await loadMaster();showMsg('masterMsg',`<span class="pill pill-ok">Threshold set to ${val} L</span>`,'ok');}catch(e){showMsg('masterMsg',e.message,'err');}}

// ── Correction ─────────────────────────────────────────────────────────────
async function loadDetailsByInput(){
  const id=$('detailStockId').value;if(!id)return;
  try{currentDetails=await api(`/api/stock/${id}`);$('correctionDetails').innerHTML=renderDetails(currentDetails);}
  catch(e){showMsg('correctionMsg',e.message,'err');}
}

// ── Users ──────────────────────────────────────────────────────────────────
async function loadUsers(){
  const users=await api('/api/users');
  $('userTableBody').innerHTML=users.map(u=>`<tr class="${!u.active?'row-danger':''}">
    <td class="mono">${u.id}</td><td><b>${u.username}</b></td>
    <td><span class="pill pill-${u.role==='admin'?'bad':u.role==='manager'?'warn':'info'}">${u.role}</span></td>
    <td>${(master?.projects||[]).find(p=>p.id===u.project_id)?.name||'—'}</td>
    <td>${u.active?'<span class="pill pill-ok">Active</span>':'<span class="pill pill-bad">Inactive</span>'}${u.locked_until&&new Date(u.locked_until)>new Date()?'<span class="pill pill-warn">LOCKED</span>':''}</td>
    <td>
      <button class="btn btn-warn btn-sm" onclick="openEditUserModal(${u.id})">Edit</button>
      ${u.active?`<button class="btn btn-danger btn-sm" onclick="toggleUserActive(${u.id},0)">Deactivate</button>`:`<button class="btn btn-success btn-sm" onclick="toggleUserActive(${u.id},1)">Activate</button>`}
      ${u.locked_until&&new Date(u.locked_until)>new Date()?`<button class="btn btn-ghost btn-sm" onclick="unlockUser(${u.id})">Unlock</button>`:''}
    </td>
  </tr>`).join('');
}
function openAddUserModal(){
  const ov=document.createElement('div');ov.className='modal-overlay';ov.id='userModal';
  ov.innerHTML=`<div class="modal"><div class="modal-title">Add New User</div>
    <div class="grid">
      <div><label>Username</label><input id="nuUser"></div>
      <div><label>Password (min 8)</label><input type="password" id="nuPass"></div>
      <div><label>Role</label><select id="nuRole"><option value="operator">Operator</option><option value="manager">Manager</option><option value="admin">Admin</option></select></div>
      <div><label>Project</label><select id="nuProject"><option value="">—</option>${(master?.projects||[]).map(p=>`<option value="${p.id}">${p.name}</option>`).join('')}</select></div>
    </div>
    <div id="nuMsg" class="mt8"></div>
    <div class="flex mt12"><button class="btn btn-primary" onclick="saveNewUser()">Create</button><button class="btn btn-ghost" onclick="closeModal('userModal')">Cancel</button></div>
  </div>`;
  document.body.appendChild(ov);ov.addEventListener('click',ev=>{if(ev.target===ov)closeModal('userModal');});
}
async function saveNewUser(){try{await api('/api/users',{method:'POST',body:JSON.stringify({username:$('nuUser').value,password:$('nuPass').value,role:$('nuRole').value,project_id:$('nuProject').value||null})});closeModal('userModal');await loadUsers();}catch(e){showMsg('nuMsg',e.message,'err');}}
function openEditUserModal(id){
  const ov=document.createElement('div');ov.className='modal-overlay';ov.id='userModal';
  ov.innerHTML=`<div class="modal"><div class="modal-title">Edit User ID ${id}</div>
    <div class="grid">
      <div><label>New Password</label><input type="password" id="euPass" placeholder="Leave blank to keep"></div>
      <div><label>Role</label><select id="euRole"><option value="operator">Operator</option><option value="manager">Manager</option><option value="admin">Admin</option></select></div>
      <div><label>Project</label><select id="euProj"><option value="">—</option>${(master?.projects||[]).map(p=>`<option value="${p.id}">${p.name}</option>`).join('')}</select></div>
    </div>
    <div id="euMsg" class="mt8"></div>
    <div class="flex mt12"><button class="btn btn-primary" onclick="saveEditUser(${id})">Save</button><button class="btn btn-ghost" onclick="closeModal('userModal')">Cancel</button></div>
  </div>`;
  document.body.appendChild(ov);ov.addEventListener('click',ev=>{if(ev.target===ov)closeModal('userModal');});
}
async function saveEditUser(id){const body={role:$('euRole').value,project_id:$('euProj').value||null};const pw=$('euPass').value;if(pw)body.password=pw;try{await api(`/api/users/${id}`,{method:'PUT',body:JSON.stringify(body)});closeModal('userModal');await loadUsers();}catch(e){showMsg('euMsg',e.message,'err');}}
async function toggleUserActive(id,active){if(!confirm(`${active?'Activate':'Deactivate'}?`))return;try{await api(`/api/users/${id}`,{method:'PUT',body:JSON.stringify({active})});await loadUsers();}catch(e){alert(e.message);}}
async function unlockUser(id){try{await api(`/api/users/${id}`,{method:'PUT',body:JSON.stringify({unlock:true})});await loadUsers();}catch(e){alert(e.message);}}

// ── Audit ──────────────────────────────────────────────────────────────────
async function loadAudit(){
  const from=$('auditFrom')?.value,to=$('auditTo')?.value;
  const qs=from&&to?`?from_date=${from}&to_date=${to}`:'';
  const rows=await api('/api/audit'+qs);
  $('auditBody').innerHTML=rows.map(a=>`<tr>
    <td class="mono muted">${a.created_at}</td><td><b>${a.username||'—'}</b></td>
    <td><span class="pill pill-gray">${a.action}</span></td>
    <td class="muted">${a.entity} ${a.entity_id?'#'+a.entity_id:''}</td>
    <td class="muted" style="max-width:260px;word-break:break-all;font-size:11px">${a.details||''}</td>
  </tr>`).join('');
}

// ── Bootstrap ──────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded',()=>{
  ['loginUser','loginPass'].forEach(id=>{
    const el=$(id);if(el)el.addEventListener('keydown',e=>{if(e.key==='Enter')login();});
  });
  const dateEl=$('date');if(dateEl)dateEl.addEventListener('change',updateDateDisplay);
  init().catch(()=>{});
});
