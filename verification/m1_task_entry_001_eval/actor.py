"""M1 eval: common native plus one frozen candidate's actual C/S read profile.

Derived from native_plugin_complex_005/actor.py; the native worker and TCP
owner remain the original native_plugin_complex_003 implementation.
Importing this file starts no service, Blender process or model consumer.
"""
import argparse,copy,importlib.util,json,os,queue,socket,subprocess,sys,threading,time,traceback,types
from pathlib import Path
HERE=Path(__file__).resolve().parent;PREVIOUS=HERE.parent/'native_plugin_complex_003'
spec=importlib.util.spec_from_file_location('complex003_owner',PREVIOUS/'actor.py');base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
save,sha,encoded=base.save,base.sha,base.encoded
MAX_WIRE=24*1024*1024
TOOLS_BY_GROUP={
    'N':frozenset(),
    'C':frozenset({'human_eye_scene_observe','human_eye_connection_status'}),
    'S':frozenset({'human_eye_spatial_relations','human_eye_surface_nearest'}),
}

class Peer:
    """One real stdio MCP process, owned by this actor, with no request retry."""
    def __init__(self,config,out):
        self.out=out;out.mkdir();self.process=None;self.reader=None;self.poisoned=False;self.records=[];self.close_record=None
        self.tx_bytes=0;self.rx_bytes=0;self.events=queue.Queue();self.stderr=None
        try:
            command=[config['dependency_python'],'-I','-B',config['entry'],'serve','--config',str(config['product_config'])]
            if config['group']=='S':command.append('--spatial-task-only')
            self.stderr=(out/'stderr.bin').open('wb')
            self.process=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=self.stderr,
                cwd=out,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            save(out/'START.json',{'launcher_pid':self.process.pid,'command':command,'started_ns':time.perf_counter_ns()})
            def read():
                try:
                    while True:
                        raw=self.process.stdout.readline(MAX_WIRE+1)
                        if not raw:break
                        if len(raw)>MAX_WIRE:raise ValueError('product_response_frame_limit')
                        self.events.put(('reply',raw,time.perf_counter_ns()))
                except BaseException as exc:self.events.put(('error',repr(exc),time.perf_counter_ns()))
                finally:self.events.put(('eof',None,time.perf_counter_ns()))
            self.reader=threading.Thread(target=read,daemon=True);self.reader.start()
        except BaseException:
            self.close();raise
    def call(self,request,timeout_s=30):
        if self.poisoned:raise RuntimeError('product_channel_poisoned_no_replay')
        started=time.perf_counter_ns();index=len(self.records)+1;folder=self.out/str(index).zfill(3);folder.mkdir()
        tx=encoded(request);(folder/'TX.bin').write_bytes(tx);rx=None;error=None;sent=False
        try:
            self.process.stdin.write(tx);self.process.stdin.flush();self.tx_bytes+=len(tx);sent=True
            if 'id' not in request:return None
            left=timeout_s-(time.perf_counter_ns()-started)/1e9
            kind,raw,received=self.events.get(timeout=max(.001,left))
            if kind!='reply':raise RuntimeError('product_'+kind+':'+str(raw))
            rx=raw;self.rx_bytes+=len(rx);(folder/'RX.bin').write_bytes(rx);value=json.loads(rx)
            if value.get('id')!=request['id']:raise ValueError('product_response_id_mismatch_no_replay')
            return value
        except BaseException as exc:
            error={'type':type(exc).__name__,'message':str(exc)};self.poisoned=True;raise
        finally:
            row={'request_id':request.get('id'),'method':request.get('method'),'started_ns':started,
                 'elapsed_ns':time.perf_counter_ns()-started,'sent_bytes':len(tx) if sent else None,
                 'attempted_send_bytes':len(tx),'send_confirmed':sent,'received_bytes':0 if rx is None else len(rx),'error':error}
            self.records.append(row);save(folder/'RECEIPT.json',row)
            save(self.out/'RPC.json',{'requests':self.records,'tx_bytes':self.tx_bytes,'rx_bytes':self.rx_bytes,'poisoned':self.poisoned})
    def close(self):
        if self.close_record is not None:return self.close_record
        error=None
        try:
            if self.process is not None and self.process.poll() is None:
                self.process.stdin.close()
                try:self.process.wait(timeout=8)
                except subprocess.TimeoutExpired:self.process.kill();self.process.wait(timeout=5);error='forced_product_stop'
        except BaseException as exc:
            error=repr(exc)
            if self.process is not None and self.process.poll() is None:self.process.kill();self.process.wait(timeout=5)
        finally:
            if self.reader is not None and self.reader.ident is not None:self.reader.join(timeout=1)
            if self.stderr is not None:self.stderr.close()
        self.close_record={'launcher_pid':None if self.process is None else self.process.pid,
            'process_reaped':self.process is not None and self.process.poll() is not None,
            'exit_code':None if self.process is None else self.process.poll(),'reader_stopped':self.reader is None or not self.reader.is_alive(),
            'error':error,'ended_ns':time.perf_counter_ns()}
        self.close_record['confirmed']=self.close_record['process_reaped'] and self.close_record['exit_code']==0 and self.close_record['reader_stopped'] and error is None
        save(self.out/'CLOSE.json',self.close_record)
        if not self.close_record['confirmed']:raise RuntimeError('product_close_unconfirmed:'+str(self.close_record))
        return self.close_record

