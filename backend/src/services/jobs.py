import time
from fastapi import HTTPException
from redis import Redis
from sqlalchemy import select
from src.config.settings import REDIS_URL
from src.models import Dataset, Job
from src.services.business import metadata
from src.services.validity import locked_chain, invalidity
from src.utils.serialization import job_dict
def create(db, data, user):
    # Lock the batch so the retirement transaction and a new analysis cannot interleave:
    # whichever commits first wins, and a committed retirement rejects the submission.
    d=db.scalar(select(Dataset).where(Dataset.id==data.dataset_id).with_for_update())
    if not d: raise HTTPException(404,'数据批次不存在')
    if d.retired_at is not None: raise HTTPException(409,f'该数据批次已停用，不再接受新分析。停用原因：{d.retire_reason}')
    allowed={p['key']:p for p in metadata().get('parameters',[])}
    if set(data.params)-set(allowed): raise HTTPException(422,'包含未知分析参数')
    params={k:p['default'] for k,p in allowed.items()}
    params.update(data.params)
    for key,p in allowed.items():
        v=params[key]
        if p['type']=='number':
            try:
                v=float(v)
                if not (p.get('min',-1e9)<=v<=p.get('max',1e9)): raise ValueError()
                params[key]=v
            except (ValueError,TypeError): raise HTTPException(422, f'{p["label"]} 超出范围或非数值')
        elif str(v) not in [str(o['value']) for o in p.get('options',[])]:
            raise HTTPException(422,f'{p["label"]} 不是有效选项')
    j=Job(name=data.name, dataset_id=data.dataset_id, params=params, created_by=user.id, created_at=time.time(), status='queued')
    db.add(j); db.flush()
    return j
def enqueue(job_id):
    try:
        r=Redis.from_url(REDIS_URL); r.rpush('analysis:queue',job_id); r.close()
    except Exception:
        pass # SQL queued status is the durable fallback
def approve(db, job_id, user):
    d,j=locked_chain(db,job_id)
    if not j: raise HTTPException(404,'分析任务不存在')
    reason=invalidity(d,j)
    if reason:
        raise HTTPException(409,f'该分析结果已失效，不能批准。原因：{reason}')
    if j.status!='completed':raise HTTPException(409,'仅已完成结果可以批准')
    j.approved=True
    return j

def effective(db, j):
    """Project the batch retirement onto a job view even before/without denormalized flags."""
    row=job_dict(j)
    if row['invalidated']: return row
    d=db.get(Dataset,j.dataset_id)
    if d is None:
        row.update({'invalidated':True,'invalidated_reason':'数据批次不存在','usable':False}); return row
    if d.retired_at is not None:
        row.update({'invalidated':True,'invalidated_at':d.retired_at,'invalidated_by':d.retired_by,
                    'invalidated_reason':d.retire_reason,'usable':False})
    return row
