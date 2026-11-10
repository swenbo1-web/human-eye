"""Parent-held read-only scene broker; tools route, they do not solve the task."""
import argparse,copy,hashlib,importlib.util,json,socket,sys,threading,time,traceback
from pathlib import Path

HERE=Path(__file__).resolve().parent
NATIVE={'name':'execute_blender_code','description':
    'Execute ordinary read-only bpy/Python in this session persistent private Blender namespace. '
    'NumPy, mathutils BVH, mesh/triangle reading, your own Python computations and cached variables are allowed. '
    'Only this scene and your own computations may be read; no fixture sources, management files or scoring data. '
    'No scene edits or saving. Image delivery disabled.',
    'inputSchema':{'type':'object','properties':{'code':{'type':'string'}},'required':['code'],'additionalProperties':False}}
SNAPSHOT="""import json as _j
print(_j.dumps({'unit_scale_m':bpy.context.scene.unit_settings.scale_length,'objects':[{'name':o.name,
'vertices_local':[list(v.co) for v in o.data.vertices],'matrix_world':[list(r) for r in o.matrix_world],
'faces':[list(p.vertices) for p in o.data.polygons]} for o in sorted(bpy.context.scene.objects,key=lambda x:x.name) if o.type=='MESH']},allow_nan=False))"""

