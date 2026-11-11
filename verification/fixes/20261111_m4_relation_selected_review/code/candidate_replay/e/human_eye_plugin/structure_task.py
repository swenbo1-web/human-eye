"""Trusted local registration and bounded durable observation accounting.

Tool arguments cannot register, renew or switch this task. A fresh service
instance cannot resume an already claimed task. This is not a security boundary
against local code with the same filesystem privileges as the trusted host.
"""
from __future__ import annotations
from contextlib import contextmanager
import copy,hashlib,json,time,uuid
from pathlib import Path
from .agent_hooks import _atomic_write,_state_lock

SCHEMA='structure-observation-task-v1'
MAXIMA=dict(queries=6,images=2,png_bytes=16*1024*1024,text_bytes=512*1024,refs=16,duration_s=180)
TEXT_RESERVATION=96*1024
STATE_BYTES=256*1024
QUERY_SCHEMA={'type':'object','additionalProperties':False,'required':['mode','operation','request_id'],
    'properties':{'mode':{'const':'mesh_structure'},'operation':{'enum':['diagnose','patch']},
        'request_id':{'type':'string','minLength':1,'maxLength':128},
        'patch_ref':{'type':'string','pattern':'^[a-f0-9]{32}$'},
        'task_ref':{'type':'string','pattern':'^[a-f0-9]{32}$'}}}


class TaskRefused(ValueError):pass


def require(value,reason):
    if not value:raise TaskRefused('structure_task_'+reason)


