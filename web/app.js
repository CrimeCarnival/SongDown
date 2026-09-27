'use strict';
const $ = id => document.getElementById(id);
const state = {files: [], caps: {}, job: null, busy: false, timer: null, limits: {bytes: 200*1024*1024, files: 100}, rendered: ''};
const headers = {'X-Requested-With': 'AudioWorkbench'};
const statusNames = {queued:'排队中',running:'转换中',completed:'已完成',partial:'部分完成',failed:'转换失败',cancelled:'已取消'};
const terminal = new Set(['completed','partial','failed','cancelled']);
function notice(message, kind='info') { const el=$('notice'); el.textContent=message; el.className=`notice ${kind}`; el.hidden=!message; }
function size(bytes) { if(bytes<1024)return `${bytes} B`; if(bytes<1024**2)return `${(bytes/1024).toFixed(1)} KB`; return `${(bytes/1024**2).toFixed(1)} MB`; }
async function api(path, options={}) {
  const response = await fetch(path,{...options,headers:{...headers,...options.headers}});
  let data;
  try { data=await response.json(); } catch { throw new Error(`服务响应异常（${response.status}），请稍后重试`); }
  if(!response.ok) { if(response.status===401){$('login-panel').hidden=false;$('workbench').hidden=true;} throw new Error(data.error||`请求失败（${response.status}）`); }
  return data;
}
function tasks() { return [...document.querySelectorAll('.task-option input:checked')].map(input=>input.value); }
function nameOf(file) { return file.webkitRelativePath || file.name; }
function extension(file) { return file.name.split('.').pop().toLowerCase(); }
function updateControls() {
  $('start').disabled=state.busy||!state.files.length||!tasks().length;
  $('clear-files').disabled=state.busy||!state.files.length;
  $('pick-files').disabled=state.busy;$('pick-folder').disabled=state.busy;
  $('file-input').disabled=state.busy;$('folder-input').disabled=state.busy;
  document.querySelectorAll('.remove-file').forEach(b=>b.disabled=state.busy);
  document.querySelectorAll('.task-option input').forEach(b=>b.disabled=state.busy);
  $('cancel').hidden=!state.busy;$('cancel').disabled=!state.job;
}
function renderFiles() {
  $('file-count').textContent=`${state.files.length} 个文件`;
  $('total-size').textContent=size(state.files.reduce((n,f)=>n+f.size,0));
  const list=$('file-list');list.replaceChildren();
  if(!state.files.length){const empty=document.createElement('div');empty.className='empty-state';empty.innerHTML='<span>♫</span><p>还没有添加音乐</p><small>支持 NCM、OGG、MGG、MFLAC 和 LRC</small>';list.append(empty);}
  state.files.forEach((file,index)=>{
    const row=document.createElement('div');row.className='file-row';
    const icon=document.createElement('div');icon.className='file-icon';icon.textContent=extension(file).toUpperCase();
    const meta=document.createElement('div');meta.className='file-meta';
    const name=document.createElement('strong');name.textContent=nameOf(file);name.title=nameOf(file);
    const detail=document.createElement('small');detail.textContent=size(file.size);meta.append(name,detail);
    const remove=document.createElement('button');remove.className='remove-file';remove.textContent='×';remove.setAttribute('aria-label',`移除 ${nameOf(file)}`);
    remove.onclick=()=>{state.files.splice(index,1);renderFiles();};row.append(icon,meta,remove);list.append(row);
  });updateControls();
}
function addFiles(files) {
  if(state.busy)return;
  const messages=[];let total=state.files.reduce((n,f)=>n+f.size,0);
  for(const file of files){
    const ext=extension(file);
    if(!state.caps[ext]){messages.push(`${file.name}：不支持此文件格式`);continue;}
    if(!file.size){messages.push(`${file.name}：文件为空`);continue;}
    if(state.files.some(f=>nameOf(f).toLowerCase()===nameOf(file).toLowerCase())){messages.push(`${file.name}：已在列表中`);continue;}
    if(state.files.length>=state.limits.files||total+file.size>state.limits.bytes-65536){messages.push('已达到单批数量或大小限制，请分批转换');break;}
    state.files.push(file);total+=file.size;
    const checkbox=document.querySelector(`.task-option input[value="${ext}"]`);if(checkbox)checkbox.checked=true;
  }
  notice(messages.slice(0,4).join('；'),messages.length?'error':'info');renderFiles();
}
async function loadEnvironment() {
  const data=await api('/api/capabilities');state.caps=data.tasks;state.limits=data.limits;
  $('mode-label').textContent='完整功能版';
  $('upload-limits').textContent=`每批最多 ${data.limits.files} 个文件 · ${size(data.limits.bytes)}`;
  const previous=tasks();const root=$('task-options');root.replaceChildren();
  for(const key of ["ncm","ogg","lrc","mgg","mflac"]){
    const task=data.tasks[key];
    if(key==='cookie')continue;
    const label=document.createElement('label');label.className='task-option';
    const input=document.createElement('input');input.type='checkbox';input.value=key;input.disabled=false;
    input.checked=previous.length?previous.includes(key):true;input.onchange=updateControls;
    const text=document.createElement('span');const title=document.createElement('strong');title.textContent=task.label;
    const detail=document.createElement('small');detail.textContent=task.available?task.detail:'服务端尚未就绪，转换时会说明原因';text.append(title,detail);label.append(input,text);root.append(label);
  }
  updateControls();
}
function renderJob(job) {
  state.job=job.id;$('result-panel').hidden=false;
  const done=terminal.has(job.status)&&Boolean(job.finished);state.busy=!done;
  $('job-status').textContent=statusNames[job.status]||job.status;
  $('result-title').textContent=done?'转换结果':'正在处理';
  const stats=job.stats;const processed=stats.success+stats.skipped+stats.failed;
  $('progress').value=done?100:(stats.total?processed/stats.total*100:0);
  $('progress-text').textContent=done?`${statusNames[job.status]} · 已处理 ${processed} / ${stats.total} 个文件`:`${statusNames[job.status]} · ${processed} / ${stats.total}`;
  $('stats-text').textContent=`成功 ${stats.success} · 跳过 ${stats.skipped} · 失败 ${stats.failed}`;
  $('log-text').textContent=job.logs.join('\n');
  $('delete-job').disabled=!done;
  const signature=JSON.stringify([job.outputs,job.file_results]);
  if(done&&signature!==state.rendered){
    state.rendered=signature;const root=$('result-files');root.replaceChildren();
    for(const failure of (job.file_results||[]).filter(f=>f.status==='failed')){const row=document.createElement('div');row.className='failure-card';const title=document.createElement('strong');title.textContent=failure.name||'转换任务';const reason=document.createElement('p');reason.textContent=failure.reason;const action=document.createElement('small');action.textContent=`${failure.action}（${failure.code}）`;row.append(title,reason,action);root.append(row);}
    for(const output of job.outputs){
      const row=document.createElement('div');row.className='result-row';
      const meta=document.createElement('div');meta.className='file-meta';const name=document.createElement('strong');name.textContent=output.name;
      const detail=document.createElement('small');detail.textContent=size(output.size);meta.append(name,detail);row.append(meta);
      const url=`/api/jobs/${job.id}/files/${output.name.split('/').map(encodeURIComponent).join('/')}`;
      if(/\.(mp3|flac)$/i.test(output.name)){const audio=document.createElement('audio');audio.controls=true;audio.preload='none';audio.src=url+'?preview=1';audio.setAttribute('aria-label',`试听 ${output.name}`);row.append(audio);}
      const link=document.createElement('a');link.className='text-button';link.href=url;link.textContent='↓ 下载';link.download=output.name;row.append(link);root.append(row);
    }
  }
  $('download-all').hidden=!done||!job.outputs.length;$('download-all').href=`/api/jobs/${job.id}/archive`;
  if(done){$('start').innerHTML='再次转换 <span>→</span>';clearTimeout(state.timer);}
  updateControls();return done;
}
async function poll() {
  try { const job=await api(`/api/jobs/${state.job}`);if(!renderJob(job))state.timer=setTimeout(poll,700); }
  catch(error){notice(error.message,'error');state.timer=setTimeout(poll,4000);}
}
async function start() {
  if(state.busy)return;
  const selected=tasks();const excluded=state.files.filter(f=>!selected.includes(extension(f)));
  if(excluded.length){notice('列表中有未启用对应转换任务的文件，请勾选其格式或移除文件。','error');return;}
  if(state.job){notice('请先下载并删除上一批任务，再开始新的转换。');return;}
  const form=new FormData();form.append('tasks',JSON.stringify(selected));state.files.forEach(f=>form.append('files',f,nameOf(f)));
  state.busy=true;state.rendered='';notice('');updateControls();$('start').textContent='正在上传…';
  $('result-files').replaceChildren();$('download-all').hidden=true;
  try {
    const job=await new Promise((resolve,reject)=>{
      const xhr=new XMLHttpRequest();xhr.open('POST','/api/jobs');xhr.setRequestHeader('X-Requested-With','AudioWorkbench');
      xhr.upload.onprogress=e=>{if(e.lengthComputable)$('start').textContent=`正在上传 ${Math.round(e.loaded/e.total*100)}%`;};
      xhr.onload=()=>{try{const data=JSON.parse(xhr.responseText);xhr.status===202?resolve(data):reject(new Error(data.error||'上传失败'));}catch{reject(new Error('上传失败，服务器响应异常'));}};
      xhr.onerror=()=>reject(new Error('上传中断，请检查网络后重试'));xhr.timeout=180000;xhr.ontimeout=()=>reject(new Error('上传超时，请分批上传'));xhr.send(form);
    });
    sessionStorage.setItem('songdown-job',job.id);$('start').textContent='正在转换…';renderJob(job);poll();
  } catch(error){state.busy=false;notice(error.message,'error');$('start').innerHTML='开始转换 <span>→</span>';updateControls();}
}
async function loadDownloads(){
  const data=await api('/api/downloads');
  $('component-title').textContent=data.title;
  $('component-info').textContent=`QQ 音乐 ${data.qq_version} · Frida ${data.frida_version}。${data.note}`;
  $('component-link').hidden=!data.available;
  if(data.available){$('component-link').href=data.url;$('component-link').textContent='打开网盘下载 →';}
  $('component-status').textContent=data.available?`提取码：${data.extraction_code||'无需提取码'}${data.sha256?' · SHA256：'+data.sha256:''}`:'组件包整理中，网盘链接待站长提供。在线转换用户无需下载或安装。';
}
async function initialize() {
  const auth=await api('/api/session');$('login-panel').hidden=auth.authenticated;$('workbench').hidden=true;$('logout').hidden=!auth.required||!auth.authenticated;
  if(!auth.authenticated)return;
  await loadEnvironment();await loadDownloads();$('workbench').hidden=false;const previous=sessionStorage.getItem('songdown-job');
  if(previous){try{const job=await api(`/api/jobs/${previous}`);if(!renderJob(job))poll();}catch{sessionStorage.removeItem('songdown-job');}}
}
$('pick-files').onclick=e=>{e.stopPropagation();$('file-input').click();};$('pick-folder').onclick=e=>{e.stopPropagation();$('folder-input').click();};
$('file-input').onchange=e=>{addFiles(e.target.files);e.target.value='';};$('folder-input').onchange=e=>{addFiles(e.target.files);e.target.value='';};
$('dropzone').onclick=e=>{if(!state.busy&&e.target.tagName!=='BUTTON')$('file-input').click();};
$('dropzone').onkeydown=e=>{if(e.target===$('dropzone')&&['Enter',' '].includes(e.key)){e.preventDefault();if(!state.busy)$('file-input').click();}};
for(const event of ['dragenter','dragover'])$('dropzone').addEventListener(event,e=>{e.preventDefault();$('dropzone').classList.add('dragover');});
for(const event of ['dragleave','drop'])$('dropzone').addEventListener(event,e=>{e.preventDefault();$('dropzone').classList.remove('dragover');});
$('dropzone').addEventListener('drop',e=>addFiles(e.dataTransfer.files));
$('clear-files').onclick=()=>{state.files=[];renderFiles();notice('');};$('start').onclick=start;
$('cancel').onclick=async()=>{try{$('cancel').disabled=true;await api(`/api/jobs/${state.job}/cancel`,{method:'POST'});notice('已请求取消，正在停止转换。');}catch(e){notice(e.message,'error');}};
$('delete-job').onclick=async()=>{try{await api(`/api/jobs/${state.job}`,{method:'DELETE'});state.job=null;state.rendered='';sessionStorage.removeItem('songdown-job');$('result-panel').hidden=true;$('result-files').replaceChildren();$('start').innerHTML='开始转换 <span>→</span>';notice('任务与临时文件已删除。','success');updateControls();}catch(e){notice(e.message,'error');}};
$('refresh-env').onclick=async()=>{try{await loadEnvironment();notice('环境状态已更新。','success');}catch(e){notice(e.message,'error');}};
$('login-form').onsubmit=async e=>{e.preventDefault();try{await api('/api/session',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token:$('access-token').value})});$('access-token').value='';notice('');await initialize();}catch(e){notice(e.message,'error');}};
$('logout').onclick=async()=>{try{if(state.busy){notice('请先等待任务结束或取消，再退出。');return;}await api('/api/session',{method:'DELETE'});sessionStorage.removeItem('songdown-job');location.reload();}catch(e){notice(e.message,'error');}};
initialize().catch(e=>notice(e.message,'error'));