class Owner(base.Owner):
    def __init__(self,config):
        if config['group'] not in TOOLS_BY_GROUP:raise ValueError('unknown_evaluation_group')
        self.read_names=TOOLS_BY_GROUP[config['group']]
        self.config=config;self.out=Path(config['output']);self.out.mkdir(parents=True,exist_ok=False)
        self.started=time.perf_counter_ns();self.calls=0;self.bytes=0;self.logs=[];self.service=None;self.he=None;self.peer=None
        helper_spec=importlib.util.spec_from_file_location('_m1_eval_native',PREVIOUS/'reused/accepted_native.py')
        self.helper=importlib.util.module_from_spec(helper_spec);helper_spec.loader.exec_module(self.helper)
        self.native=self.helper.NativeSession.start(blender=config['blender'],asset=config['asset'],workspace=self.out/'native',
            deadline_ns=config['worker_deadline_ns'],condition='N' if config['group']=='N' else 'P',expected_asset_sha256=config['asset_sha256'],max_calls=128)
        self.initial=self.snapshot('INITIAL.json');self.tools=[copy.deepcopy(base.NATIVE)];self.identity=None
        if config['group']!='N':
            cfg={'schema_version':'1.0','enabled':True,'observe_on_prompt':False,'project_root':config['install_root'],
                'state_file':str(self.out/'state.json'),'audit_file':str(self.out/'audit.jsonl'),'quad_size':128,'request_budget_s':30.,'max_sessions':4,
                'expected_identity':{'source_sha256':config['source_sha256']},'blender':{'host':self.native.host,'port':self.native.port,'timeout_s':30.}}
            save(self.out/'product_config.json',cfg)
            self.peer=Peer.__new__(Peer)
            self.peer.__init__(dict(config,product_config=self.out/'product_config.json'),self.out/'plugin')
            # base.close performs final mesh readback, host.close, then native.close.
            self.service=types.SimpleNamespace(host=self.peer)
            init=self.peer.call({'jsonrpc':'2.0','id':'private-init','method':'initialize','params':{'protocolVersion':'2025-03-26','capabilities':{},'clientInfo':{'name':'owned-comparison','version':'m1-eval-prep'}}})
            save(self.out/'PLUGIN_INITIALIZE.json',init);self.identity=init['result']['_meta']['human_eye']
            assert self.identity['source_sha256']==config['source_sha256'] and self.identity['source_kind']=='installed_distribution'
            self.peer.call({'jsonrpc':'2.0','method':'notifications/initialized'})
            listed=self.peer.call({'jsonrpc':'2.0','id':'private-list','method':'tools/list'});save(self.out/'PLUGIN_TOOLS.json',listed)
            read_tools=[t for t in listed['result']['tools'] if t['name'] in self.read_names]
            assert len(read_tools)==2 and {t['name'] for t in read_tools}==self.read_names
            assert read_tools==config['read_schemas'],'profile_read_schemas_differ_from_frozen_installed_candidate'
            if config['group']=='S':
                assert len(listed['result']['tools'])==2,'compact_directory_contains_other_tools'
            self.tools+=copy.deepcopy(read_tools)
            # The same metadata-only probe for C/S; never warm geometry.
            ping=self.peer.call({'jsonrpc':'2.0','id':'private-ping','method':'ping'})
            assert ping.get('result')=={},'product_startup_ping_failed'
            save(self.out/'PLUGIN_PING.json',ping)
        save(self.out/'IDENTITY.json',{'group':config['group'],'runtime_identity':self.identity,'actor_pid':os.getpid(),'actor_parent_pid':os.getppid(),
            'python':sys.executable,'asset_sha256':sha(config['asset']),'common_native_sha256':__import__('hashlib').sha256(encoded(base.NATIVE)).hexdigest(),
            'startup_ns':time.perf_counter_ns()-self.started,'product_serve_entry':config.get('entry'),
            'profile':config['group'],'exposed_tool_names':[t['name'] for t in self.tools],
            'product_spatial_task_only':config['group']=='S','private_geometry_warmup':False})
    def handle(self,req):
        method=req.get('method');rid=req.get('id')
        if method!='tools/call':return super().handle(req)
        if rid is None:return None
        self.calls+=1;mark=time.perf_counter_ns();folder=self.out/('tool_'+str(self.calls).zfill(2));folder.mkdir();save(folder/'REQUEST.json',req)
        response=None;failure=None;produced_bytes=None;wire_bytes=0;name=None;args=None
        try:
            if self.calls>32:raise RuntimeError('common_tool_attempt_budget_32')
            params=req.get('params',{})
            if type(params) is not dict:raise ValueError('tool_params_object_required')
            name=params.get('name');args=params.get('arguments',{})
            if type(args) is not dict:raise ValueError('tool_arguments_object_required')
            if name=='execute_blender_code':
                assert set(args)=={'code'} and type(args['code']) is str
                receipt=self.native.run(args['code'],timeout_s=30);save(folder/'NATIVE_RECEIPT.json',receipt)
                raw=receipt['response'];result={'content':[{'type':'text','text':encoded(raw).decode().rstrip()}],'isError':raw.get('status')!='success'}
            elif name in self.read_names and self.peer is not None:
                if name=='human_eye_scene_observe' and args.get('include_image') is not False:
                    raise ValueError('zero_image_budget_requires_explicit_include_image_false')
                answer=self.peer.call(req,timeout_s=max(.001,30-(time.perf_counter_ns()-mark)/1e9))
                result=answer.get('result',{'content':[{'type':'text','text':json.dumps(answer)}],'isError':True})
            else:raise ValueError('tool_not_available')
            if any(block.get('type')=='image' for block in result.get('content',[])):
                raise ValueError('zero_image_delivery_budget')
            response={'jsonrpc':'2.0','id':rid,'result':result};produced_bytes=len(encoded(response))
            if self.bytes+produced_bytes>1048576:raise ValueError('common_tool_response_byte_budget_1MiB')
            wire_bytes=produced_bytes;self.bytes+=wire_bytes;save(folder/'RESPONSE.json',response);return response
        except BaseException as exc:
            failure={'type':type(exc).__name__,'message':str(exc),'traceback':traceback.format_exc()}
            response={'jsonrpc':'2.0','id':rid,'result':{'content':[{'type':'text','text':json.dumps({'status':'error','error':str(exc),'automatic_retry':False})}],'isError':True}}
            size=len(encoded(response))
            if self.bytes+size<=1048576:
                wire_bytes=size;self.bytes+=size;save(folder/'ERROR_RESPONSE.json',response);return response
            raise
        finally:
            row={'attempt':self.calls,'name':name,'started_ns':mark,'elapsed_ns':time.perf_counter_ns()-mark,
                'response_bytes':wire_bytes,'produced_response_bytes':produced_bytes,'exception':failure,
                'is_error':failure is not None or bool((response or {}).get('result',{}).get('isError'))}
            self.logs.append(row);save(folder/'ATTEMPT.json',row)
            save(self.out/'TOOLS.json',{'attempts':self.calls,'calls':self.calls,'wire_tool_bytes':self.bytes,'tools':self.logs})
    def close(self):
        result={'errors':[],'actor_pid':os.getpid(),'actor_parent_pid':os.getppid(),'tool_attempts':self.calls,'tools':self.logs,'started_ns':self.started}
        try:
            try:
                final=self.snapshot('FINAL.json');result['geometry_unchanged']=final==self.initial
            except BaseException as exc:result['errors'].append({'stage':'final_snapshot','error':repr(exc)})
        finally:
            # A failed final read never skips the still-owned product process.
            try:
                if self.peer is not None:result['plugin_close']=self.peer.close()
                else:result['plugin_close']=None
            except BaseException as exc:
                result['errors'].append({'stage':'product_close','error':repr(exc)})
                result['plugin_close']=getattr(self.peer,'close_record',None)
            finally:
                try:
                    result['native_close']=self.native.close();result['worker_closed']=self.native.status().get('closed')
                except BaseException as exc:result['errors'].append({'stage':'native_close','error':repr(exc)})
        result['asset_unchanged']=sha(self.config['asset'])==self.config['asset_sha256'];result['ended_ns']=time.perf_counter_ns()
        n=result.get('native_close',{});p=result.get('plugin_close')
        result['confirmed']=bool(not result['errors'] and result.get('geometry_unchanged') and result['asset_unchanged']
            and n.get('process_reaped') and n.get('exit_code')==0 and result.get('worker_closed')
            and (self.peer is None or p and p.get('confirmed')))
        save(self.out/'CLOSE.json',result);return result

if __name__=='__main__':
    # Reuse the proven single-owner TCP broker and stdin lifetime unchanged.
    base.Owner=Owner;base.main()
