/** @typedef {{id:number,name:string,source:string,rows:number,checksum:string,retired:boolean,retired_at:number|null,retired_by:string|null,retire_reason:string|null}} Dataset */
/** @typedef {{id:number,name:string,dataset_id:number,status:string,result:Object,approved:boolean,invalated?:boolean,invalidated:boolean,invalidated_reason:string|null,usable:boolean}} AnalysisJob */
/** @typedef {{id:number,name:string,job_id:number,destination:string,next_run:number,enabled:boolean,invalidated:boolean,invalidated_reason:string|null}} ReportSchedule */
/** @typedef {{id:number,report_id:number,created_at:number,checksum:string,filename:string,destination:string,invalidated:boolean,invalidated_reason:string|null,downloadable:boolean}} DeliveryRecord */
export {};
