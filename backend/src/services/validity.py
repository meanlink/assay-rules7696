"""Shared validity chain for batch retirement.

Every approval, scheduling, delivery and download decision reads the same chain
dataset -> job (and then report/delivery) under row locks, so a retirement that
has committed always wins the boundary and one that has not yet committed will
see the blocked operation and still invalidate its output.
"""
from sqlalchemy import select
from src.models import Dataset, Job


def locked_chain(db, job_id):
    """Acquire the canonical dataset -> job lock pair and return current rows."""
    j0 = db.scalar(select(Job).where(Job.id == job_id))
    if j0 is None:
        return None, None
    d = db.scalar(select(Dataset).where(Dataset.id == j0.dataset_id).with_for_update()) if j0.dataset_id else None
    j = db.scalar(select(Job).where(Job.id == job_id).with_for_update())
    return d, j


def invalidity(d, j):
    """Why this job may not be approved/distributed/downloaded, else None."""
    if j is None:
        return '分析任务不存在'
    if j.invalidated_at is not None or j.status == 'invalidated':
        return j.invalidated_reason or '关联数据批次已停用'
    if d is None:
        return '数据批次不存在'
    if d.retired_at is not None:
        return d.retire_reason or '数据批次已停用'
    return None
