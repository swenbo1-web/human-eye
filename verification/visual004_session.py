"""Finite neutral owner broker for the paired visual trial; no task solver.

Only an explicit P observe operation dynamically imports the product adapter.
The N path and common process/image/text accounting do not import Human Eye.
"""
from __future__ import annotations
import argparse,hashlib,json,os,socket,sys,time,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from verification.visual004_native import NativeSession,ImageLedger,encoded,load,save,sha,check,need,MAX_CODE,publish_ready,protected_files_intact
from verification import visual004_native as neutral

MAX_PUBLIC_CALLS=48;TEXT_LIMIT=256*1024;CONTROL_LIMIT=48*2048;ERROR_RESERVE=2048;REQUEST_LIMIT=MAX_CODE+32768
OPS={'native_run','observe','image_reserve','status','close'}

class OwnerBroker:
    def __init__(self,session,*,started_ns,deadline_ns):
        self.session=session;self.workspace=session.workspace;self.deadline_ns=deadline_ns
        self.images=ImageLedger(self.workspace)
        self.state=dict(schema='visual004-owner-broker-v1',started_ns=started_ns,original_deadline_ns=deadline_ns,
            owner_pid=os.getpid(),
            condition=session.config['condition'],public_calls=0,max_public_calls=MAX_PUBLIC_CALLS,
            public_text_limit=TEXT_LIMIT,public_data_limit=TEXT_LIMIT,public_control_limit=CONTROL_LIMIT,
            public_text_bytes=0,public_data_bytes=0,public_control_bytes=0,full_result_bytes_generated=0,
            request_ids=[],events=[],closed=False,close_receipt=None,
            neutral_scope='process/deadline/file/image/text accounting only; no inventory/solver/task selection')
        self._persist()
    def _persist(self):save(self.workspace/'BROKER_STATE.json',self.state,replace=True)
    def _request(self,request):
        need(type(request) is dict and set(request)=={'request_id','operation','args'},'broker_request')
        need(type(request['request_id']) is str and 1<=len(request['request_id'])<=128,'request_id')
        need(request['operation'] in OPS and type(request['args']) is dict,'broker_operation')
        return request['operation'],request['args']
    def _image_refs(self,image_ids):
        reservation=self.images.reserve_delivery(image_ids)
        index={row['image_id']:row for row in self.images.status()['constructions']}
        return [dict(index[image_id],reservation_id=reservation['reservation_id'],
            consumption_proof='actual_image_block_host_evidence_required') for image_id in image_ids]
    def _native(self,args):
        need(set(args)<={'code','deliver_paths','timeout_s'} and type(args.get('code')) is str
            and len(args['code'].encode('utf8'))<=MAX_CODE,'native_arguments')
        paths=args.get('deliver_paths',[]);need(type(paths) is list and len(paths)<=8 and all(type(p) is str for p in paths),'deliver_paths')
        result=self.session.run(args['code'],timeout_s=args.get('timeout_s',30));registered=[]
        # Failed scripts may still construct images. Register only explicitly
        # requested files, retain all worker render/file events separately.
        for name in paths:
            path=Path(name);path=(path if path.is_absolute() else self.workspace/path).resolve()
            need(path.is_relative_to(self.workspace) and path.is_file(),'image_workspace')
            registered.append(self.images.register_external_image(path.read_bytes(),label=name,origin='native_consumer_requested_PNG'))
        return dict(native=result,images_constructed_for_delivery=registered,
            image_refs=self._image_refs([row['image_id'] for row in registered]) if registered else [])
    def _observe(self,args):
        need(self.session.config['condition']=='P','P_only_product')
        need(set(args)=={'arguments'} and type(args['arguments']) is dict,'observe_arguments')
        from verification.visual004_product import observe
        result=observe(self.session,args['arguments'])
        image_ids=[row['image_id'] for row in result.get('images',[])]
        return dict(product=result,image_refs=self._image_refs(image_ids) if image_ids else [])
    def _operate(self,operation,args):
        if operation=='native_run':return self._native(args)
        if operation=='observe':return self._observe(args)
        if operation=='image_reserve':
            need(set(args)=={'image_ids'},'reserve_arguments');return dict(image_refs=self._image_refs(args['image_ids']))
        if operation=='status':
            need(not args,'status_arguments')
            return dict(native=self.session.status(),images=self.images.status(),
                public_calls=self.state['public_calls'],public_text_bytes=self.state['public_text_bytes'],
                public_data_bytes=self.state['public_data_bytes'],public_control_bytes=self.state['public_control_bytes'],
                original_deadline_ns=self.deadline_ns)
        need(False,'broker_operation')
    def close(self,reason='requested'):
        if not self.state['closed']:
            # Product context owns no child process. Releasing it before the
            # native owner shutdown must never restart or reset either one.
            cleanup_error=None
            if self.session.config['condition']=='P':
                try:
                    from verification.visual004_product import close_product
                    close_product(self.session)
                except BaseException as exc:cleanup_error=dict(type=type(exc).__name__,message=str(exc))
            receipt=self.session.close()
            if cleanup_error is not None:receipt=dict(receipt,product_context_cleanup_error=cleanup_error)
            self.state.update(closed=True,close_reason=reason,close_receipt=receipt,closed_ns=time.perf_counter_ns())
            self._persist()
        return self.state['close_receipt']
    def handle(self,request):
        entered=time.perf_counter_ns();sequence=len(self.state['events'])+1
        folder=self.workspace/'broker_calls'/str(sequence);folder.mkdir(parents=True,exist_ok=False)
        save(folder/'REQUEST.json',request)
        event=dict(sequence=sequence,started_ns=entered,state='reserved',public_call_reserved=False,
            source='actual controller request, not model-consumption attestation')
        self.state['events'].append(event)
        operation=request.get('operation') if type(request) is dict else None
        # Close is an administrative control, available even after exhaustion.
        is_close=operation=='close'
        if not is_close:
            self.state['public_calls']+=1;event['public_call_reserved']=True
        self._persist();full=None
        try:
            operation,args=self._request(request)
            if is_close:
                need(not args,'close_arguments');result=self.close()
            else:
                check(self.deadline_ns);need(not self.state['closed'],'broker_closed')
                need(self.state['public_calls']<=MAX_PUBLIC_CALLS,'public_call_budget')
                need(self.state['public_data_bytes']<TEXT_LIMIT,'public_data_budget')
                need(self.state['public_control_bytes']<=CONTROL_LIMIT-2*ERROR_RESERVE,'public_control_budget')
                need(not (self.workspace/'POISONED.json').exists(),'session_poisoned')
                need(request['request_id'] not in self.state['request_ids'],'duplicate_request_no_replay')
                self.state['request_ids'].append(request['request_id']);self._persist()
                result=self._operate(operation,args)
                check(self.deadline_ns)
            observed_failure=False
            if operation=='native_run':observed_failure=result['native']['response'].get('status')!='success'
            elif operation=='observe':observed_failure=bool(result['product'].get('mcp_is_error') or result['product'].get('rpc_error'))
            event['observed_suboperation_failure']=observed_failure
            full=dict(schema='visual004-broker-response-v1',request_id=request['request_id'],operation=operation,
                ok=True,operation_succeeded=not observed_failure,result=result,original_deadline_ns=self.deadline_ns,model_image_consumption_confirmed=None)
            event['state']='completed'
        except BaseException as exc:
            if isinstance(exc,(OSError,TimeoutError)):
                # N's NativeSession already does this; the idempotent owner
                # abort also covers uncaught P transport exceptions without
                # importing product exception classes on the N path.
                self.session.abort('broker_transport_uncertain')
            full=dict(schema='visual004-broker-response-v1',request_id=request.get('request_id') if type(request) is dict else None,
                operation=operation,ok=False,error=dict(type=type(exc).__name__,message=str(exc)),
                original_deadline_ns=self.deadline_ns,automatic_retry=False,model_image_consumption_confirmed=None)
            event.update(state='failed',error_type=type(exc).__name__,reason=str(exc))
        raw=encoded(full);save(folder/'FULL_RESULT.json',full)
        self.state['full_result_bytes_generated']+=len(raw);event['full_result_bytes']=len(raw)
        public=dict(full)
        if full['ok'] and not is_close:
            private=full['result']
            if operation=='observe':
                value=private['product']
                public['result']=dict(mcp_text=value.get('mcp_text',[]),mcp_is_error=value.get('mcp_is_error'),
                    rpc_error=value.get('rpc_error'),image_refs=private.get('image_refs',[]))
            elif operation=='native_run':
                value=private['native']['response'];success=value.get('status')=='success'
                public['result']=dict(stdout=value.get('result',{}).get('result','') if success else value.get('stdout',''),
                    stderr='' if success else value.get('stderr',''),script_error=None if success else value.get('error'),
                    image_refs=private.get('image_refs',[]))
        public_raw=encoded(public)
        data_bytes=(len(encoded(public['result']))-1) if public.get('ok') and not is_close else 0
        control_bytes=len(public_raw)-data_bytes
        if (data_bytes and self.state['public_data_bytes']+data_bytes>TEXT_LIMIT) or control_bytes>ERROR_RESERVE:
            binding=full.get('request_id')
            if type(binding) is not str or len(binding)>128:binding=None
            public=dict(schema='visual004-broker-response-v1',request_id=binding,operation=operation,ok=False,
                error=dict(type='PublicTextBudgetExceeded',message='Complete result/diagnostic retained privately; no truncated data is returned.'),
                full_result_bytes=len(raw),original_deadline_ns=self.deadline_ns,automatic_retry=False)
            public_raw=encoded(public);data_bytes=0;control_bytes=len(public_raw)
            event['state']='text_budget_failed';event['full_result_not_delivered']=True
            if control_bytes>ERROR_RESERVE:
                public['request_id']=None;public_raw=encoded(public);control_bytes=len(public_raw)
        # Normal headers and errors use the fixed control allowance, not a
        # guessed reservation that silently shrinks the full data allowance.
        if self.state['public_control_bytes']+control_bytes>CONTROL_LIMIT:
            public=dict(ok=False,error=dict(type='PublicControlBudgetExceeded',message='No further public payload; owner cleanup remains available.'))
            public_raw=encoded(public);data_bytes=0;control_bytes=len(public_raw);event['state']='control_budget_failed'
            if self.state['public_control_bytes']+control_bytes>CONTROL_LIMIT:
                public=None;public_raw=b'';control_bytes=0;event['undelivered_control_budget']=True
        if not is_close and self.state['public_calls']>MAX_PUBLIC_CALLS:
            public=None;public_raw=b'';data_bytes=control_bytes=0;event['state']='public_call_budget_failed_no_payload'
        self.state['public_data_bytes']+=data_bytes;self.state['public_control_bytes']+=control_bytes
        self.state['public_text_bytes']+=len(public_raw)
        event.update(public_wire_bytes=len(public_raw),finished_ns=time.perf_counter_ns(),
            public_data_bytes=data_bytes,public_control_bytes=control_bytes,
            elapsed_ns=time.perf_counter_ns()-entered,image_reservations=len(self.images.status()['reservations']))
        save(folder/'PUBLIC_RESPONSE.json',public);self._persist()
        # The result, serialization and durable records all belong to the
        # original window. A later complete-looking private candidate cannot
        # become a valid public success just because persistence took time.
        if not is_close and public is not None and public.get('ok') and time.perf_counter_ns()>=self.deadline_ns:
            self.state['public_data_bytes']-=data_bytes;self.state['public_control_bytes']-=control_bytes
            self.state['public_text_bytes']-=len(public_raw)
            public=dict(schema='visual004-broker-response-v1',request_id=full.get('request_id'),operation=operation,ok=False,
                error=dict(type='OriginalDeadlineExceeded',message='Result construction/persistence completed after the original task deadline.'),
                original_deadline_ns=self.deadline_ns,automatic_retry=False)
            public_raw=encoded(public);data_bytes=0;control_bytes=len(public_raw)
            if self.state['public_control_bytes']+control_bytes>CONTROL_LIMIT:
                public=None;public_raw=b'';control_bytes=0;event['undelivered_control_budget']=True
            self.state['public_control_bytes']+=control_bytes;self.state['public_text_bytes']+=len(public_raw)
            event.update(state='deadline_exceeded_after_result',full_result_not_delivered=True,public_data_bytes=0,
                public_control_bytes=control_bytes,public_wire_bytes=len(public_raw),finished_ns=time.perf_counter_ns())
            save(folder/'PUBLIC_RESPONSE.json',public,replace=True);self._persist()
        return public

