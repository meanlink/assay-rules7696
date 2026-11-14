import time, json, logging
from pathlib import Path
from sqlalchemy import select, update
from redis import Redis
from src.config.database import Session
from src.config.settings import REDIS_URL
from src.models import Job, Dataset, Report
from src.services.business import analyze
from src.services.reports import deliver
from src.services.audit import record
logging.basicConfig(level=logging.INFO)

def block(db, job, reason, stage):
    """Invalidate a job. The reason/timestamp written by retirement is never overwritten."""
    now=time.time()
    first=db.execute(update(Job).where(Job.id==job.id, Job.invalidated_at.is_(None)).values(
        status='invalidated', invalidated_at=now, invalidated_reason=reason,
        approved=False, result={}).execution_options(synchronize_session=False))
    if first.rowcount==0:
        db.execute(update(Job).where(Job.id==job.id).values(
            status='invalidated', approved=False, result={}).execution_options(synchronize_session=False))
    db.refresh(job)
    record(db,'worker','job.blocked',{'id':job.id,'reason':job.invalidated_reason,'stage':stage})

def retired_reason(db, job):
    """A retired batch must never yield a usable result, even if its job finishes now."""
    d=db.get(Dataset,job.dataset_id)
    if d is None: return '数据批次不存在'
    if d.retired_at is not None: return d.retire_reason or '数据批次已停用'
    return None

def execute(job_id):
    with Session() as db:
        j=db.get(Job,job_id)
        if not j:return
        if j.status=='invalidated':
            record(db,'worker','job.blocked',{'id':j.id,'reason':j.invalidated_reason or '关联数据批次已停用','stage':'queue'})
            db.commit(); return
        if j.status!='queued':return
        reason=retired_reason(db,j)
        if reason or j.invalidated_at is not None:
            block(db,j,reason or '关联数据批次已停用','queue')
            db.commit(); return
        # Conditional start: if retirement invalidation wins the row first, this affects 0 rows.
        started=db.execute(update(Job).where(Job.id==j.id, Job.status=='queued', Job.invalidated_at.is_(None)).values(status='running').execution_options(synchronize_session=False))
        db.commit()
        if started.rowcount!=1:
            db.refresh(j)
            if j.invalidated_at is not None:
                record(db,'worker','job.blocked',{'id':j.id,'reason':j.invalidated_reason,'stage':'start'})
            db.commit(); return
        try:
            d=db.get(Dataset,j.dataset_id)
            result=analyze(d.records,j.params)
            json.dumps(result,allow_nan=False)
            db.refresh(j)
            # Re-check after compute: retirement may have committed while the analysis ran.
            reason=retired_reason(db,j)
            if reason or j.invalidated_at is not None:
                block(db,j,reason or '关联数据批次已停用','completed')
            else:
                # Conditional publish: a retirement that invalidates the row between the check
                # above and this UPDATE makes rowcount 0, so no usable result is ever published.
                published=db.execute(update(Job).where(
                    Job.id==j.id, Job.status=='running', Job.invalidated_at.is_(None),
                ).values(result=result, status='completed', finished_at=time.time()).execution_options(synchronize_session=False))
                if published.rowcount==1:
                    record(db,'worker','job.completed',{'id':j.id})
                else:
                    block(db,j,'关联数据批次已停用','publish-blocked')
        except Exception as e:
            logging.exception('Analysis failed')
            db.rollback()
            j=db.get(Job,job_id)
            if j is not None and (j.status=='invalidated' or j.invalidated_at is not None):
                db.commit(); return
            db.execute(update(Job).where(Job.id==job_id, Job.invalidated_at.is_(None)).values(
                status='failed', error=str(e)[:990], finished_at=time.time()).execution_options(synchronize_session=False))
            record(db,'worker','job.failed',{'id':job_id,'error':str(e)[:990]})
        db.commit()

def recover():
    """Restart recovery: work of retired batches is invalidated, never re-run.
    Running work of live batches is requeued; queued work stays queued for execution."""
    with Session() as db:
        for j in list(db.scalars(select(Job).where(Job.status=='running'))):
            if retired_reason(db,j):
                block(db,j,retired_reason(db,j),'recovered')
            else:
                j.status='queued';record(db,'worker','job.recovered',{'id':j.id})
        for j in list(db.scalars(select(Job).where(Job.status=='queued'))):
            reason=retired_reason(db,j)
            if reason or j.invalidated_at is not None:
                block(db,j,reason or '关联数据批次已停用','recovered-queue')
        # Plans linked to retired batches are switched off before the first delivery tick.
        for r in list(db.scalars(select(Report).where(Report.enabled==True, Report.invalidated_at.is_(None)))):
            j=db.get(Job,r.job_id)
            if not j: continue
            reason=retired_reason(db,j) or (j.invalidated_reason if j.invalidated_at is not None else None)
            if reason:
                r.invalidated_at=time.time(); r.invalidated_reason=reason; r.enabled=False
        db.commit()

def tick():
    with Session() as db:
        queued=list(db.scalars(select(Job.id).where(Job.status=='queued').limit(3)))
    for job_id in queued:execute(job_id)
    with Session() as db:
        for r in db.scalars(select(Report).where(Report.enabled==True,Report.next_run<=time.time())):
            d=deliver(db,r)
            if d:record(db,'worker','report.delivered',{'id':r.id,'delivery':d.id})
        db.commit()

def main():
    r=Redis.from_url(REDIS_URL,socket_timeout=3)
    # This Compose stack has a single worker. A crash must not strand its jobs,
    # but a restart must not resurrect work from a retired batch either.
    recover()
    while True:
        Path('/tmp/heartbeat').touch()
        try:
            item=r.blpop('analysis:queue',timeout=1)
            if item:execute(int(item[1]))
            tick()
        except Exception:
            logging.exception('Worker retry');time.sleep(2)
if __name__=='__main__':main()
