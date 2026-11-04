"""One post-anchor, two-source read/publication session, not a scheduler.

The configured ledger root is operator authority, never a model parameter.
Each task digest owns one persistent slot there; changing request IDs, run nonce
or process cannot reset that task's spent reads. No automatic read retry exists.
"""
import copy,hashlib,json,os,threading,time,uuid
from pathlib import Path
from . import deformation_context as context,deformation_task_view as producer,deformation_anchors as anchors

CAPS=dict(directories=2,facts=4,native_supplements=1)
REFERENCE_FIELDS={'schema','run_nonce','condition_id','task_sha256','evidence_sha256','view_sha256','evidence_version'}
READ_BINDINGS=('request_id','run_nonce','condition_id','task_sha256','label','source_ref','selection','kind','deadline_ns','task_deadline_ns')
SIDECAR_LIMIT=2*1024*1024
AUDIT_LIMIT=4*1024*1024
VIEW_LIMIT=512*1024


class DeliveryError(ValueError):
    def __init__(self,reason):self.reason=reason;super().__init__('deformation_delivery_'+reason)


def need(value,reason):
    if not value:raise DeliveryError(reason)


def _blob(value):return context.publication_bytes(value)
def _digest(blob):return hashlib.sha256(blob).hexdigest()


def _persist_blob(path,blob):
    """Flush file bytes, atomically publish name; not a directory-fsync claim."""
    path=Path(path);temporary=path.with_name(path.name+'.pending-'+uuid.uuid4().hex)
    with temporary.open('xb') as f:
        f.write(blob);f.flush();os.fsync(f.fileno())
    os.replace(temporary,path)
    need(path.read_bytes()==blob,'persisted_bytes_mismatch')


def _read_blob(path,maximum):
    with Path(path).open('rb') as f:blob=f.read(maximum+1)
    need(len(blob)<=maximum,'artifact_byte_budget');return blob


