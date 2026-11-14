import {jobs} from '../api/entities.js';
import {workspace} from '../stores/workspace.js';
import {session} from '../stores/session.js';
import {heading} from '../components/common/shell.js';
import {chart} from '../components/common/chart.js';
import {table} from '../components/common/table.js';
import {status} from '../components/common/status.js';
import {esc,fmt,date,notify} from '../utils/dom.js';

export function invalidationNotice(j){
 if(!j.invalidated)return '';
 return '<p class="warning"><strong>结果已失效，仅供追溯，不能批准、分发或下载。</strong><br>停用原因：'+esc(j.invalidated_reason||'关联数据批次已停用')+'<br>失效时间：'+date(j.invalidated_at||0)+(j.invalidated_by?' · '+esc(j.invalidated_by):'')+'</p>';
}

export async function results(id){
 workspace.jobs=await jobs.list();const j=id?await jobs.get(id):(workspace.jobs.find(j=>j.id===workspace.selectedJob)||workspace.jobs[0]);
 if(j&&!workspace.jobs.some(x=>x.id===j.id))workspace.jobs.push(j);
 if(!j)return heading('04 / REVIEW','结果复核','尚无分析结果。')+'<div class="empty">先到分析工作台，选择批次并提交一次计算。<a href="#/workbench">前往工作台 ↗</a></div>';
 workspace.selectedJob=j.id;const r=j.result||{},invalid=j.invalidated;
 const headingAction='<button class="button" id="refresh-results">刷新结果 ↻</button>';
 const selector='<div class="result-selector"><label>分析记录<select id="select-job">'+workspace.jobs.map(x=>'<option value="'+x.id+'" '+(x.id===j.id?'selected':'')+'>'+esc(x.name)+' · '+esc(x.status+(x.invalidated?'/失效':''))+'</option>').join('')+'</select></label>'+status(j.status)+'<span>'+date(j.created_at)+'</span><span class="approval">'+(invalid?'已失效':(j.approved?'已获业务批准':'待负责人复核'))+'</span></div>';
 const approveButton=(session.user.role==='admin'&&!j.approved&&!invalid)?'<button class="primary" id="approve-job">批准此业务结论</button>':'';
 const approveHint=invalid?'<p class="warning">该结果已因批次停用而失效，批准入口已关闭，原值保留供追溯。</p>':'<p class="hint">仅批准结果可进入定时分发档案。</p>';
 const computed=(j.status==='completed'||invalid&&r.summary)?'<section class="result-lead"><p class="eyebrow">COMPUTED FINDING'+(invalid?' / INVALIDATED':'')+'</p><h2>'+esc(r.summary)+'</h2><div class="metrics">'+(r.metrics||[]).map(m=>'<div><span>'+esc(m.label)+'</span><strong>'+esc(fmt(m.value))+'<small>'+esc(m.unit||'')+'</small></strong></div>').join('')+'</div></section><section class="panel">'+chart(r.chart)+'</section><div class="two-columns"><section class="panel"><div class="section-title"><h2>业务解释</h2><span>'+(invalid?'历史结果 · 已失效':'由计算结果生成')+'</span></div><ol class="questions">'+(r.findings||[]).map(v=>'<li>'+esc(v)+'</li>').join('')+'</ol>'+(r.warnings||[]).map(v=>'<p class="warning">'+esc(v)+'</p>').join('')+'</section><section class="method-sheet compact"><p class="eyebrow">REPRODUCIBILITY</p><h3>计算口径与参数</h3><p>'+esc(r.method)+'</p><pre>'+esc(JSON.stringify(j.params,null,2))+'</pre>'+approveButton+approveHint+'</section></div><section class="panel"><div class="section-title"><h2>结果明细</h2><span>'+(r.table?.rows?.length||0)+' 行</span></div>'+table(r.table?.columns||[],r.table?.rows||[])+'</section>':'<section class="panel empty">'+(j.status==='invalidated'?'该结果因批次停用而失效，没有可用的计算结果。':(j.status==='failed'?'计算失败：'+esc(j.error)+'。请返回工作台调整参数或数据。':'后台正在执行计算。点击刷新结果查看最新进展。'))+'<a href="#/workbench">返回工作台 ↗</a></section>';
 return heading('04 / REVIEW','结果复核与业务解释',j.name,headingAction)+selector+invalidationNotice(j)+computed;
}
export function bindResults(refresh){document.querySelector('#refresh-results')?.addEventListener('click',refresh);document.querySelector('#select-job')?.addEventListener('change',e=>{workspace.selectedJob=Number(e.target.value);location.hash='#/results/'+e.target.value;});document.querySelector('#approve-job')?.addEventListener('click',async()=>{try{await jobs.approve(workspace.selectedJob);notify('已批准，可创建分发计划');await refresh();}catch(e){notify(e.message,true);}});}