def encoded(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode('utf8')


def digest(value):return hashlib.sha256(encoded(value)).hexdigest()


def integer(value,minimum,maximum):return type(value) is int and minimum<=value<=maximum


def hex_id(value):return type(value) is str and len(value)==32 and all(c in '0123456789abcdef' for c in value)


def query(value):
    require(type(value) is dict and not set(value)-{'mode','operation','request_id','patch_ref','task_ref'}
        and value.get('mode')=='mesh_structure' and value.get('operation') in ('diagnose','patch'),'query_fields')
    request=value.get('request_id')
    require(type(request) is str and 1<=len(request)<=128
        and all(c.isascii() and (c.isalnum() or c in '_.:-') for c in request),'request_id')
    if value['operation']=='patch':require(hex_id(value.get('patch_ref')),'patch_ref_required')
    else:require('patch_ref' not in value,'diagnose_has_no_patch_ref')
    if 'task_ref' in value:require(hex_id(value['task_ref']),'invalid_task_ref')
    return dict(value)


def _config(path):
    from .agent_hooks import _read_object,_path
    path=Path(path).resolve();config=_read_object(path)
    ledger=_path(path.parent,config.get('structure_task_file'),'structure_task_file')
    protected=[path]+[_path(path.parent,config.get(k),k) for k in ('state_file','audit_file')]
    protected += [p.with_name(p.name+'.lock') for p in protected[1:]]
    require(ledger not in protected and ledger.with_name(ledger.name+'.lock') not in protected,'path_collision')
    fingerprint=hashlib.sha256(json.dumps(config,sort_keys=True,ensure_ascii=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
    return ledger,fingerprint


def _registration_value(fingerprint,object_id,*,categories=None,limits=None):
    from .mesh_structure import SUPPORTED
    require(type(object_id) is str and 1<=len(object_id)<=256 and object_id.strip(),'object_id')
    categories=list(SUPPORTED) if categories is None else categories
    require(type(categories) is list and 1<=len(categories)<=9 and len(set(categories))==len(categories)
        and all(c in SUPPORTED for c in categories),'categories')
    limits=dict(MAXIMA) if limits is None else dict(limits)
    require(set(limits)==set(MAXIMA) and all(integer(limits[k],0 if k in ('images','png_bytes') else 1,v)
        for k,v in MAXIMA.items()) and limits['text_bytes']>=TEXT_RESERVATION,'limits')
    now=time.perf_counter_ns();wall=time.time_ns()
    value=dict(schema=SCHEMA,task_id=uuid.uuid4().hex,config_fingerprint=fingerprint,object_id=object_id,
        categories=categories,limits=limits,created_ns=now,deadline_ns=now+limits['duration_s']*10**9,
        created_wall_ns=wall,deadline_wall_ns=wall+limits['duration_s']*10**9,owner=None,
        spent=dict(queries=0,images=0,png_bytes=0,text_bytes=0),confirmed=dict(images=0,png_bytes=0,text_bytes=0),
        requests={},refs={},inflight=None,stopped=False)
    return value


def register(config_path, object_id, *, categories=None, limits=None):
    """Explicit trusted local entry; not advertised by any model-facing tool."""
    from .agent_hooks import _read_object
    require(not _read_object(Path(config_path)).get('structure_task_control_file'),'use_lifecycle_begin')
    ledger,fingerprint=_config(config_path)
    value=_registration_value(fingerprint,object_id,categories=categories,limits=limits)
    with _state_lock(ledger):
        require(not ledger.exists(),'registration_already_exists')
        _atomic_write(ledger,value,_buffered=True)
    return dict(task_id=value['task_id'],object_id=object_id,limits=value['limits'],execution_authority=False)


class TaskStore:
    def __init__(self,config_path,config_fingerprint,*,ledger_path=None):
        self.path,self.fingerprint=_config(config_path)
        require(self.fingerprint==config_fingerprint,'loaded_config_changed')
        if ledger_path is not None:self.path=Path(ledger_path).resolve()
        self.owner=uuid.uuid4().hex;self.poisoned=False

    def _write(self,value):
        require(len(encoded(value))<=STATE_BYTES,'state_byte_budget')
        try:_atomic_write(self.path,value,_buffered=True)
        except BaseException:self.poisoned=True;raise

    def _read(self):
        require(self.path.is_file(),'registration_required')
        with self.path.open('rb') as stream:raw=stream.read(STATE_BYTES+1)
        require(len(raw)<=STATE_BYTES,'state_byte_budget')
        def unique(pairs):
            result={}
            for key,value in pairs:
                require(key not in result,'duplicate_state_key');result[key]=value
            return result
        def reject(value):raise TaskRefused('structure_task_nonfinite_state')
        value=json.loads(raw,object_pairs_hook=unique,parse_constant=reject)
        fields={'schema','task_id','config_fingerprint','object_id','categories','limits','created_ns','deadline_ns',
            'created_wall_ns','deadline_wall_ns','owner','spent','confirmed','requests','refs','inflight','stopped'}
        require(type(value) is dict and set(value)==fields and value['schema']==SCHEMA
            and hex_id(value['task_id']) and value['config_fingerprint']==self.fingerprint,'state_binding')
        from .mesh_structure import SUPPORTED
        require(type(value['object_id']) is str and 1<=len(value['object_id'])<=256
            and type(value['categories']) is list and 1<=len(value['categories'])<=9
            and all(type(c) is str and c in SUPPORTED for c in value['categories'])
            and len(set(value['categories']))==len(value['categories']),'state_target')
        limits=value['limits']
        require(type(limits) is dict and set(limits)==set(MAXIMA) and all(integer(limits[k],
            0 if k in ('images','png_bytes') else 1,v) for k,v in MAXIMA.items())
            and limits['text_bytes']>=TEXT_RESERVATION,'state_limits')
        for key in ('created_ns','deadline_ns','created_wall_ns','deadline_wall_ns'):
            require(integer(value[key],1,2**63-1),'state_clock')
        require(value['deadline_ns']-value['created_ns']==limits['duration_s']*10**9
            and value['deadline_wall_ns']-value['created_wall_ns']==limits['duration_s']*10**9,'state_duration')
        require(value['owner'] is None or hex_id(value['owner']),'state_owner')
        require(type(value['stopped']) is bool and type(value['requests']) is dict
            and len(value['requests'])<=limits['queries'] and type(value['refs']) is dict
            and len(value['refs'])<=limits['refs'],'state_counts')
        require(type(value['spent']) is dict and set(value['spent'])=={'queries','images','png_bytes','text_bytes'}
            and all(integer(v,0,limits[k]) for k,v in value['spent'].items()),'state_spent')
        require(type(value['confirmed']) is dict and set(value['confirmed'])=={'images','png_bytes','text_bytes'}
            and all(integer(v,0,value['spent'][k]) for k,v in value['confirmed'].items()),'state_confirmed')
        require(value['spent']['queries']==len(value['requests']) and (value['inflight'] is None
            or type(value['inflight']) is str and value['inflight'] in value['requests']),'state_inflight')
        for key,row in value['requests'].items():
            query(dict(mode='mesh_structure',operation='diagnose',request_id=key))
            require(type(row) is dict and set(row)=={'fingerprint','phase','reserved','charge','receipt'}
                and type(row['fingerprint']) is str and len(row['fingerprint'])==64
                and row['phase'] in ('reserved','constructed','failed')
                and type(row['reserved']) is dict and set(row['reserved'])=={'images','png_bytes','text_bytes'}
                and all(integer(v,0,limits[k]) for k,v in row['reserved'].items())
                and type(row['charge']) is dict and set(row['charge'])==set(row['reserved'])
                and all(integer(v,0,row['reserved'][k]) for k,v in row['charge'].items())
                and (row['receipt'] is None or type(row['receipt']) is dict and len(encoded(row['receipt']))<=4096),
                'state_request')
            require(row['reserved']['images'] in (0,2) and row['reserved']['png_bytes']==
                (16*1024*1024 if row['reserved']['images'] else 0)
                and row['reserved']['text_bytes']==TEXT_RESERVATION,'state_reservation_shape')
            receipt=row['receipt']
            if row['phase']=='reserved':
                require(receipt is None and row['charge']==row['reserved'],'state_pending_receipt')
            else:
                require(type(receipt) is dict and set(receipt)=={'status','images_constructed','png_bytes_constructed',
                    'text_bytes_constructed','delivery','current_evidence'}
                    and type(receipt['status']) is str and 1<=len(receipt['status'])<=64
                    and receipt['delivery']=='not_attested' and receipt['current_evidence'] is False
                    and all(integer(receipt[k+'_constructed'],0,row['charge'][k]) for k in
                            ('images','png_bytes','text_bytes')),'state_receipt')
        for key in ('images','png_bytes','text_bytes'):
            require(value['spent'][key]==sum(r['charge'][key] for r in value['requests'].values()),'state_charge_sum')
            require(value['confirmed'][key]==sum(r['receipt'][key+'_constructed'] for r in value['requests'].values()
                if r['receipt'] is not None),'state_confirmed_sum')
        require(sum(r['phase']=='reserved' for r in value['requests'].values())==(value['inflight'] is not None),
                'state_reservation_count')
        require(value['inflight'] is None or value['requests'][value['inflight']]['phase']=='reserved','state_inflight_phase')
        for key,row in value['refs'].items():
            require(hex_id(key) and type(row) is dict and len(encoded(row))<=16384,'state_reference')
        return value

    def check(self,value):
        require(not self.poisoned,'writer_failed')
        now=time.perf_counter_ns();wall=time.time_ns()
        require(value['created_ns']<=now<value['deadline_ns'] and value['created_wall_ns']<=wall<value['deadline_wall_ns'],
                'expired_or_clock_reset')
        require(value['owner'] in (None,self.owner),'service_restart_requires_new_registration')
        require(not value['stopped'] and value['inflight'] is None,'prior_outcome_unconfirmed')

    @contextmanager
    def locked(self,timeout_s=20.):
        require(not self.poisoned,'writer_failed')
        with _state_lock(self.path,timeout_s=timeout_s):
            value=self._read();self.check(value);yield value

    def reserve(self,value,request_id,fingerprint,*,want_images):
        old=value['requests'].get(request_id)
        if old is not None:
            require(old['fingerprint']==fingerprint,'request_id_conflict')
            return dict(historical_receipt=True,current_evidence=False,receipt=copy.deepcopy(old['receipt']),images=[])
        limits=value['limits'];spent=value['spent']
        require(spent['queries']<limits['queries'],'query_budget_exhausted')
        require(spent['text_bytes']+TEXT_RESERVATION<=limits['text_bytes'],'text_budget_exhausted')
        images=2 if want_images and spent['images']+2<=limits['images'] and spent['png_bytes']+16*1024*1024<=limits['png_bytes'] else 0
        reserve=dict(images=images,png_bytes=16*1024*1024 if images else 0,text_bytes=TEXT_RESERVATION)
        value['owner']=self.owner;spent['queries']+=1
        for k,v in reserve.items():spent[k]+=v
        value['requests'][request_id]=dict(fingerprint=fingerprint,phase='reserved',reserved=reserve,
            charge=copy.deepcopy(reserve),receipt=None)
        value['inflight']=request_id;self._write(value)
        return None

    def finish(self,value,request_id,*,text_bytes,images,png_bytes,outcome,image_outcome_known=True,failed=False):
        record=value['requests'][request_id];reserved=record['reserved']
        require(value['inflight']==request_id and record['phase']=='reserved','finish_without_reservation')
        require(integer(text_bytes,0,reserved['text_bytes']) and integer(images,0,reserved['images'])
            and integer(png_bytes,0,reserved['png_bytes']),'output_exceeded_reservation')
        actual=dict(text_bytes=text_bytes,images=images,png_bytes=png_bytes)
        for key,count in actual.items():
            if key=='text_bytes' or image_outcome_known:
                value['spent'][key]-=reserved[key]-count;record['charge'][key]=count
            value['confirmed'][key]+=count
        record.update(phase='failed' if failed else 'constructed',receipt=dict(status=outcome,
            images_constructed=images,png_bytes_constructed=png_bytes,text_bytes_constructed=text_bytes,
            delivery='not_attested',current_evidence=False))
        value['inflight']=None;self._write(value)

    @staticmethod
    def summary(value):
        return dict(task_id=value['task_id'],limits=copy.deepcopy(value['limits']),spent=copy.deepcopy(value['spent']),
            confirmed=copy.deepcopy(value['confirmed']),deadline_ns=value['deadline_ns'],deadline_wall_ns=value['deadline_wall_ns'],
            scope='registered_task_not_caller_session',delivery='construction_not_model_read',execution_authority=False)