def serve(*,asset,blender,workspace,condition,seconds=600,expected_asset_sha256=None,qa_vertex_patch=None):
    started=time.perf_counter_ns();need(type(seconds) in (int,float) and 0<seconds<=600,'broker_seconds')
    deadline=started+int(seconds*1e9);session=None;broker=None
    try:
        session=NativeSession.start(asset=asset,blender=blender,workspace=workspace,deadline_ns=deadline,
            condition=condition,expected_asset_sha256=expected_asset_sha256,max_calls=128,qa_vertex_patch=qa_vertex_patch)
        broker=OwnerBroker(session,started_ns=started,deadline_ns=deadline)
        with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as server:
            server.bind(('127.0.0.1',0));server.listen(2)
            ready=dict(schema='visual004-owner-broker-ready-v1',pid=os.getpid(),worker_pid=session.config['pid'],
                host='127.0.0.1',port=server.getsockname()[1],condition=condition,started_ns=started,
                original_deadline_ns=deadline,asset_sha256=session.config['asset_sha256'],helper_sha256=sha(Path(__file__)),
                neutral_helper_sha256=session.config['helper_sha256'])
            publish_ready(session.workspace/'BROKER_READY.json',ready,deadline_ns=deadline)
            sys.stdout.buffer.write(encoded(ready));sys.stdout.buffer.flush()
            check(deadline)
            while not broker.state['closed']:
                remaining=(deadline-time.perf_counter_ns())/1e9
                if remaining<=0:break
                server.settimeout(min(remaining,1.))
                try:connection,_=server.accept()
                except socket.timeout:continue
                with connection:
                    data=bytearray();connection.settimeout(max(.001,min(5.,remaining)))
                    while True:
                        chunk=connection.recv(65536)
                        if not chunk:break
                        data.extend(chunk);need(len(data)<=REQUEST_LIMIT,'broker_request_bytes')
                    try:request=json.loads(data);response=broker.handle(request)
                    except BaseException as exc:
                        response=dict(ok=False,error=dict(type=type(exc).__name__,message=str(exc)),automatic_retry=False)
                    try:
                        if response is not None:connection.sendall(encoded(response))
                    except OSError:
                        if session is not None:session.abort('broker_client_delivery_unknown')
                        break
    finally:
        if broker is not None:broker.close('serve_exit_or_original_deadline')
        elif session is not None:session.close()

