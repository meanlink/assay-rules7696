import time, os, csv, io, hashlib, json
from fastapi import HTTPException
from sqlalchemy import select
from src.models import Dataset, Job, Report, Delivery
from src.config.settings import ARTIFACT_DIR
from src.services.validity import locked_chain as _locked_chain, invalidity

def create(db, data):
    if not db.get(Job,data.job_id):
        raise HTTPException(409,'请先选择已完成且获批准的分析结果')
    d, j = _locked_chain(db, data.job_id)
    reason=invalidity(d,j)
    if reason:
        raise HTTPException(409,f'该分析结果已因批次停用而失效，不能创建分发计划。原因：{reason}')
    if j.status!='completed' or not j.approved:
        raise HTTPException(409,'请先选择已完成且获批准的分析结果')
    r=Report(name=data.name, job_id=j.id, destination=data.destination, interval_seconds=data.interval_seconds, next_run=time.time()+data.delay_seconds, enabled=True)
    db.add(r); db.flush()
    return r

def deliver(db, report):
    # Same order as retirement: dataset -> job -> report.
    j0=db.get(Job,report.job_id)
    if not j0: return None
    d, j = _locked_chain(db, report.job_id)
    r=db.scalar(select(Report).where(Report.id==report.id).with_for_update())
    if r is None: return None
    reason=invalidity(d,j)
    if reason or r.invalidated_at is not None or not r.enabled or not j.approved:
        if r.invalidated_at is None and reason:
            r.invalidated_at=time.time(); r.invalidated_reason=reason
        r.enabled=False
        return None
    out=io.StringIO()
    out.write('\ufeff')
    table=j.result.get('table',{})
    cols=table.get('columns',[])
    writer=csv.writer(out)
    def safe(v):
        if isinstance(v,(int,float)) and not isinstance(v,bool): return v
        text=str(v)
        return "'"+text if text.startswith(('=','+','-','@','\t','\r')) else text
    writer.writerow([safe(c['label']) for c in cols])
    for row in table.get('rows',[]): writer.writerow([safe(row.get(c['key'],'')) for c in cols])
    data=out.getvalue().encode('utf-8')
    delivery=Delivery(report_id=r.id, created_at=time.time(), checksum=hashlib.sha256(data).hexdigest(), filename='', destination=r.destination)
    db.add(delivery); db.flush()
    delivery.filename=f'report-{r.id}-delivery-{delivery.id}.csv'
    os.makedirs(ARTIFACT_DIR,exist_ok=True)
    with open(os.path.join(ARTIFACT_DIR,delivery.filename),'wb') as f:f.write(data)
    with open(os.path.join(ARTIFACT_DIR,delivery.filename+'.json'),'w') as f: json.dump({'job':j.name,'params':j.params,'result':j.result,'checksum':delivery.checksum},f,ensure_ascii=False,allow_nan=False)
    r.next_run=time.time()+r.interval_seconds
    return delivery