class DeliverySession:
    def __init__(self,task_spec,*,run_nonce,condition_id,deadline_ns,store,reader,prior_usage,limits=None,clock_ns=time.perf_counter_ns):
        producer.validate_task_spec(task_spec)
        need(type(run_nonce) is str and len(run_nonce)==32 and all(c in '0123456789abcdef' for c in run_nonce)
            and type(condition_id) is str and 1<=len(condition_id)<=256,'run_binding')
        need(type(deadline_ns) is int and deadline_ns>clock_ns(),'original_deadline')
        limits=CAPS if limits is None else limits
        need(type(limits) is dict and set(limits)==set(CAPS)
            and all(type(v) is int and 0<=v<=CAPS[k] for k,v in limits.items()),'budget_caps')
        need(type(prior_usage) is dict and set(prior_usage)==set(CAPS)
            and all(type(v) is int and 0<=v<=limits[k] for k,v in prior_usage.items())
            and prior_usage['directories']==2,'prior_usage')
        self.spec=copy.deepcopy(task_spec);self.task_sha256=producer.task_digest(self.spec)
        self.run_nonce=run_nonce;self.condition_id=condition_id;self.deadline_ns=deadline_ns
        self.clock_ns=clock_ns;self.reader=reader;self._gate=threading.RLock();self._cancelled=threading.Event()
        self._closed=False;self._close_attempted=False;self._publication_completed=False;self.ledger_writes=[]
        self.store_root=Path(store).resolve();self.store_root.mkdir(parents=True,exist_ok=True)
        self.store_path=self.store_root/self.task_sha256
        try:self.store_path.mkdir()
        except FileExistsError:
            try:
                if hasattr(reader,'close'):reader.close()
            finally:raise DeliveryError('existing_task_no_reset')
        self.ledger=dict(schema='deformation-delivery-ledger-v1',task_sha256=self.task_sha256,run_nonce=run_nonce,
            condition_id=condition_id,original_deadline_ns=deadline_ns,limits=copy.deepcopy(limits),usage=copy.deepcopy(prior_usage),
            state='ready',requests={},deliveries=[],events=[],published=False,delivered=False,model_received=False,
            reader_costs={},reference=None,close_receipt=None,timings={},
            timing_scope='inclusive wall spans; do not add nested stages; complete request includes ledger writes')
        self.task=dict(spec=self.spec,task_sha256=self.task_sha256,condition_id=condition_id,run_nonce=run_nonce)
        try:self._initialize()
        except BaseException as exc:
            self._fail(exc)
            if isinstance(exc,DeliveryError):raise
            raise DeliveryError('initialization_failed') from exc

    def _initialize(self):
        reader=self.reader
        directories=reader.directory_receipts
        need(type(directories) is dict and set(directories)==set(self.spec['sources']),'directory_receipts')
        for label,receipt in directories.items():
            source=self.spec['sources'][label]
            need(type(receipt) is dict and receipt.get('label')==label and receipt.get('status')=='ok' and receipt.get('fresh') is True
                and all(_blob(receipt.get(k))==_blob(source[k]) for k in
                    ('source_ref','catalog_sha256','anchor_id','profile_sha256','core_half_extents_m'))
                and type(receipt.get('task_deadline_ns')) is int and receipt['task_deadline_ns']==self.deadline_ns
                and type(receipt.get('logical_directory_reads')) is int and receipt['logical_directory_reads']==1,
                'directory_binding')
        costs=reader.snapshot_costs()
        need(type(costs) is dict and type(costs.get('logical_directory_reads')) is int
            and costs['logical_directory_reads']==self.ledger['usage']['directories'],'prior_directory_costs')
        need(getattr(reader,'task_deadline_ns',self.deadline_ns)==self.deadline_ns,'reader_task_deadline')
        self.ledger['directory_receipts']=copy.deepcopy(directories)
        _persist_blob(self.store_path/'SPEC.json',_blob(self.spec))
        _persist_blob(self.store_path/'BINDING.json',_blob({k:self.ledger[k] for k in ('task_sha256','run_nonce','condition_id','original_deadline_ns','limits')}))
        self._snapshot();self._save();self._check()

    def _save(self):
        start=self.clock_ns();blob=_blob(self.ledger)
        try:_persist_blob(self.store_path/'LEDGER.json',blob)
        except BaseException:
            self.ledger_writes.append(dict(bytes=len(blob),elapsed_ns=self.clock_ns()-start,status='unknown'));raise
        self.ledger_writes.append(dict(bytes=len(blob),elapsed_ns=self.clock_ns()-start,status='completed'))

    def _snapshot(self):
        try:costs=self.reader.snapshot_costs()
        except BaseException as exc:
            self.ledger['cost_snapshot_error']=type(exc).__name__;return
        need(type(costs) is dict,'reader_costs')
        self.ledger['reader_costs']=copy.deepcopy(costs)
        for key in ('physical_inspect_requests','B2_rows_passes'):
            value=costs.get(key)
            need(value is None or type(value) is int and value>=0,'reader_costs')
            self.ledger['usage'][key]=value

    def _event(self,name,**values):
        self.ledger['events'].append(dict(sequence=len(self.ledger['events'])+1,event=name,at_ns=self.clock_ns(),**values))

    def _check(self,subdeadline=None):
        if self._cancelled.is_set():raise DeliveryError('cancelled')
        need(self.clock_ns()<self.deadline_ns,'original_deadline')
        if subdeadline is not None:need(self.clock_ns()<subdeadline,'read_deadline')

    def _close(self):
        if self._closed:return self.ledger.get('close_receipt')
        need(not self._close_attempted,'close_previously_failed');self._close_attempted=True
        started=self.clock_ns()
        try:
            receipt=self.reader.verify_and_close()
            need(type(receipt) is dict and receipt.get('sources_unchanged') is True
                and receipt.get('all_owned_closed') is True and receipt.get('original_deadline_preserved') is True,'close_receipt')
            self._closed=True;self.ledger['close_receipt']=copy.deepcopy(receipt)
            return receipt
        finally:
            self.ledger['timings']['verify_and_close_ns']=self.clock_ns()-started;self._snapshot()

    def _fail(self,exc):
        reason=exc.reason if isinstance(exc,DeliveryError) else type(exc).__name__
        state='cancelled' if self._cancelled.is_set() else 'deadline_exceeded' if self.clock_ns()>=self.deadline_ns else 'receipt_unknown' if reason=='receipt_unknown' else 'failed'
        self.ledger.update(state=state,error=dict(reason=reason,message=str(exc)),model_received=False)
        if not self._publication_completed:self.ledger.update(published=False,delivered=False)
        self._event('terminal',state=state,reason=reason)
        if not self._closed and not self._close_attempted:
            try:self._close()
            except BaseException as close_exc:self.ledger['close_error']=dict(type=type(close_exc).__name__,message=str(close_exc))
        if not self._closed and hasattr(self.reader,'close'):
            try:self.reader.close()
            except BaseException as cleanup_exc:self.ledger['cleanup_error']=dict(type=type(cleanup_exc).__name__,message=str(cleanup_exc))
        try:self._snapshot();self._save()
        except BaseException as persist_exc:self.ledger['terminal_persist_error']=type(persist_exc).__name__

    def request(self,request_id,*,kind='facts',explicit_candidates_by_label=None,max_candidates=4):
        with self._gate:
            need(type(request_id) is str and 1<=len(request_id)<=256,'request_id')
            need(request_id not in self.ledger['requests'],'duplicate_request')
            need(self.ledger['state']=='ready','terminal_no_retry')
            self.ledger['requests'][request_id]=dict(kind=kind,state='accepted')
            start=self.clock_ns()
            try:
                self._check();need(kind in ('facts','targeted','joint_supplement'),'read_kind')
                need(kind in getattr(self.reader,'supported_read_kinds',('facts',)),'unsupported_read_kind')
                if kind=='targeted':need(explicit_candidates_by_label is not None,'targeted_selection_required')
                if kind=='joint_supplement':
                    need(self.ledger['usage']['native_supplements']<self.ledger['limits']['native_supplements'],'budget_exhausted')
                    self.ledger['usage']['native_supplements']+=1
                else:need(self.ledger['usage']['facts']+2<=self.ledger['limits']['facts'],'budget_exhausted')
                self.ledger['state']='reading';self._event('request_accepted',request_id=request_id,kind=kind);self._save()
                frames=[];receipts=[]
                for label,source in self.spec['sources'].items():
                    self._check()
                    if kind!='joint_supplement':self.ledger['usage']['facts']+=1
                    self.ledger['usage']['logical_source_read_attempts']=self.ledger['usage'].get('logical_source_read_attempts',0)+1
                    subdeadline=min(self.deadline_ns,self.clock_ns()+30_000_000_000)
                    request=dict(schema='deformation-fact-read-v1',request_id=request_id+'/'+label,run_nonce=self.run_nonce,
                        condition_id=self.condition_id,task_sha256=self.task_sha256,label=label,kind=kind,
                        source_ref=copy.deepcopy(source['source_ref']),selection={k:copy.deepcopy(source[k]) for k in
                            ('catalog_sha256','anchor_id','core_half_extents_m','profile_sha256')},
                        deadline_ns=subdeadline,task_deadline_ns=self.deadline_ns)
                    if kind=='targeted':request['targeted_triangle_indices']=copy.deepcopy(explicit_candidates_by_label.get(label))
                    self._event('dispatch',request=request);self._save() # reservation survives a lost reply
                    try:response=self.reader.read(copy.deepcopy(request))
                    except BaseException as exc:
                        self._snapshot();self._event('receipt_unknown',request_id=request['request_id'],error=type(exc).__name__)
                        raise DeliveryError('receipt_unknown') from exc
                    self._snapshot();self._check(subdeadline)
                    need(type(response) is dict and type(response.get('receipt')) is dict,'receipt_unknown')
                    receipt=response['receipt'];self._event('receipt',receipt=copy.deepcopy(receipt));self._save()
                    need(all(_blob(receipt.get(k))==_blob(request[k]) for k in READ_BINDINGS),'receipt_binding')
                    need(receipt.get('status')=='ok' and receipt.get('fresh') is True,'receipt_unknown')
                    frame=response.get('bundle');need(type(frame) is dict and frame.get('label')==label,'receipt_binding')
                    need(receipt.get('source_sha256')==frame['proof']['source_sha256'],'receipt_source_binding')
                    if kind=='targeted':need(receipt.get('targeted_triangle_indices')==request['targeted_triangle_indices'],'targeted_receipt')
                    frames.append(frame);receipts.append(receipt)
                self.ledger['state']='constructing';self._event('qualified_facts',request_id=request_id);self._save();self._check()
                phase=self.clock_ns()
                view,audit=producer.produce(copy.deepcopy(self.task),frames,explicit_candidates_by_label=explicit_candidates_by_label,
                    max_candidates=max_candidates,deadline_ns=self.deadline_ns)
                self.ledger['timings']['producer_ns']=self.clock_ns()-phase
                self._check()
                phase=self.clock_ns()
                evidence=audit['evidence_sidecar'];evidence_blob=_blob(evidence);view_blob=_blob(view);audit_blob=_blob(audit)
                need(len(evidence_blob)<=SIDECAR_LIMIT and len(audit_blob)<=AUDIT_LIMIT and len(view_blob)<=VIEW_LIMIT,'artifact_byte_budget')
                self._check()
                evidence_sha=_digest(evidence_blob);view_sha=_digest(view_blob)
                need(view['evidence_ref']['sha256']==evidence_sha,'evidence_digest')
                need(audit['published_publication_sha256']==view_sha and audit['published_publication_bytes']==len(view_blob),'view_digest')
                self._semantic(view,evidence)
                self.ledger['timings']['serialization_and_hash_ns']=self.clock_ns()-phase;phase=self.clock_ns()
                artifact_spans=[]
                for name,blob in (('EVIDENCE.json',evidence_blob),('VIEW.json',view_blob),('AUDIT.json',audit_blob),('READ_RECEIPTS.json',_blob(receipts))):
                    self._check();at=self.clock_ns();_persist_blob(self.store_path/name,blob)
                    artifact_spans.append(dict(artifact=name,bytes=len(blob),sha256=_digest(blob),persist_and_readback_ns=self.clock_ns()-at))
                    self.ledger['artifact_persistence']=copy.deepcopy(artifact_spans);self._check()
                self._event('artifacts_persisted',evidence_sha256=evidence_sha,view_sha256=view_sha,
                    evidence_bytes=len(evidence_blob),view_bytes=len(view_blob),audit_bytes=len(audit_blob))
                self.ledger['timings']['artifact_persistence_ns']=self.clock_ns()-phase
                self._save();self._check();self._close();self._check()
                reference=dict(schema='deformation-evidence-reference-v1',run_nonce=self.run_nonce,condition_id=self.condition_id,
                    task_sha256=self.task_sha256,evidence_sha256=evidence_sha,view_sha256=view_sha,evidence_version=2)
                marker=dict(schema='deformation-publication-commit-v1',reference=reference,request_id=request_id,
                    original_deadline_ns=self.deadline_ns,sources=copy.deepcopy(self.spec['sources']),
                    published=True,delivered=False,model_received=False)
                phase=self.clock_ns();_persist_blob(self.store_path/'PUBLISHED.json',_blob(marker));self._check()
                self.ledger['publication_artifact_written']=True
                self.ledger.update(state='published',published=True,reference=reference)
                self.ledger['requests'][request_id]['state']='published';self._event('published',request_id=request_id)
                self.ledger['timings']['publication_commit_ns']=self.clock_ns()-phase
                self.ledger['timings']['request_through_publication_ns']=self.clock_ns()-start
                self._snapshot();self._save();self._check()
                self.ledger['timings']['publication_commit_ns']=self.clock_ns()-phase
                self.ledger['timings']['publication_commit_scope']='marker, costs snapshot and first ledger commit; final timing-ledger write excluded'
                self.ledger['timings']['request_through_publication_ns']=self.clock_ns()-start
                self._save();self._check()
                reply=dict(status='published',reference=copy.deepcopy(reference),view=copy.deepcopy(view),published=True,
                    delivered=False,model_received=False,usage=copy.deepcopy(self.ledger['usage']),
                    measurements=dict(timings=copy.deepcopy(self.ledger['timings']),ledger_writes=copy.deepcopy(self.ledger_writes),
                        artifact_persistence=copy.deepcopy(artifact_spans),returned_view_bytes=len(view_blob),
                        complete_request_ns=self.clock_ns()-start))
                self._check();self._publication_completed=True;return reply
            except BaseException as exc:
                self._fail(exc)
                if isinstance(exc,DeliveryError):raise
                raise DeliveryError('execution_failed') from exc

    def _semantic(self,view,evidence):
        need(type(view) is dict and view.get('schema')=='surface-deformation-task-witness-view-v2'
            and type(evidence) is dict and evidence.get('schema')=='surface-deformation-task-witness-evidence-v2','evidence_version')
        need(_blob(evidence.get('request_task'))==_blob(self.task),'evidence_task_binding')
        expected=dict(task_sha256=self.task_sha256,run_nonce=self.run_nonce,condition_id=self.condition_id,
            question=self.spec['question'],thresholds=self.spec['thresholds'])
        need(_blob(view.get('task_binding'))==_blob(expected),'view_task_binding')
        need(set(evidence.get('frames',{}))==set(self.spec['sources']) and set(view.get('source_bindings',{}))==set(self.spec['sources']),'evidence_sources')
        for label,source in self.spec['sources'].items():
            frame=evidence['frames'][label];binding=view['source_bindings'][label]
            need(_blob(anchors.source_ref(frame['proof']))==_blob(source['source_ref'])
                and _blob(binding.get('source_ref'))==_blob(source['source_ref'])
                and frame['operator_pins']['profile_sha256']==source['profile_sha256']
                and binding.get('catalog_sha256')==source['catalog_sha256'] and binding.get('anchor_id')==source['anchor_id']
                and frame['policy']['required_core_half_extents_m']==source['core_half_extents_m'],'evidence_sources')

    def _reference(self,reference):
        started=self.clock_ns()
        self._check()
        need(self.ledger['state'] in ('published','delivered') and self.ledger['published'] is True,'unpublished_reference')
        need(type(reference) is dict and set(reference)==REFERENCE_FIELDS and _blob(reference)==_blob(self.ledger['reference']),'reference_binding')
        marker=json.loads(_read_blob(self.store_path/'PUBLISHED.json',65536))
        need(marker.get('schema')=='deformation-publication-commit-v1' and marker.get('reference')==reference
            and marker.get('published') is True and marker.get('original_deadline_ns')==self.deadline_ns
            and _blob(marker.get('sources'))==_blob(self.spec['sources']),'publication_binding')
        evidence=_read_blob(self.store_path/'EVIDENCE.json',SIDECAR_LIMIT);view=_read_blob(self.store_path/'VIEW.json',VIEW_LIMIT)
        need(len(evidence)<=SIDECAR_LIMIT and len(view)<=VIEW_LIMIT and _digest(evidence)==reference['evidence_sha256']
            and _digest(view)==reference['view_sha256'],'artifact_digest')
        need(_read_blob(self.store_path/'SPEC.json',65536)==_blob(self.spec),'persisted_task_binding')
        binding=json.loads(_read_blob(self.store_path/'BINDING.json',65536))
        need(all(_blob(binding.get(k))==_blob(self.ledger[k]) for k in
            ('task_sha256','run_nonce','condition_id','original_deadline_ns','limits')),'persisted_task_binding')
        persisted=json.loads(_read_blob(self.store_path/'LEDGER.json',AUDIT_LIMIT))
        need(persisted.get('state') in ('published','delivered') and persisted.get('reference')==reference
            and all(_blob(persisted.get(k))==_blob(self.ledger[k]) for k in
                ('task_sha256','run_nonce','condition_id','original_deadline_ns','limits','usage')),'publication_binding')
        artifact_limits={'EVIDENCE.json':SIDECAR_LIMIT,'VIEW.json':VIEW_LIMIT,
            'AUDIT.json':AUDIT_LIMIT,'READ_RECEIPTS.json':VIEW_LIMIT}
        records=self.ledger.get('artifact_persistence')
        need(type(records) is list and len(records)==4
            and all(type(row) is dict and row.get('artifact') in artifact_limits for row in records)
            and {row['artifact'] for row in records}==set(artifact_limits)
            and _blob(persisted.get('artifact_persistence'))==_blob(records),'artifact_manifest')
        artifact_bytes=0
        for row in records:
            try:blob=_read_blob(self.store_path/row['artifact'],artifact_limits[row['artifact']])
            except OSError as exc:raise DeliveryError('artifact_unavailable') from exc
            need(type(row.get('bytes')) is int and len(blob)==row['bytes']
                and _digest(blob)==row.get('sha256'),'artifact_digest')
            artifact_bytes+=len(blob);self._check()
        value=json.loads(evidence);model_view=json.loads(view);self._semantic(model_view,value)
        # Producer v2 owns the exact semantic envelope; immutable digest and
        # publication marker bind it here without treating arbitrary paths as reads.
        self._check();self.ledger['last_reference_verification']=dict(elapsed_ns=self.clock_ns()-started,
            evidence_bytes_read=len(evidence),view_bytes_read=len(view),four_artifact_bytes_read=artifact_bytes,
            payload_artifact_bytes_read=artifact_bytes+len(evidence)+len(view),
            scope='persisted artifact read/hash/semantic verification; not a new source inspect')
        return value

    def resolve(self,reference,pointer=''):
        with self._gate:
            started=self.clock_ns()
            value=self._reference(reference)
            need(type(pointer) is str and len(pointer)<=2048 and (pointer=='' or pointer.startswith('/')),'reference_pointer')
            try:
                for part in pointer.split('/')[1:] if pointer else []:
                    part=part.replace('~1','/').replace('~0','~')
                    if type(value) is list:
                        need(part.isdigit() and str(int(part))==part,'reference_pointer');value=value[int(part)]
                    else:need(type(value) is dict and part in value,'reference_pointer');value=value[part]
            except (IndexError,KeyError):raise DeliveryError('reference_pointer')
            try:
                self._check();self._event('evidence_resolution_attempt',pointer=pointer)
                self.ledger['timings']['last_resolution_through_value_ns']=self.clock_ns()-started
                self.ledger['last_resolved_value_bytes']=len(_blob(value));self._save();self._check()
                reply=dict(reference=copy.deepcopy(reference),pointer=pointer,value=copy.deepcopy(value),published=True,
                    delivered=self.ledger['delivered'],model_received=False)
                self._check()
            except BaseException as exc:
                self.ledger.update(state='evidence_delivery_unknown',model_received=False)
                self.ledger['resolution_error']=str(exc)
                try:self._save()
                except BaseException:pass
                raise DeliveryError('evidence_delivery_unknown') from exc
            return reply

    def deliver(self,reference,delivery_id):
        with self._gate:
            started=self.clock_ns()
            self._reference(reference)
            need(type(delivery_id) is str and 1<=len(delivery_id)<=256,'delivery_id')
            need(delivery_id not in self.ledger['deliveries'],'duplicate_delivery')
            self.ledger['deliveries'].append(delivery_id)
            was_delivered=self.ledger['delivered']
            try:
                self._event('protocol_delivery_attempt',delivery_id=delivery_id,model_received=False)
                self._save();self._check()
                self.ledger.update(state='delivered',delivered=True,model_received=False)
                self.ledger['timings']['last_delivery_through_ack_ns']=self.clock_ns()-started
                self._save();self._check()
                reply=dict(status='delivered',reference=copy.deepcopy(reference),published=True,delivered=True,model_received=False,
                    scope='protocol_transport_ack_not_model_consumption')
                self._check()
            except BaseException as exc:
                self.ledger.update(state='delivery_unknown',delivered=was_delivered,model_received=False)
                self.ledger['delivery_error']=str(exc)
                try:self._save()
                except BaseException:pass
                raise DeliveryError('delivery_unknown') from exc
            return reply

    def cancel(self,reason='cancelled'):
        self._cancelled.set()
        with self._gate:
            self.ledger['cancel_reason']=str(reason);self._fail(DeliveryError('cancelled'))
            return copy.deepcopy(self.ledger)