def load_broker_ready(workspace,*,allow_expired=False):
    """One complete marker read, bound to this owned session; no parse retry."""
    workspace=Path(workspace).resolve()
    need(not (workspace/'START_FAILURE.json').exists(),'broker_native_start_failed')
    config=load(workspace/'SESSION.json')
    need(type(config) is dict and config.get('schema')=='visual004-native-session-v1','broker_session_binding')
    deadline=config.get('deadline_ns')
    need(type(deadline) is int and deadline>0 and type(config.get('pid')) is int and config['pid']>0
        and config.get('condition') in ('P','N'),'broker_session_binding')
    if not allow_expired:check(deadline)
    ready=load(workspace/'BROKER_READY.json')
    if not allow_expired:check(deadline)
    fields={'schema','pid','worker_pid','host','port','condition','started_ns','original_deadline_ns','asset_sha256','helper_sha256','neutral_helper_sha256'}
    need(type(ready) is dict and set(ready)==fields and ready['schema']=='visual004-owner-broker-ready-v1','broker_ready_schema')
    need(ready['host']=='127.0.0.1' and type(ready['port']) is int and 1<=ready['port']<=65535
        and type(ready['pid']) is int and ready['pid']>0 and type(ready['worker_pid']) is int
        and ready['worker_pid']==config['pid'],'broker_ready_identity')
    need(type(ready['started_ns']) is int and 0<ready['started_ns']<deadline
        and type(ready['original_deadline_ns']) is int and ready['original_deadline_ns']==deadline
        and deadline-ready['started_ns']<=600*10**9 and ready['condition']==config['condition'],'broker_ready_deadline')
    need(all(type(ready[key]) is str and len(ready[key])==64 and all(c in '0123456789abcdef' for c in ready[key])
        for key in ('asset_sha256','helper_sha256','neutral_helper_sha256')),'broker_ready_digests')
    need(ready['helper_sha256']==sha(Path(__file__)),'broker_helper_changed')
    need(ready['neutral_helper_sha256']==config.get('helper_sha256')==sha(Path(neutral.__file__))
        and ready['asset_sha256']==config.get('asset_sha256'),'broker_ready_source_binding')
    state=load(workspace/'BROKER_STATE.json')
    need(type(state) is dict and state.get('schema')=='visual004-owner-broker-v1'
        and type(state.get('owner_pid')) is int and state['owner_pid']==ready['pid']
        and state.get('started_ns')==ready['started_ns'] and state.get('original_deadline_ns')==deadline
        and state.get('condition')==ready['condition'],'broker_owner_binding')
    if not allow_expired:
        need(protected_files_intact(config),'broker_source_changed');check(deadline)
    return ready

