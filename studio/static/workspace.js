const $ = id => document.getElementById(id);
const S = {projects:[], prompts:[], project:null, branch:null, version:null, busy:false, settings:null};
function node(tag, cls, text) { const e=document.createElement(tag); if(cls)e.className=cls; if(text!==undefined)e.textContent=text; return e; }
function notify(text, error=false) {
  $('notice').textContent=text; $('notice').className=error?'error':'success';
  document.querySelectorAll('.dialog-notice').forEach(e=>e.remove());
  if(error){const opened=[...document.querySelectorAll('dialog[open]')].at(-1);if(opened){const note=node('p','dialog-notice',text);note.style.color='#a14f39';note.setAttribute('role','alert');opened.prepend(note);}}
}
async function api(path, body) {
  const r=await fetch('/api/workspace'+path,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const data=await r.json(); if(!r.ok)throw new Error(typeof data.detail==='string'?data.detail:'请求格式不正确。'); return data;
}
function current(){return S.project?.versions.find(v=>v.id===S.version);}
function branch(){return S.project?.branches.find(b=>b.id===S.branch);}
function dirty(){return !!current() && $('document').value!==current().document;}
function canLeave(){return !dirty() || window.confirm('当前稿件有未保存修改。放弃这些修改并切换？');}
function vlabel(id){return 'V'+(S.project.versions.findIndex(v=>v.id===id)+1);}
function headState(){
  const history=!!branch() && branch().head!==S.version;
  $('historical').hidden=!history;
  $('send-button').disabled=S.busy||history;
  $('save-document').disabled=S.busy||history;
  $('document').readOnly=S.busy||history;
  $('instruction').disabled=S.busy||history;
  $('dirty-status').textContent=history?'历史版本 · 只读':dirty()?'有未保存修改':'已保存';
}
async function run(work){
  if(S.busy)return;
  S.busy=true; const buttons=[...document.querySelectorAll('button')]; buttons.forEach(b=>b.disabled=true); headState();
  notify('处理中，请稍候。真实模型生成可能需要一至两分钟。');
  try{await work();}catch(e){notify(e.message,true);}finally{S.busy=false;buttons.forEach(b=>b.disabled=false);headState();}
}
function pathTo(id){const map=new Map(S.project.versions.map(v=>[v.id,v])), result=[];while(id){const v=map.get(id);result.push(v);id=v.parent_id;}return result.reverse();}
function renderProjects(){
  $('projects').replaceChildren(...S.projects.map(p=>{
    const b=node('button','list-button'+(p.id===S.project?.id?' active':''),p.title);
    b.onclick=()=>{if(!canLeave())return;run(async()=>{load(await api('/projects/'+p.id));notify('已打开项目。');});};return b;
  }));
  if(!S.projects.length)$('projects').append(node('p','muted small','还没有项目，先写下一个想法。'));
}
function load(project,bid,vid){
  S.project=project; S.branch=bid||project.branches[0].id; S.version=vid||branch().head;
  localStorage.setItem('storyBranchSelection',JSON.stringify({pid:project.id,bid:S.branch,vid:S.version}));render();
}
function render(){
  renderProjects(); $('welcome').hidden=true;$('session').hidden=false;$('branch-section').hidden=false;$('document-panel').hidden=false;
  $('project-title').textContent=S.project.title;$('branch-label').textContent=branch().name+' / '+vlabel(S.version);$('brief-text').textContent=S.project.brief;
  $('branches').replaceChildren(...S.project.branches.map(b=>{
    const e=node('button','list-button'+(b.id===S.branch?' active':''));e.append(node('b','',b.name),node('small','muted',b.fork_version?'从 '+vlabel(b.fork_version)+' 分叉':'原始故事线'));
    e.onclick=()=>{if(!S.busy&&canLeave())load(S.project,b.id);};return e;
  }));
  $('versions').replaceChildren(...pathTo(branch().head).slice().reverse().map(v=>{
    const b=node('button','version'+(v.id===S.version?' active':''));
    b.append(node('b','',vlabel(v.id)+' · '+(v.provider==='manual'?'人工记录':v.provider==='demo'?'样例生成':'DeepSeek')),node('span','',v.instruction.slice(0,60)));
    b.onclick=()=>{if(!S.busy&&canLeave())load(S.project,S.branch,v.id);};return b;
  }));
  const history=pathTo(S.version);$('chat').replaceChildren();
  history.forEach(v=>{
    const row=node('article','turn');row.append(node('div','turn-label',vlabel(v.id)+' · '+new Date(v.created_at).toLocaleString()));
    row.append(node('p','user-message',v.instruction),node('p','assistant-message',v.reply));$('chat').append(row);
  });
  $('document').value=current().document;
  $('version-meta').textContent=vlabel(S.version)+' · '+(current().provider==='demo'?'固定样例':current().provider==='manual'?'人工保存':current().model);
  $('provenance').textContent=JSON.stringify({provider:current().provider,model:current().model,parent:current().parent_id,prompt:JSON.parse(current().prompt_json)},null,2);
  const others=S.project.versions.filter(v=>v.id!==S.version);
  $('compare-select').replaceChildren(node('option','','请选择对照版本'),...others.map(v=>{const o=node('option','',vlabel(v.id)+' · '+v.instruction.slice(0,30));o.value=v.id;return o;}));
  $('compare-select').options[0].value='';$('compare-select').value=current().parent_id||'';compare();headState();
  $('chat').scrollTop=$('chat').scrollHeight;
}
function compare(){const v=S.project?.versions.find(v=>v.id===$('compare-select').value);$('compare-content').textContent=v?(v.document||'此版本尚无稿件。'):'选择历史版本，在这里对照阅读。';}
function renderPrompts(){
  const selected=$('prompt-select').value;
  $('prompt-select').replaceChildren(new Option('自由对话',''),...S.prompts.map(p=>new Option(p.title,p.id)));
  $('prompt-select').value=selected;
  $('library').replaceChildren(...S.prompts.map(p=>{
    const card=node('article','prompt-card');card.append(node('span','badge',p.category+' · '+(p.builtin?'内置':'个人')),node('h3','',p.title),node('p','',p.body));
    const actions=node('div','label-row'); const use=node('button','primary','应用到本轮');use.onclick=()=>{if(!S.project){notify('请先创建或打开项目。',true);return;}if(S.busy)return;$('prompt-select').value=p.id;$('prompt-body').value=p.body;$('library-dialog').close();notify('已应用提示词，可在发送前调整。');};
    const copy=node('button','','修改并另存');copy.onclick=()=>{template(p.title+' · 改版',p.category,p.body);};actions.append(copy,use);card.append(actions);return card;
  }));
}
function template(title,category,body){$('template-title').value=title;$('template-category').value=category;$('template-body').value=body;$('template-dialog').showModal();}
function renderSettings(){
  $('mode').textContent=S.settings.mode==='demo'?'样例模式 · 固定内容':'DeepSeek · 已配置';
  $('send-hint').textContent=S.settings.mode==='demo'?'固定样例，仅验证流程':'发送将调用 DeepSeek，并保存完整新版本';
  $('provider').value=S.settings.mode;$('model-name').value=S.settings.model;
  $('key-status').textContent=S.settings.configured?'已有密钥配置；实际连通性以生成请求为准。':'尚未配置密钥。';
}
document.querySelectorAll('[data-close]').forEach(b=>b.onclick=()=>{if(!S.busy)$(b.dataset.close).close();});
['new-button','welcome-new'].forEach(id=>$(id).onclick=()=>{if(canLeave())$('new-dialog').showModal();});
$('library-button').onclick=()=>$('library-dialog').showModal();
$('settings-button').onclick=()=>{$('api-key').value='';renderSettings();$('settings-dialog').showModal();};
$('settings-dialog').addEventListener('close',()=>{$('api-key').value='';});
$('settings-form').onsubmit=e=>{e.preventDefault();run(async()=>{
  const key=$('api-key').value.trim();$('api-key').value='';
  S.settings=await api('/settings',{mode:$('provider').value,model:$('model-name').value,api_key:key});renderSettings();$('settings-dialog').close();notify('配置已保存。可发送创作需求；本次未发起模型调用。');
});};
$('clear-key').onclick=()=>run(async()=>{S.settings=await api('/settings',{mode:'demo',model:$('model-name').value,clear_key:true});$('api-key').value='';renderSettings();notify('密钥已从当前服务内存清除。');});
$('new-form').onsubmit=e=>{e.preventDefault();const data=Object.fromEntries(new FormData(e.target));run(async()=>{const p=await api('/projects',data);S.projects=await api('/projects');load(p);$('new-dialog').close();notify('项目已创建，选择指南并开始对话。');});};
$('prompt-select').onchange=()=>{$('prompt-body').value=S.prompts.find(p=>p.id===$('prompt-select').value)?.body||'';};
$('save-template').onclick=()=>template(S.prompts.find(p=>p.id===$('prompt-select').value)?.title||'我的创作指南','自定义',$('prompt-body').value);
$('template-form').onsubmit=e=>{e.preventDefault();run(async()=>{const p=await api('/prompts',{title:$('template-title').value,category:$('template-category').value,body:$('template-body').value});S.prompts=await api('/prompts');renderPrompts();$('prompt-select').value=p.id;$('prompt-body').value=p.body;$('template-dialog').close();notify('个人模板已保存，后续项目也可使用。');});};
$('chat-form').onsubmit=e=>{e.preventDefault();if(dirty()){notify('请先保存稿件修改，再发送创作需求。',true);return;}run(async()=>{
  const title=S.prompts.find(p=>p.id===$('prompt-select').value)?.title||'自由对话';
  const p=await api('/projects/'+S.project.id+'/versions',{action:'chat',branch_id:S.branch,parent_id:S.version,instruction:$('instruction').value,prompt_title:title,prompt_body:$('prompt-body').value});
  load(p,S.branch);$('instruction').value='';notify('回复与稿件已保存为 '+vlabel(S.version)+'。');
});};
$('save-document').onclick=()=>run(async()=>{
  if(!dirty())throw new Error('稿件没有变化。');
  const p=await api('/projects/'+S.project.id+'/versions',{action:'edit',branch_id:S.branch,parent_id:S.version,instruction:'人工修改稿件',document:$('document').value});load(p,S.branch);notify('人工修改已保存为新版本。');
});
$('document').oninput=headState;$('compare-select').onchange=compare;
$('fork-button').onclick=()=>{if(!canLeave())return;$('fork-source').textContent='从 '+vlabel(S.version)+' 创建分支。该版本之前的对话和稿件将被继承。';$('fork-name').value='';$('fork-dialog').showModal();};
$('fork-form').onsubmit=e=>{e.preventDefault();run(async()=>{const result=await api('/projects/'+S.project.id+'/branches',{version_id:S.version,name:$('fork-name').value});load(result.project,result.branch_id);$('fork-dialog').close();notify('新分支已创建，原分支的后续版本保持独立。');});};
$('refresh-button').onclick=()=>{if(canLeave())run(async()=>{load(await api('/projects/'+S.project.id),S.branch);notify('已读取最新版本。');});};
$('export-button').onclick=()=>{
  if(dirty()){notify('请先保存稿件修改再导出。',true);return;}
  const v=current(); const content='# '+S.project.title+'\n\n分支：'+branch().name+' / '+vlabel(v.id)+'\n来源：'+v.provider+' '+v.model+'\n\n## 创作简报\n\n'+S.project.brief+'\n\n## 稿件\n\n'+v.document;
  const url=URL.createObjectURL(new Blob([content],{type:'text/markdown;charset=utf-8'})), a=node('a');a.href=url;a.download='story-'+vlabel(v.id)+'.md';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
};
window.addEventListener('beforeunload',e=>{if(dirty()||S.busy){e.preventDefault();e.returnValue='';}});
async function boot(){
  [S.projects,S.prompts,S.settings]=await Promise.all([api('/projects'),api('/prompts'),api('/settings')]);renderProjects();renderPrompts();renderSettings();
  let saved;try{saved=JSON.parse(localStorage.getItem('storyBranchSelection'));}catch{}
  if(saved&&S.projects.some(p=>p.id===saved.pid)){const p=await api('/projects/'+saved.pid);const b=p.branches.find(b=>b.id===saved.bid)||p.branches[0];load(p,b.id,p.versions.some(v=>v.id===saved.vid)?saved.vid:b.head);}
  notify('工作台已就绪。');
}
boot().catch(e=>notify('加载失败：'+e.message,true));
