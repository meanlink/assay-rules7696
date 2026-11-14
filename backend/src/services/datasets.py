from fastapi import HTTPException
from sqlalchemy import select
from src.models import Dataset, Job, Report, Delivery
from src.services.business import metadata
from src.services.audit import record
from src.utils.serialization import checksum, dataset_dict, job_dict, report_dict, delivery_dict
import math, time

def create(db, data):
    name=data.name.strip()
    if len(name)<2: raise HTTPException(422, '批次名称去除空格后至少需要两个字符')
    if db.scalar(select(Dataset).where(Dataset.name==name)):
        raise HTTPException(409, '该数据批次名已存在，请修改名称')
    for index,row in enumerate(data.records):
        for c in metadata()['columns']:
            value=row.get(c['key'])
            if value is None or value=='': raise HTTPException(422, f'第 {index+1} 行缺少字段 {c["label"]}')
            if c['type']=='number':
                try:
                    if isinstance(value,bool) or not math.isfinite(float(value)): raise ValueError()
                    row[c['key']]=float(value)
                except (TypeError, ValueError, OverflowError): raise HTTPException(422, f'第 {index+1} 行 {c["label"]} 必须为有限数值')
    d=Dataset(name=name, source=data.source, records=data.records, checksum=checksum(data.records), created_at=time.time())
    db.add(d); db.flush()
    return d

def affected_entities(db, dataset, for_update=False):
    """Retirement scope: every job of the batch, its plans, and archived deliveries.
    Completed results keep their computed values; they are only marked unusable.
    for_update serializes retirement with a worker finishing the same row."""
    job_stmt=select(Job).where(Job.dataset_id==dataset.id).order_by(Job.id)
    jobs=list(db.scalars(job_stmt.with_for_update() if for_update else job_stmt))
    job_ids=[j.id for j in jobs]
    plans=list(db.scalars(select(Report).where(Report.job_id.in_(job_ids)).order_by(Report.id))) if job_ids else []
    plan_ids=[r.id for r in plans]
    deliveries=list(db.scalars(select(Delivery).where(Delivery.report_id.in_(plan_ids)).order_by(Delivery.id))) if plan_ids else []
    return jobs, plans, deliveries

def impact(db, dataset):
    jobs, plans, deliveries = affected_entities(db, dataset)
    retired_fields = {'retired': dataset.retired_at is not None, 'retired_at': dataset.retired_at,
                      'retired_by': dataset.retired_by, 'retire_reason': dataset.retire_reason}
    job_rows=[]
    for j in jobs:
        row=job_dict(j)
        row['usable']=dataset.retired_at is None and j.invalidated_at is None
        row['blocked_reason']=dataset.retire_reason if dataset.retired_at is not None else None
        job_rows.append(row)
    plan_rows=[report_dict(r) for r in plans]
    delivery_rows=[delivery_dict(d, dataset.retired_at is not None or any(p.id==d.report_id and p.invalidated_at is not None for p in plans),
                                 dataset.retire_reason or '关联分析结果已停用') for d in deliveries]
    return {'dataset': {**dataset_dict(dataset), **retired_fields}, 'jobs': job_rows, 'reports': plan_rows,
            'deliveries': delivery_rows,
            'counts': {'jobs': len(job_rows), 'jobs_invalidated': sum(1 for j in job_rows if not j['usable']),
                       'reports': len(plan_rows), 'reports_invalidated': sum(1 for r in plan_rows if r['invalidated']),
                       'deliveries': len(delivery_rows), 'deliveries_blocked': sum(1 for d in delivery_rows if d['invalidated'])}}

def retire(db, dataset_id, reason, actor):
    reason=reason.strip()
    if len(reason)<2: raise HTTPException(422, '请填写至少两个字符的停用原因')
    d=db.scalar(select(Dataset).where(Dataset.id==dataset_id).with_for_update())
    if not d: raise HTTPException(404, '数据批次不存在')
    if d.retired_at is not None:
        raise HTTPException(409, f'该批次已于 {time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(d.retired_at))} 停用，原因：{d.retire_reason}')
    now=time.time()
    d.retired_at=now; d.retired_by=actor; d.retire_reason=reason
    jobs, plans, deliveries = affected_entities(db, d, for_update=True)
    for j in jobs:
        if j.invalidated_at is None:
            j.invalidated_at=now; j.invalidated_by=actor; j.invalidated_reason=reason
        # Queued/running work can never publish a usable result again; completed rows keep their values.
        if j.status in ('queued','running'): j.status='invalidated'
        record(db, actor, 'job.invalidated', {'id':j.id, 'dataset_id':d.id, 'reason':reason,
            'status':j.status, 'result_preserved':j.status=='completed'})
    for r in plans:
        if r.invalidated_at is None:
            r.invalidated_at=now; r.invalidated_reason=reason
        r.enabled=False
    record(db, actor, 'dataset.retire', {'id':d.id, 'name':d.name, 'reason':reason,
        'jobs':[j.id for j in jobs], 'jobs_queued_or_running':[j.id for j in jobs if j.status=='invalidated'],
        'reports':[r.id for r in plans], 'deliveries':[x.id for x in deliveries],
        'completed_preserved':[j.id for j in jobs if j.status=='completed']})
    return d