def client(workspace,request):
    started=time.perf_counter_ns();workspace=Path(workspace).resolve()
    is_close=request.get('operation')=='close'
    ready=load_broker_ready(workspace,allow_expired=is_close)
    # Only cleanup may use the fixed seven-second control window, after binding.
    # This never renews the original task or worker deadline.
    io_deadline=started+7*10**9 if is_close else ready['original_deadline_ns']
    check(io_deadline)
    timeout=max(.001,min(7. if is_close else 35.,(io_deadline-time.perf_counter_ns())/1e9))
    with socket.create_connection((ready['host'],ready['port']),timeout=timeout) as connection:
        connection.sendall(encoded(request));connection.shutdown(socket.SHUT_WR);raw=bytearray()
        while True:
            remaining=(io_deadline-time.perf_counter_ns())/1e9
            need(remaining>0,'original_deadline');connection.settimeout(min(7. if is_close else 35.,remaining))
            chunk=connection.recv(65536)
            if not chunk:break
            raw.extend(chunk);need(len(raw)<=TEXT_LIMIT+CONTROL_LIMIT,'broker_public_response_bytes')
    check(io_deadline)
    need(raw,'broker_public_budget_rejected_no_payload')
    result=json.loads(raw);check(io_deadline);return result

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--serve',action='store_true')
    parser.add_argument('--workspace',required=True,type=Path);parser.add_argument('--asset',type=Path)
    parser.add_argument('--blender',type=Path);parser.add_argument('--condition',choices=['P','N']);parser.add_argument('--seconds',type=float,default=600)
    parser.add_argument('--expected-asset-sha256');parser.add_argument('--requestJSON',type=Path);args=parser.parse_args()
    if args.serve:
        need(args.asset is not None and args.blender is not None and args.condition is not None,'serve_arguments')
        serve(asset=args.asset,blender=args.blender,workspace=args.workspace,condition=args.condition,seconds=args.seconds,
            expected_asset_sha256=args.expected_asset_sha256);return
    need(args.requestJSON is not None,'requestJSON');path=args.requestJSON.resolve()
    need(path.is_relative_to(args.workspace.resolve()),'request_workspace')
    result=client(args.workspace,load(path));sys.stdout.buffer.write(encoded(result));sys.stdout.buffer.flush()

if __name__=='__main__':main()
