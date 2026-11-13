const $ = id => document.getElementById(id);
const S = {projects:[], prompts:[], project:null, branch:null, version:null, busy:false, settings:null, user:null, stage:"brief", writing:null};
const themeMedia=window.matchMedia('(prefers-color-scheme: dark)');
function applyTheme(){const choice=localStorage.getItem('storyTheme')||'system';$('theme-select').value=choice;document.documentElement.dataset.theme=choice==='system'?(themeMedia.matches?'dark':'light'):choice;}
$('theme-select').onchange=()=>{localStorage.setItem('storyTheme',$('theme-select').value);applyTheme();};themeMedia.addEventListener('change',applyTheme);applyTheme();
let failedResponse='';
function node(tag, cls, text) { const e=document.createElement(tag); if(cls)e.className=cls; if(text!==undefined)e.textContent=text; return e; }
function notify(text, error=false) {
  $('notice').textContent=text; $('notice').className=error?'error':'success';
  document.querySelectorAll('.dialog-notice').forEach(e=>e.remove());
  if(error){const opened=[...document.querySelectorAll('dialog[open]')].at(-1);if(opened){const note=node('p','dialog-notice',text);note.style.color='#a14f39';note.setAttribute('role','alert');opened.prepend(note);}}
}
async function api(path, body) {
  const r=await fetch('/api/workspace'+path,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const data=await r.json(); if(r.status===401){location.assign('/login');throw new Error('登录已过期，请重新登录。');} if(!r.ok){const error=new Error(typeof data.detail==='string'?data.detail:data.detail?.message||'请求格式不正确。');error.status=r.status;error.responseText=data.detail?.response_text;throw error;} return data;
}
function current(){return S.project?.versions.find(v=>v.id===S.version);}
function branch(){return S.project?.branches.find(b=>b.id===S.branch);}
const STAGES=[['brief','创作定位','seed-brief'],['concept','故事立意','seed-concept'],['character','人物与关系','seed-character'],['outline','前三集大纲','seed-outline'],['scenes','首集分场','seed-scenes'],['script','首集剧本','seed-script']];
const STATUS={empty:'未开始',draft:'待确认',confirmed:'已确认',stale:'待检查'};
function stageText(v=current()){if(S.stage==='archived_review')return v?.route.archived_review?.text||'';return S.stage==='legacy'?(v?.route.legacy||''):(v?.route.documents[S.stage]?.text||'');}
function dirty(){return !!current() && $('document').value!==stageText();}
function remember(){localStorage.setItem('storyBranchSelection',JSON.stringify({pid:S.project.id,bid:S.branch,vid:S.version,stage:S.stage}));}
function selectStage(stage){if(S.busy||!canLeave())return;S.stage=stage;$('writing-mode').value='write';remember();render();const seed=STAGES.find(s=>s[0]===stage)?.[2]||'';$('prompt-select').value=seed;$('prompt-body').value=S.prompts.find(p=>p.id===seed)?.body||'';$('instruction').value='';}
function renderStages(){
  $('stages').replaceChildren(...STAGES.map(([id,label],i)=>{const b=node('button','stage-button'+(S.stage===id?' active':''));b.dataset.stage=id;b.append(node('b','',String(i+1).padStart(2,'0')+' · '+label),node('small','stage-'+current().stage_status[id],STATUS[current().stage_status[id]]));b.onclick=()=>selectStage(id);return b;}));
  if(current().route.legacy){const b=node('button','stage-button'+(S.stage==='legacy'?' active':''),'历史稿件 · 待人工整理');b.onclick=()=>selectStage('legacy');$('stages').append(b);}
  if(current().route.archived_review?.text){const b=node('button','stage-button'+(S.stage==='archived_review'?' active':''),'历史审阅 · 只读');b.onclick=()=>selectStage('archived_review');$('stages').append(b);}
  const label=STAGES.find(s=>s[0]===S.stage)?.[1]||(S.stage==='archived_review'?'历史审阅':'历史稿件');$('stage-title').textContent=label;
  const status=current().stage_status[S.stage];$('stage-status').textContent=STATUS[status]||'历史材料';
  const upstream=STAGES.slice(0,STAGES.findIndex(s=>s[0]===S.stage)).filter(s=>current().stage_status[s[0]]!=='confirmed');
  $('stage-guidance').textContent=S.stage==='archived_review'?'旧版审阅保留为只读资料；新审阅可在任意阶段通过“只审阅”任务进行。':S.stage==='legacy'?'旧版稿件保留在这里，可手动整理到对应阶段。':status==='stale'?'上游成果已经变化。请核对内容后确认沿用，或让 AI 更新本阶段。':upstream.length?'下一步：先检查并确认 '+upstream.map(s=>s[1]).join('、')+'。':S.stage==='concept'?'先生成三个候选，再用“选定 / 修改故事立意”保存唯一方向并确认。':S.stage==='script'?'本阶段产出首集英文剧本，并在文末附中文梗概。':'可自由讨论或编辑；确认成果后进入下一阶段。';
}
function canLeave(){return !dirty() || window.confirm('当前稿件有未保存修改，草稿会暂存在当前标签页。仍要切换？');}
function vlabel(id){return 'V'+(S.project.versions.findIndex(v=>v.id===id)+1);}
function headState(){
  const history=!!branch() && branch().head!==S.version;
  const readonly=history||S.stage==='archived_review';
  $('historical').hidden=!history;
  $('send-button').disabled=S.busy||readonly;
  $('save-document').disabled=S.busy||readonly;
  $('confirm-stage').disabled=S.busy||readonly||dirty()||S.stage==='legacy'||!stageText().trim()||current()?.stage_status[S.stage]==='confirmed';
  $('document').readOnly=S.busy||readonly;
  $('insert-template').disabled=S.busy||readonly||!S.writing?.contracts[S.stage];
  $('choose-concept').disabled=S.busy||readonly||dirty();
  $('instruction').disabled=S.busy||readonly;
  $('writing-mode').disabled=S.busy||readonly;
  $('dirty-status').textContent=readonly?'历史版本 · 只读':dirty()?'有未保存修改':'已保存';
}
async function run(work){
  if(S.busy)return;
  S.busy=true; const buttons=[...document.querySelectorAll('button')]; buttons.forEach(b=>b.disabled=true); headState();
  notify('处理中，请稍候。长篇生成可能需要数分钟，请保持页面打开。');
  try{await work();}catch(e){if(e.responseText){failedResponse=e.responseText;$('failed-text').textContent=failedResponse;$('failed-response').hidden=false;$('failed-response').open=true;}if(e.status===409&&dirty())$('recover-draft').hidden=false;notify(e.message,true);}finally{S.busy=false;buttons.forEach(b=>b.disabled=false);headState();}
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
  const changed=S.project?.id!==project.id;S.project=project; S.branch=project.branches.some(b=>b.id===bid)?bid:project.branches[0].id; S.version=vid&&project.versions.some(v=>v.id===vid)?vid:branch().head;if(changed){failedResponse='';$('failed-response').hidden=true;}
  remember();render();
}
function render(){
  renderProjects(); $('welcome').hidden=true;$('session').hidden=false;$('branch-section').hidden=false;$('document-panel').hidden=false;
  $('project-title').textContent=S.project.title;$('branch-label').textContent=branch().name+' / '+vlabel(S.version);$('brief-text').textContent=current().route.documents.brief.text;renderStages();renderPrompts();renderWriting();renderContract();
  $('branches').replaceChildren(...S.project.branches.map(b=>{
    const e=node('button','list-button'+(b.id===S.branch?' active':''));e.append(node('b','',b.name),node('small','muted',b.fork_version?'从 '+vlabel(b.fork_version)+' 分叉':'原始故事线'));
    e.onclick=()=>{if(!S.busy&&canLeave())load(S.project,b.id);};
    const row=node('div','branch-row');row.append(e);
    if(b.fork_version){const remove=node('button','delete-branch','删除');remove.setAttribute('aria-label','删除分支 '+b.name);remove.onclick=()=>{
      if(S.busy)return;
      if(b.id===S.branch&&dirty()){notify('当前分支有未保存修改，请先保存或另存分支。',true);return;}
      if(!window.confirm('删除分支“'+b.name+'”？全组将无法继续在此分支编辑。其他分支不受影响，共享的历史版本仍会保留。'))return;
      run(async()=>{const p=await api('/projects/'+S.project.id+'/branches/'+b.id+'/delete',{head:b.head});load(p,S.branch===b.id?undefined:S.branch,S.branch===b.id?undefined:S.version);notify('分支已删除，共享历史已保留。');});
    };row.append(remove);}return row;
  }));
  const versionScroll=$('versions').scrollTop;$('version-count').textContent=pathTo(branch().head).length+' 个版本';
  $('versions').replaceChildren(...pathTo(branch().head).slice().reverse().map(v=>{
    const b=node('button','version'+(v.id===S.version?' active':''));
    b.append(node('b','',vlabel(v.id)+' · '+(v.provider==='manual'?'人工记录':v.provider==='demo'?'样例生成':'DeepSeek')),node('span','',v.instruction.slice(0,60)));
    b.onclick=()=>{if(!S.busy&&canLeave())load(S.project,S.branch,v.id);};return b;
  }));
  $('versions').scrollTop=versionScroll;
  const history=pathTo(S.version);$('chat').replaceChildren();
  history.filter(v=>v.stage===(S.stage==='archived_review'?'review':S.stage)).forEach(v=>{
    const row=node('article','turn');row.append(node('div','turn-label',vlabel(v.id)+' · '+new Date(v.created_at).toLocaleString()));
    row.append(node('small','muted',v.author_name||'历史记录'),node('p','user-message',v.instruction),node('p','assistant-message',v.reply));$('chat').append(row);
  });
  $('document').value=stageText();
  const draft=sessionStorage.getItem(draftKey());
  if(draft!==null&&draft!==stageText()&&branch().head===S.version){$('document').value=draft;notify('已恢复此版本的未保存草稿。');}
  $('recover-draft').hidden=true;
  const revision=current().route.documents[S.stage]?.revision;const source=S.project.versions.find(v=>v.id===revision)||current();
  $('version-meta').textContent='路线 '+vlabel(S.version)+' · '+(source.provider==='demo'?'固定样例':source.provider==='manual'?'人工保存':source.model)+' · '+(source.author_name||'历史记录');
  $('provenance').textContent=JSON.stringify({provider:source.provider,model:source.model,content_version:revision,route_version:S.version,prompt:JSON.parse(source.prompt_json),selected_event_prompt:JSON.parse(current().prompt_json),stage:S.stage,dependencies:current().route.documents[S.stage]?.dependencies},null,2);
  const reachable=new Set(S.project.branches.flatMap(b=>pathTo(b.head).map(v=>v.id)));const others=S.project.versions.filter(v=>v.id!==S.version&&reachable.has(v.id));
  $('compare-select').replaceChildren(node('option','','请选择对照版本'),...others.map(v=>{const o=node('option','',vlabel(v.id)+' · '+v.instruction.slice(0,30));o.value=v.id;return o;}));
  $('compare-select').options[0].value='';$('compare-select').value=current().parent_id||'';compare();headState();
  $('chat').scrollTop=$('chat').scrollHeight;
}
function compare(){const v=S.project?.versions.find(v=>v.id===$('compare-select').value);$('compare-content').textContent=v?((stageText(v)||'此版本的当前阶段尚无稿件。')+(S.stage==='concept'?'\n\n人工选定立意：\n'+(v.route.selected_concept||'尚未选定'):'')):'选择历史版本，在这里对照阅读。';}
function renderWriting(){
  const polish=$('writing-mode').querySelector('option[value="polish"]');polish.disabled=S.stage!=='script';
  if(polish.disabled&&$('writing-mode').value==='polish')$('writing-mode').value='write';
  const mode=$('writing-mode').value;
  const hints={write:'生成或修改当前阶段；其他阶段保持原样。',discuss:'只记录讨论回复，服务器保持稿件和确认状态不变。',critique:'只给出有依据的修改意见，服务器保持稿件不变。',polish:'润色首集英文对白，保留剧情和人物设定，保存完整新版本。'};
  $('writing-hint').textContent=hints[mode];
  const skills=[...(S.writing?.stages[S.stage]||[])];
  if(mode==='critique'&&!skills.some(s=>s.id==='notes')){const notes=S.writing?.review_skills.find(s=>s.id==='notes');if(notes)skills.push(notes);}
  $('writing-methods').replaceChildren(node('p','muted small','按阶段使用已审阅的写作方法；生成质量仍需实际试写验证。'),...skills.map(s=>{const p=node('p','small'),a=node('a','',s.title+' · MIT 来源');a.href=s.source;a.target='_blank';a.rel='noopener noreferrer';p.append(a);return p;}));
  if(!skills.length)$('writing-methods').append(node('p','small','创作约束与待确认事项整理。'));
}
$('writing-mode').onchange=renderWriting;
function renderPrompts(){
  const selected=$('prompt-select').value;
  const available=S.prompts.filter(p=>!S.project||(p.stages||[]).includes(S.stage));
  $('prompt-select').replaceChildren(new Option('自由对话',''),...available.map(p=>new Option(p.title,p.id)));
  $('prompt-select').value=available.some(p=>p.id===selected)?selected:'';
  if(selected&&!$('prompt-select').value)$('prompt-body').value='';
  $('library').replaceChildren(...available.map(p=>{
    const card=node('article','prompt-card');card.append(node('span','badge',p.category+' · '+(p.builtin?'内置':'小组')),node('h3','',p.title),node('p','',p.body));
    const actions=node('div','label-row'); const use=node('button','primary','应用到本轮');use.onclick=()=>{if(!S.project){notify('请先创建或打开项目。',true);return;}if(S.busy)return;$('prompt-select').value=p.id;$('prompt-body').value=p.body;if(p.id==='seed-doctor'){$('writing-mode').value='critique';renderWriting();}$('library-dialog').close();notify('已应用提示词，可在发送前调整。');};
    const copy=node('button','','修改并另存');copy.onclick=()=>{template(p.title+' · 改版',p.category,p.body);};actions.append(copy,use);card.append(actions);return card;
  }));
}
function template(title,category,body){$('template-title').value=title;$('template-category').value=category;$('template-body').value=body;$('template-stage').replaceChildren(new Option('所有阶段（受各阶段边界约束）',''),...STAGES.map(([id,label])=>new Option(label,id)));$('template-stage').value=STAGES.some(([id])=>id===S.stage)?S.stage:'';$('template-dialog').showModal();}
function renderSettings(){
  $('mode').textContent=S.settings.mode==='demo'?'样例模式 · 固定内容':'DeepSeek · 已配置';
  $('send-hint').textContent=S.settings.mode==='demo'?'固定样例，仅验证流程':'发送将调用 DeepSeek，并保存完整新版本';
  $('max-tokens').value=S.settings.max_tokens||81920;$('provider').value=S.settings.mode;$('model-name').value=S.settings.model;
  $('key-status').textContent=S.settings.configured?'已有密钥配置；实际连通性以生成请求为准。':'尚未配置密钥。';
}
document.querySelectorAll('[data-close]').forEach(b=>b.onclick=()=>{if(!S.busy)$(b.dataset.close).close();});
['new-button','welcome-new'].forEach(id=>$(id).onclick=()=>{if(canLeave())$('new-dialog').showModal();});
$('library-button').onclick=()=>$('library-dialog').showModal();
$('settings-button').onclick=()=>{$('api-key').value='';renderSettings();$('settings-dialog').showModal();};
$('settings-dialog').addEventListener('close',()=>{$('api-key').value='';});
$('settings-form').onsubmit=e=>{e.preventDefault();run(async()=>{
  const key=$('api-key').value.trim();$('api-key').value='';
  S.settings=await api('/settings',{mode:$('provider').value,model:$('model-name').value,max_tokens:Number($('max-tokens').value),api_key:key});renderSettings();$('settings-dialog').close();notify('配置已保存。可发送创作需求；本次未发起模型调用。');
});};
$('clear-key').onclick=()=>run(async()=>{S.settings=await api('/settings',{mode:'demo',model:$('model-name').value,clear_key:true});$('api-key').value='';renderSettings();notify('密钥已从当前服务内存清除。');});
$('new-form').onsubmit=e=>{e.preventDefault();const data=Object.fromEntries(new FormData(e.target));run(async()=>{const p=await api('/projects',data);S.projects=await api('/projects');S.stage='brief';$('writing-mode').value='write';$('prompt-select').value='';$('prompt-body').value='';$('instruction').value='';load(p);$('new-dialog').close();notify('项目已创建，选择指南并开始对话。');});};
$('prompt-select').onchange=()=>{$('prompt-body').value=S.prompts.find(p=>p.id===$('prompt-select').value)?.body||'';if($('prompt-select').value==='seed-doctor'){$('writing-mode').value='critique';renderWriting();}};
$('save-template').onclick=()=>template(S.prompts.find(p=>p.id===$('prompt-select').value)?.title||'我的创作指南','自定义',$('prompt-body').value);
$('template-form').onsubmit=e=>{e.preventDefault();run(async()=>{const p=await api('/prompts',{title:$('template-title').value,category:$('template-category').value,body:$('template-body').value,stage:$('template-stage').value});S.prompts=await api('/prompts');renderPrompts();if(!p.stage||p.stage===S.stage){$('prompt-select').value=p.id;$('prompt-body').value=p.body;}$('template-dialog').close();notify('小组模板已保存，在适用阶段可以使用。');});};
$('chat-form').onsubmit=e=>{e.preventDefault();if(dirty()){notify('请先保存稿件修改，再发送创作需求。',true);return;}run(async()=>{
  const title=S.prompts.find(p=>p.id===$('prompt-select').value)?.title||'自由对话';const taskMode=$('writing-mode').value;
  const p=await api('/projects/'+S.project.id+'/versions',{action:'chat',stage:S.stage,writing_mode:taskMode,branch_id:S.branch,parent_id:S.version,instruction:$('instruction').value,prompt_title:title,prompt_body:$('prompt-body').value});
  load(p,p.recovered_branch_id||S.branch);$('instruction').value='';notify(p.recovered_branch_id?'其他成员已更新原分支，生成结果已保留为独立分支。':['discuss','critique'].includes(taskMode)?'回复已记录，稿件保持不变。':'回复与稿件已保存为 '+vlabel(S.version)+'。');
});};
$('save-document').onclick=()=>run(async()=>{
  if(!dirty())throw new Error('稿件没有变化。');
  const key=draftKey();const p=await api('/projects/'+S.project.id+'/versions',{action:'edit',stage:S.stage,branch_id:S.branch,parent_id:S.version,instruction:'人工修改稿件',document:$('document').value});sessionStorage.removeItem(key);load(p,S.branch);notify('人工修改已保存为新版本。');
});
function draftKey(){return 'storyDraft:'+S.user?.id+':'+S.project?.id+':'+S.branch+':'+S.version+':'+S.stage;}
$('document').oninput=()=>{if(dirty())sessionStorage.setItem(draftKey(),$('document').value);else sessionStorage.removeItem(draftKey());headState();};$('compare-select').onchange=compare;
$('recover-draft').onclick=()=>run(async()=>{
  const document=$('document').value,key=draftKey(),head=S.version;
  const fork=await api('/projects/'+S.project.id+'/branches',{version_id:head,name:'冲突草稿 · '+S.user.name+' · '+new Date().toLocaleTimeString()});
  const p=await api('/projects/'+S.project.id+'/versions',{action:'edit',stage:S.stage,branch_id:fork.branch_id,parent_id:head,instruction:'保留并发修改草稿',document});
  sessionStorage.removeItem(key);load(p,fork.branch_id);notify('草稿已另存为分支，原分支未被覆盖。');
});
$('fork-button').onclick=()=>{if(!canLeave())return;$('fork-source').textContent='从 '+vlabel(S.version)+' 创建分支。将继承该版本的全部阶段成果、确认状态和对话。';$('fork-name').value='';$('fork-dialog').showModal();};
$('fork-form').onsubmit=e=>{e.preventDefault();run(async()=>{const result=await api('/projects/'+S.project.id+'/branches',{version_id:S.version,name:$('fork-name').value});load(result.project,result.branch_id);$('fork-dialog').close();notify('新分支已创建，原分支的后续版本保持独立。');});};
$('refresh-button').onclick=()=>{if(canLeave())run(async()=>{load(await api('/projects/'+S.project.id),S.branch);notify('已读取最新版本。');});};
$('export-button').onclick=()=>{
  if(dirty()){notify('请先保存稿件修改再导出。',true);return;}
  const v=current(); const content='# '+S.project.title+'\n\n路线：'+branch().name+' / '+vlabel(v.id)+'\n\n'+STAGES.map(([id,label])=>'## '+label+'（'+STATUS[v.stage_status[id]]+'）\n\n'+(v.route.documents[id].text||'尚未开始')).join('\n\n')+(v.route.selected_concept?'\n\n## 人工选定立意\n\n'+v.route.selected_concept:'')+(v.route.archived_review?.text?'\n\n## 历史审阅（旧版）\n\n'+v.route.archived_review.text:'')+reviewExport()+(v.route.legacy?'\n\n## 历史稿件\n\n'+v.route.legacy:'');
  const url=URL.createObjectURL(new Blob([content],{type:'text/markdown;charset=utf-8'})), a=node('a');a.href=url;a.download='story-'+vlabel(v.id)+'.md';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
};
window.addEventListener('beforeunload',e=>{if(dirty()||S.busy){e.preventDefault();e.returnValue='';}});
async function boot(){
  const response=await fetch('/api/auth/me');if(response.status===401){location.replace('/login');return;}if(!response.ok)throw new Error('无法读取登录状态。');S.user=await response.json();
  $('user-name').textContent=S.user.name;$('settings-button').hidden=S.user.role!=='admin';
  [S.projects,S.prompts,S.settings,S.writing]=await Promise.all([api('/projects'),api('/prompts'),api('/settings'),api('/writing')]);renderProjects();renderPrompts();renderSettings();
  let saved;try{saved=JSON.parse(localStorage.getItem('storyBranchSelection'));}catch{}
  if(saved&&STAGES.some(s=>s[0]===saved.stage))S.stage=saved.stage;
  if(saved&&S.projects.some(p=>p.id===saved.pid)){const p=await api('/projects/'+saved.pid);const b=p.branches.find(b=>b.id===saved.bid)||p.branches[0];load(p,b.id,p.versions.some(v=>v.id===saved.vid)?saved.vid:b.head);}
  notify('工作台已就绪。');
}
$('confirm-stage').onclick=()=>run(async()=>{if(dirty())throw new Error('请先保存修改。');const p=await api('/projects/'+S.project.id+'/versions',{action:'confirm',stage:S.stage,branch_id:S.branch,parent_id:S.version});load(p,S.branch);notify('本阶段成果已确认，可以进入下一阶段。');});
$('download-failed').onclick=()=>{const url=URL.createObjectURL(new Blob([failedResponse],{type:'text/plain;charset=utf-8'})),a=node('a');a.href=url;a.download='未保存的模型返回.txt';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
$('logout-button').onclick=async()=>{if(!canLeave())return;const r=await fetch('/api/auth/logout',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});if(r.ok||r.status===401){sessionStorage.clear();location.assign('/login');}else notify('退出失败，请重试。',true);};

function reviewEvents(){return S.project?pathTo(S.version).filter(v=>JSON.parse(v.prompt_json).writing?.mode==='critique'):[];}
function reviewExport(){return reviewEvents().map(v=>'\n\n## 审阅 · '+(STAGES.find(s=>s[0]===v.stage)?.[1]||v.stage)+' / '+vlabel(v.id)+'\n\n'+v.reply).join('');}
function renderContract(){
  const c=S.writing?.contracts[S.stage];document.querySelector('.stage-contract').hidden=!c;
  $('contract-role').textContent=c?.role||'';$('contract-boundary').textContent=c?'边界：'+c.boundary:'';
  const checks=current()?.stage_checks[S.stage]||[];
  $('stage-checks').replaceChildren(...(checks.length?checks:['结构检查通过；请审阅内容后人工确认。']).map(t=>node('li','',t)));
  $('concept-choice').hidden=S.stage!=='concept';$('selected-concept').textContent=current()?.route.selected_concept||'尚未选定。候选文本更新后，需要重新选定。';
  $('migration-notice').textContent=current()?.route.migration_notice||'';$('migration-notice').hidden=!current()?.route.migration_notice;
  const reviews=reviewEvents();$('review-log').replaceChildren(...reviews.map(v=>{const d=node('details');d.append(node('summary','',(STAGES.find(s=>s[0]===v.stage)?.[1]||v.stage)+' · '+vlabel(v.id)),node('p','assistant-message',v.reply));return d;}));
  if(!reviews.length)$('review-log').append(node('p','muted small','选择“只审阅，不改稿”即可记录当前阶段意见。'));
}
$('insert-template').onclick=()=>{
  const c=S.writing?.contracts[S.stage];if(!c||S.busy||$('document').readOnly)return;
  const existing=new Set($('document').value.split(/\r?\n/).filter(l=>l.startsWith('## ')).map(l=>l.slice(3).trim()));
  const missing=c.sections.filter(t=>!existing.has(t));if(!missing.length){notify('段落标题已齐全，请填写内容。');return;}
  $('document').value+=($('document').value?'\n\n':'')+missing.map(t=>'## '+t+'\n[待填写]').join('\n\n');$('document').oninput();notify('已补入缺失标题，请整理内容并保存。');
};
$('choose-concept').onclick=()=>{if(dirty()){notify('请先保存候选稿件。',true);return;}$('selection-text').value=sessionStorage.getItem(draftKey()+':selection')??current().route.selected_concept??'';$('selection-dialog').showModal();};
$('selection-text').oninput=()=>sessionStorage.setItem(draftKey()+':selection',$('selection-text').value);
$('selection-form').onsubmit=e=>{e.preventDefault();run(async()=>{const key=draftKey()+':selection';const p=await api('/projects/'+S.project.id+'/versions',{action:'select_concept',stage:'concept',branch_id:S.branch,parent_id:S.version,selection:$('selection-text').value});sessionStorage.removeItem(key);load(p,S.branch);$('selection-dialog').close();notify('选定立意已保存，请检查并确认本阶段。');});};
boot().catch(e=>notify('加载失败：'+e.message,true));
