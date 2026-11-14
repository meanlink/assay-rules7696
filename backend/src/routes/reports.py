import os
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from src.config.database import get_db
from src.config.settings import ARTIFACT_DIR
from src.models import Dataset, Job, Report, Delivery
from src.schemas.report import ReportInput
from src.middlewares.auth import current_user, admin_only
from src.services import reports
from src.services.audit import record
from src.utils.serialization import report_dict, delivery_dict
router=APIRouter()

def delivery_block(db, delivery, lock=True):
    """A downloaded archive inherits the validity of its plan, job and dataset.
    Download takes locks; read-only listings reuse the same rule without blocking writers."""
    if delivery is None: return '归档不存在'
    if lock: db.scalar(select(Delivery).where(Delivery.id==delivery.id).with_for_update())
    r0=db.get(Report,delivery.report_id)
    if r0 is None: return '分发计划不存在'
    if lock: d, j = reports._locked_chain(db, r0.job_id)
    else:
        j=db.get(Job,r0.job_id); d=db.get(Dataset,j.dataset_id) if j else None
    r=db.scalar(select(Report).where(Report.id==delivery.report_id).with_for_update()) if lock else db.get(Report,delivery.report_id)
    if r is None: return '分发计划不存在'
    if r.invalidated_at is not None: return r.invalidated_reason or '分发计划已停用'
    return reports.invalidity(d, j)

@router.get('/reports')
def listing(db=Depends(get_db),u=Depends(current_user)):
    return [report_dict(r) for r in db.scalars(select(Report).order_by(Report.id.desc()))]
@router.post('/reports',status_code=201)
def create(data:ReportInput,db=Depends(get_db),u=Depends(admin_only)):
    r=reports.create(db,data); record(db,u.email,'report.schedule',{'id':r.id,'destination':r.destination}); db.commit()
    return report_dict(r)
@router.post('/reports/{id}/toggle')
def toggle(id:int,db=Depends(get_db),u=Depends(admin_only)):
    r=db.get(Report,id)
    if not r:raise HTTPException(404,'分发计划不存在')
    if not r.enabled and r.invalidated_at is not None:
        raise HTTPException(409,f'该分发计划已因批次停用而失效，不能重新启用。原因：{r.invalidated_reason or "关联数据批次已停用"}')
    r.enabled=not r.enabled;record(db,u.email,'report.toggle',{'id':id,'enabled':r.enabled});db.commit()
    return report_dict(r)
@router.get('/deliveries')
def deliveries(db=Depends(get_db),u=Depends(current_user)):
    rows=[]
    for d in db.scalars(select(Delivery).order_by(Delivery.id.desc()).limit(100)):
        reason=delivery_block(db,d,lock=False)
        rows.append(delivery_dict(d, reason is not None, reason))
    return rows
@router.get('/deliveries/{id}/download')
def download(id:int,format:str='csv',db=Depends(get_db),u=Depends(current_user)):
    d=db.get(Delivery,id)
    if not d:raise HTTPException(404,'归档不存在')
    reason=delivery_block(db,d)
    if reason:
        record(db,u.email,'delivery.download_blocked',{'id':id,'reason':reason});db.commit()
        raise HTTPException(409,f'该归档已失效，不能下载。原因：{reason}')
    if format not in ('csv','json'):raise HTTPException(422,'支持 CSV 或 JSON')
    filename=d.filename+('.json' if format=='json' else '')
    p=os.path.join(ARTIFACT_DIR,filename)
    if not os.path.exists(p):raise HTTPException(404,'归档文件不存在，请重新安排分发')
    return FileResponse(p,filename=filename,media_type='application/json' if format=='json' else 'text/csv; charset=utf-8')