def save(path,value):
    path=Path(path);path.write_text(json.dumps(value,indent=2,ensure_ascii=False,allow_nan=False)+'\n',encoding='utf8',newline='\n')
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def encoded(value):return json.dumps(value,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode()+b'\n'

class Owner:
    def __init__(self,config):
        self.config=config;self.out=Path(config['output']);self.out.mkdir(parents=True,exist_ok=False)
        self.started=time.perf_counter_ns();self.calls=0;self.bytes=0;self.logs=[];self.service=None;self.he=None
        spec=importlib.util.spec_from_file_location('_held_native',HERE/'reused/accepted_native.py')
        self.helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.helper)
        self.native=self.helper.NativeSession.start(blender=config['blender'],asset=config['asset'],
            workspace=self.out/'native',deadline_ns=config['worker_deadline_ns'],condition='N' if config['group']=='N' else 'P',
            expected_asset_sha256=config['asset_sha256'],max_calls=128)
        self.initial=self.snapshot('INITIAL.json')
        self.tools=[copy.deepcopy(NATIVE)]
        self.identity=None
        if config['group']!='N':
            from human_eye_plugin.live_service import LiveSpatialService
            from human_eye_plugin.live_spatial_mcp import LiveSpatialMCPServer,SPATIAL_TASK_TOOLS_SCHEMA
            from human_eye_plugin.runtime_identity import runtime_identity
            self.identity=runtime_identity(mode='live')
            assert self.identity['source_sha256']==config['source_sha256']
            assert self.identity['source_kind']=='installed_distribution'
            install=Path(config['install_root']);assert Path(sys.modules['human_eye_plugin'].__file__).parent.parent==install
            cfg={'schema_version':'1.0','enabled':True,'observe_on_prompt':False,'project_root':str(install),
                'state_file':str(self.out/'state.json'),'audit_file':str(self.out/'audit.jsonl'),'quad_size':128,
                'request_budget_s':30.,'max_sessions':4,'expected_identity':{'source_sha256':self.identity['source_sha256']},
                'blender':{'host':self.native.host,'port':self.native.port,'timeout_s':30.}}
            save(self.out/'product_config.json',cfg)
            self.service=LiveSpatialService(self.out/'product_config.json',production_mode=True)
            self.he=LiveSpatialMCPServer(self.service,default_session_id='current-scene',spatial_task_only=True)
            self.tools+=copy.deepcopy(SPATIAL_TASK_TOOLS_SCHEMA)
        save(self.out/'IDENTITY.json',{'group':config['group'],'runtime_identity':self.identity,
            'python':sys.executable,'numpy_in_native':'Blender bundled; unchanged for every group',
            'asset_sha256':sha(config['asset']),'startup_ns':time.perf_counter_ns()-self.started})

    def snapshot(self,name):
        value=self.native.run(SNAPSHOT,timeout_s=30);save(self.out/(name+'.receipt.json'),value)
        assert value['response']['status']=='success',value
        raw=json.loads(value['response']['result']['result']);save(self.out/name,raw);return raw

    def handle(self,req):
        method=req.get('method');rid=req.get('id')
        if rid is None:return None
        if method=='initialize':result={'protocolVersion':req.get('params',{}).get('protocolVersion','2025-03-26'),
            'capabilities':{'tools':{}},'serverInfo':{'name':'owned-spatial-session','version':'1'}}
        elif method=='tools/list':result={'tools':self.tools}
        elif method=='ping':result={}
        elif method=='tools/call':
            assert self.calls<32,'common_tool_budget_32';self.calls+=1
            params=req['params'];name=params['name'];args=params.get('arguments',{});mark=time.perf_counter_ns()
            folder=self.out/('tool_'+str(self.calls).zfill(2));folder.mkdir();save(folder/'REQUEST.json',req)
            if name=='execute_blender_code':
                assert set(args)=={'code'} and type(args['code']) is str
                receipt=self.native.run(args['code'],timeout_s=30);save(folder/'NATIVE_RECEIPT.json',receipt)
                response=receipt['response'];result={'content':[{'type':'text','text':encoded(response).decode().rstrip()}],
                    'isError':response.get('status')!='success'}
            elif name=='human_eye_spatial_relations' and self.he is not None:
                answer=self.he.handle_jsonrpc_message(req)
                result=answer.get('result',{'content':[{'type':'text','text':json.dumps(answer)}],'isError':True})
            else:raise ValueError('tool_not_available')
            value={'jsonrpc':'2.0','id':rid,'result':result};save(folder/'RESPONSE.json',value)
            self.logs.append({'name':name,'elapsed_ns':time.perf_counter_ns()-mark,'response_bytes':len(encoded(value)),
                'is_error':bool(result.get('isError'))})
            self.bytes+=len(encoded(value));assert self.bytes<=1048576,'common_response_byte_budget_1MiB'
            save(self.out/'TOOLS.json',{'calls':self.calls,'wire_tool_bytes':self.bytes,'tools':self.logs})
            return value
        else:return {'jsonrpc':'2.0','id':rid,'error':{'code':-32601,'message':'Method not found'}}
        return {'jsonrpc':'2.0','id':rid,'result':result}

    def close(self):
        result={'errors':[],'calls':self.calls,'tools':self.logs,'started_ns':self.started}
        try:
            final=self.snapshot('FINAL.json');result['geometry_unchanged']=final==self.initial
            if self.service is not None:self.service.host.close()
        except BaseException as e:result['errors'].append(repr(e))
        finally:
            result['native_close']=self.native.close()
            result['worker_closed']=self.native.status().get('closed')
            result['ended_ns']=time.perf_counter_ns();result['asset_unchanged']=sha(self.config['asset'])==self.config['asset_sha256']
            result['confirmed']=bool(result.get('geometry_unchanged') and result['native_close']['process_reaped']
                and result['native_close']['exit_code']==0 and result['worker_closed'] and result['asset_unchanged'] and not result['errors'])
            save(self.out/'CLOSE.json',result)
        return result

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--config',required=True,type=Path);args=parser.parse_args()
    config=json.loads(args.config.read_text());owner=None;stop=threading.Event();listener=None
    try:
        owner=Owner.__new__(Owner);owner.__init__(config)
        listener=socket.socket();listener.bind(('127.0.0.1',0));listener.listen(2);listener.settimeout(.2)
        def serve():
            while not stop.is_set():
                try:conn,_=listener.accept()
                except socket.timeout:continue
                except OSError:break
                with conn:
                    data=bytearray();conn.settimeout(40)
                    while True:
                        chunk=conn.recv(65536)
                        if not chunk:break
                        data.extend(chunk);assert len(data)<24*1024*1024
                    request=json.loads(data);rid=request['request_id']
                    try:reply={'request_id':rid,'ok':True,'result':owner.handle(request['args']['message'])}
                    except BaseException as e:reply={'request_id':rid,'ok':False,'error':repr(e)}
                    conn.sendall(encoded(reply))
        thread=threading.Thread(target=serve,daemon=True);thread.start()
        save(config['endpoint'],{'host':'127.0.0.1','port':listener.getsockname()[1],
            'chain_deadline_ns':config['worker_deadline_ns'],'actor_pid':__import__('os').getpid()})
        # Only the external controller owns this stdin and the backend lifetime.
        sys.stdin.readline();stop.set();listener.close();thread.join(timeout=35)
    except BaseException as e:
        save(Path(config['output']).parent/'ACTOR_ERROR.json',{'error':repr(e),'traceback':traceback.format_exc()})
        raise
    finally:
        if listener is not None:listener.close()
        if owner is not None and hasattr(owner,'native'):owner.close()

if __name__=='__main__':main()
