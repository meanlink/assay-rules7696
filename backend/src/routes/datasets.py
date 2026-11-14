from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from src.config.database import get_db
from src.models import Dataset
from src.schemas.dataset import DatasetInput, DatasetRetireInput
from src.middlewares.auth import current_user, can_write, admin_only
from src.services import datasets
from src.services.audit import record
from src.utils.serialization import dataset_dict
router=APIRouter(prefix='/datasets')
@router.get('')
def listing(db=Depends(get_db),u=Depends(current_user)):
    return [dataset_dict(d) for d in db.scalars(select(Dataset).order_by(Dataset.id.desc()))]
@router.post('',status_code=201)
def create(data:DatasetInput,db=Depends(get_db),u=Depends(can_write)):
    d=datasets.create(db,data); record(db,u.email,'dataset.create',{'id':d.id,'rows':len(d.records)})
    db.commit(); return dataset_dict(d)
@router.get('/{id}')
def detail(id:int,db=Depends(get_db),u=Depends(current_user)):
    d=db.get(Dataset,id)
    if not d:raise HTTPException(404,'数据批次不存在')
    return {**dataset_dict(d),'records':d.records}
@router.get('/{id}/impact')
def impact(id:int,db=Depends(get_db),u=Depends(current_user)):
    d=db.get(Dataset,id)
    if not d:raise HTTPException(404,'数据批次不存在')
    return datasets.impact(db,d)
@router.post('/{id}/retire')
def retire(id:int,data:DatasetRetireInput,db=Depends(get_db),u=Depends(admin_only)):
    d=datasets.retire(db,id,data.reason,u.email)
    db.commit()
    return {**datasets.impact(db,d),'message':f'批次已停用：已拒绝新分析，{len(datasets.affected_entities(db,d)[0])} 个分析任务及其计划、归档全部失效。'}
