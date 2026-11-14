import {datasets} from '../api/entities.js';
import {workspace} from '../stores/workspace.js';
import {session} from '../stores/session.js';
import {heading} from '../components/common/shell.js';
import {table} from '../components/common/table.js';
import {JobStatus} from '../constants/enums.js';
import {esc,date,notify} from '../utils/dom.js';
import {submit} from '../hooks/forms.js';
import {parseCSV} from '../utils/csv.js';

const batchState=d=>d.retired
 ?'<p class="warning"><strong>已停用</strong> · '+date(d.retired_at)+' · '+esc(d.retired_by||'')+'<br>停用原因：'+esc(d.retire_reason||'—')+'</p>'
 :'<p class="hint">批次可用。停用后将拒绝该批次的新分析，并使该批次已排队、计算中、已完成的分析及其分发计划、归档全部失效；已完成结果保留原值供追溯。</p>';

function impactHtml(impact,loggedIn){
 const c=impact.counts;
 const jobCols=[{key:'name',label:'分析任务'},{key:'status',label:'状态'},{key:'usable',label:'可用'},{key:'reason',label:'失效原因'}];
 const jobs=impact.jobs.map(j=>({name:j.name,status:JobStatus[j.status]||j.status,usable:j.usable?'可用':'失效',reason:j.invalidated?(j.invalidated_reason||'—'):'—'}));
 const planCols=[{key:'name',label:'分发计划'},{key:'enabled',label:'启用'},{key:'invalidated',label:'失效'},{key:'reason',label:'失效原因'}];
 const plans=impact.reports.map(r=>({name:r.name,enabled:r.enabled?'是':'否',invalidated:r.invalidated?'是':'否',reason:r.invalidated?(r.invalidated_reason||'—'):'—'}));
 const delCols=[{key:'filename',label:'归档文件'},{key:'created_at',label:'生成时间'},{key:'downloadable',label:'可下载'}];
 const dels=impact.deliveries.map(d=>({filename:d.filename,created_at:date(d.created_at),downloadable:d.downloadable?'可下载':'已拦截'}));
 return '<section class="panel"><div class="section-title"><h2>批次状态与影响清单</h2><span>分析 '+c.jobs+' · 计划 '+c.reports+' · 归档 '+c.deliveries+'</span></div>'+batchState(impact.dataset)
 +'<div class="section-title"><h3>关联分析任务 ('+c.jobs_invalidated+'/'+c.jobs+' 失效)</h3></div>'+table(jobCols,jobs,'该批次尚无分析任务。')
 +'<div class="section-title"><h3>关联分发计划 ('+c.reports_invalidated+'/'+c.reports+' 失效)</h3></div>'+table(planCols,plans,'该批次尚无分发计划。')
 +'<div class="section-title"><h3>关联归档 ('+c.deliveries_blocked+'/'+c.deliveries+' 已拦截)</h3></div>'+table(delCols,dels,'该批次尚无归档。')
 +(loggedIn&&!impact.dataset.retired?'<form id="retire-form"><label>停用原因（必填，会写入审计与所有受影响结果）<textarea name="reason" rows="3" required minlength="2" placeholder="例如：仪器校准错误导致整批数据污染"></textarea></label><button type="submit" class="primary" id="retire-button">停用整批数据</button></form>':'')
 +(impact.dataset.retired?'<p class="hint">该批次已停用，结果、计划与归档均不可批准、分发或下载；原值保留供追溯。':'')+'</section>';
}

export async function dataPage(){
 workspace.datasets=await datasets.list();const m=workspace.meta;
 const first=workspace.datasets[0];
 const selected=first?await datasets.get(first.id):null;
 const impact=first?await datasets.impact(first.id):null;
 const canRetire=session.user.role==='admin';
 return heading('02 / DATA INTAKE','数据接入与批次追溯','保留原始业务字段、来源和内容指纹。分析任务始终绑定一个不可变数据批次；受污染批次可带原因整批停用。')+'<div class="dataset-grid"><section class="panel"><div class="section-title"><h2>业务批次</h2><span>'+workspace.datasets.length+' 批</span></div><div class="batch-list">'+workspace.datasets.map(d=>'<button class="batch-item" data-dataset="'+d.id+'"><strong>'+esc(d.name)+(d.retired?' · 已停用':'')+'</strong><span>'+d.rows+' 条 · '+esc(d.source)+'</span>'+(d.retired?'<small>停用原因：'+esc(d.retire_reason||'—')+'</small>':'')+'<small>SHA256 '+esc(d.checksum.slice(0,18))+'…</small></button>').join('')+'</div><div class="section-title"><h2>接入新数据</h2></div><form id="dataset-form"><label>批次名称<input name="name" required minlength="2" placeholder="例如：11 月复测批次"></label><label>上传 CSV 或 JSON<input type="file" id="file-input" accept=".json,.csv"></label><label>记录 JSON<textarea name="records" rows="6" placeholder="粘贴 JSON 数组，或先选择上方文件" required></textarea></label><p class="hint">字段：'+m.columns.map(c=>esc(c.key)+' / '+esc(c.label)).join('，')+'。5–5,000 条记录。</p><button type="submit" class="primary" '+(session.user.role==='viewer'?'disabled':'')+'>校验并接入批次</button></form></section><section><section class="panel"><div class="section-title"><h2 id="preview-name">'+esc(selected?.name||'尚无批次')+'</h2><span>预览前 30 条</span></div><div id="data-preview">'+table(m.columns,selected?.records.slice(0,30)||[])+'</div></section><div id="impact-panel">'+(impact?impactHtml(impact,canRetire):'')+'</div></section></div>';
}

function bindRetire(refresh){
 const form=document.querySelector('#retire-form');
 if(!form)return;
 const datasetId=form.dataset.datasetId;
 submit(form,async f=>{
  const reason=String(f.get('reason')||'').trim();
  if(!window.confirm('停用将拒绝该批次的新分析，并使关联的分析、计划和归档全部失效。确认停用？'))return;
  await datasets.retire(datasetId,reason);
  notify('批次已停用，关联分析与归档已失效');
  await refresh();
 });
}

export function bindData(refresh){
 let source='manual.json';
 document.querySelector('#file-input').addEventListener('change',async e=>{try{const file=e.target.files[0];if(!file)return;source=file.name;const text=await file.text(),records=file.name.endsWith('.csv')?parseCSV(text):JSON.parse(text);document.querySelector('[name=records]').value=JSON.stringify(records,null,2);}catch(error){notify(error.message,true);}});
 document.querySelectorAll('[data-dataset]').forEach(button=>button.onclick=async()=>{
  try{
   const id=button.dataset.dataset;
   const [d,impact]=await Promise.all([datasets.get(id),datasets.impact(id)]);
   document.querySelector('#preview-name').textContent=d.name;
   document.querySelector('#data-preview').innerHTML=table(workspace.meta.columns,d.records.slice(0,30));
   document.querySelector('#impact-panel').innerHTML=impactHtml(impact,session.user.role==='admin');
   const form=document.querySelector('#retire-form');
   if(form){form.dataset.datasetId=id;bindRetire(refresh);}
  }catch(error){notify(error.message,true);}
 });
 const form=document.querySelector('#retire-form');
 if(form){form.dataset.datasetId=workspace.datasets[0]?.id??'';bindRetire(refresh);}
 submit(document.querySelector('#dataset-form'),async f=>{await datasets.create({name:f.get('name'),source,records:JSON.parse(f.get('records'))});notify('数据已接入，可前往工作台执行分析');await refresh();});
}
