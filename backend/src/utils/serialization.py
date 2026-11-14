import hashlib, json
def checksum(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()
def dataset_dict(d):
    return {'id':d.id, 'name':d.name, 'source':d.source, 'rows':len(d.records), 'checksum':d.checksum, 'created_at':d.created_at,
            'retired':d.retired_at is not None, 'retired_at':d.retired_at, 'retired_by':d.retired_by, 'retire_reason':d.retire_reason}
def job_dict(j):
    return {**{k:getattr(j,k) for k in ['id','name','dataset_id','params','status','result','error','approved','created_at','finished_at']},
            'invalidated':j.invalidated_at is not None, 'invalidated_at':j.invalidated_at, 'invalidated_by':j.invalidated_by, 'invalidated_reason':j.invalidated_reason,
            'usable':j.invalidated_at is None}
def report_dict(r):
    return {**{k:getattr(r,k) for k in ['id','name','job_id','destination','interval_seconds','next_run','enabled']},
            'invalidated':r.invalidated_at is not None, 'invalidated_at':r.invalidated_at, 'invalidated_reason':r.invalidated_reason}
def delivery_dict(d, invalidated=False, invalidated_reason=None):
    return {**{k:getattr(d,k) for k in ['id','report_id','created_at','checksum','filename','destination']},
            'invalidated':invalidated, 'invalidated_reason':invalidated_reason, 'downloadable':not invalidated}
