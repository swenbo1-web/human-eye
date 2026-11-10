"""Single owner of all SCALE-DIAG-001 sampling; no model consumer."""
from pathlib import Path
import argparse, ctypes, hashlib, importlib.util, json, os, subprocess, sys, time, traceback

HERE=Path(__file__).resolve().parent
BLENDER=Path('D:/Tools/blender5.2/blender.exe')
PRODUCT_PY=HERE.parents[1]/'.plugin_ab_runtime/B/venv/Scripts/python.exe'
CANONICAL='a50e34c9169e9384047b29fa8bda8a072f96681f64610334ccec367d8597589b'

def dump(path,value):
    Path(path).write_text(json.dumps(value,ensure_ascii=False,allow_nan=False,indent=2)+'\n',encoding='utf8',newline='\n')
def load(path):return json.loads(Path(path).read_bytes())
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m);return m
def encode(value):return json.dumps(value,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()+b'\n'

def memory(pid=None):
    class COUNTERS(ctypes.Structure):
        _fields_=[('cb',ctypes.c_ulong),('PageFaultCount',ctypes.c_ulong),('PeakWorkingSetSize',ctypes.c_size_t),('WorkingSetSize',ctypes.c_size_t),('QuotaPeakPagedPoolUsage',ctypes.c_size_t),('QuotaPagedPoolUsage',ctypes.c_size_t),('QuotaPeakNonPagedPoolUsage',ctypes.c_size_t),('QuotaNonPagedPoolUsage',ctypes.c_size_t),('PagefileUsage',ctypes.c_size_t),('PeakPagefileUsage',ctypes.c_size_t)]
    try:
        c=COUNTERS();c.cb=ctypes.sizeof(c)
        kernel=ctypes.WinDLL('kernel32');kernel.GetCurrentProcess.restype=ctypes.c_void_p
        psapi=ctypes.WinDLL('psapi');psapi.GetProcessMemoryInfo.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_ulong]
        kernel.OpenProcess.argtypes=[ctypes.c_ulong,ctypes.c_int,ctypes.c_ulong];kernel.OpenProcess.restype=ctypes.c_void_p
        kernel.CloseHandle.argtypes=[ctypes.c_void_p]
        handle=kernel.GetCurrentProcess() if pid is None else kernel.OpenProcess(0x410,False,pid)
        ok=psapi.GetProcessMemoryInfo(handle,ctypes.byref(c),c.cb)
        if pid is not None and handle:kernel.CloseHandle(handle)
        return {'working_set_bytes':c.WorkingSetSize,'lifetime_peak_working_set_bytes':c.PeakWorkingSetSize} if ok else None
    except Exception:return None

def steps_file(out):
    source=(HERE/'build_fixtures.py').read_text(encoding='utf8')
    init="_mg={'__name__':'scale_management','__file__':"+repr(str(HERE/'build_fixtures.py'))+"}\nexec("+repr(source)+",_mg)\n"
    # Reload the owned input copy, never touch the immutable published asset.
    codes={str(i):(init+"_mg['OUT']=__import__('pathlib').Path(bpy.data.filepath).parent\n_mg['advance']("+str(i)+")\n" if i!=6 else
          "bpy.ops.wm.open_mainfile(filepath=__import__('os').environ['SCALE_OWNED_INPUT'])\nbpy.context.view_layer.update()\n")+
          "if '_scale_solver' in globals():_scale_solver.change("+str(i)+")\n" for i in range(1,7)}
    dump(out/'MANAGEMENT_STEPS.json',codes)
    return out/'MANAGEMENT_STEPS.json'

SNAPSHOT="""import json as _j, os as _os
def _scale_snapshot():
 rows=[]
 for o in sorted(bpy.context.scene.objects,key=lambda o:o.name):
  if o.type!='MESH':continue
  local=[[float(c) for c in v.co] for v in o.data.vertices];mat=[[float(v) for v in r] for r in o.matrix_world]
  rows.append({'logical_id':o.get('scale_logical_id'),'name':o.name,'vertices_local':local,'matrix_world':mat,'vertices_world':[[sum(mat[j][i]*p[i] for i in range(3))+mat[j][3] for j in range(3)] for p in local],'triangles':[list(p.vertices) for p in o.data.polygons]})
 return {'unit_scale_m':float(bpy.context.scene.unit_settings.scale_length),'objects':rows}
_os.environ['SCALE_OWNED_INPUT']=bpy.data.filepath
print(_j.dumps(_scale_snapshot(),allow_nan=False,separators=(',',':')))
"""

class SocketMeter:
    def __init__(self):self.counts={};self.original=None
    def reset(self):self.counts={'socket_send_bytes':0,'socket_recv_bytes':0,'socket_connects':0,'recv_calls':0}
    def install(self):
        import socket
        self.reset();self.original=socket.create_connection;meter=self
        class Proxy:
            def __init__(self,s):self.s=s
            def __getattr__(self,k):return getattr(self.s,k)
            def __enter__(self):self.s.__enter__();return self
            def __exit__(self,*a):return self.s.__exit__(*a)
            def sendall(self,data,*a,**kw):result=self.s.sendall(data,*a,**kw);meter.counts['socket_send_bytes']+=len(data);return result
            def recv(self,*a,**kw):data=self.s.recv(*a,**kw);meter.counts['socket_recv_bytes']+=len(data);meter.counts['recv_calls']+=1;return data
        def connect(*a,**kw):
            s=self.original(*a,**kw);self.counts['socket_connects']+=1;return Proxy(s)
        socket.create_connection=connect
    def close(self):
        if self.original:
            import socket
            socket.create_connection=self.original

def child(args):
    out=Path(args.output);out.mkdir(parents=True,exist_ok=False)
    begun=time.perf_counter_ns();helper=module('scale_session',HERE/'session.py')
    asset=HERE/'fixtures'/(args.scene+'.blend');native=None;meter=None;service=None;rows=[];failed=None;close=None
    try:
        management=steps_file(out) if args.mode=='T' else None
        native=helper.NativeSession.start(blender=BLENDER,asset=asset,workspace=out/'native',deadline_ns=begun+570*10**9,
            condition='N' if args.group=='N' else 'P',expected_asset_sha256=sha(asset),max_calls=128,management_steps=management)
        initial_receipt=native.run(SNAPSHOT,timeout_s=30);dump(out/'INITIAL_RECEIPT.json',initial_receipt)
        initial=json.loads(initial_receipt['response']['result']['result']);dump(out/'INITIAL.json',initial)
        expected=load(HERE/'fixtures'/(('T0' if args.mode=='T' else args.scene)+'.json'))
        assert initial=={k:expected[k] for k in ('unit_scale_m','objects')},'initial_actual_mesh_binding'
        pid=native.process.pid
        if args.group=='P':
            from human_eye_plugin.live_service import LiveSpatialService
            from human_eye_plugin.live_spatial_mcp import LiveSpatialMCPServer
            from human_eye_plugin.runtime_identity import runtime_identity
            identity=runtime_identity(mode='live');assert identity['source_sha256']==CANONICAL and identity['source_kind']=='installed_distribution'
            install=Path(sys.modules['human_eye_plugin'].__file__).parent.parent
            assert install==PRODUCT_PY.parents[1]/'Lib/site-packages'
            config={'schema_version':'1.0','enabled':True,'observe_on_prompt':False,'project_root':str(install),'state_file':str(out/'state.json'),
                    'audit_file':str(out/'audit.jsonl'),'quad_size':128,'request_budget_s':30.,'max_sessions':4,
                    'expected_identity':{'source_sha256':CANONICAL},'blender':{'host':native.host,'port':native.port,'timeout_s':30.}}
            dump(out/'CONFIG.json',config);service=LiveSpatialService(out/'CONFIG.json',production_mode=True)
            server=LiveSpatialMCPServer(service,default_session_id='scale-task',spatial_task_only=args.mode=='G')
            meter=module('scale_instrument',HERE/'instrument.py').install(service)
            dump(out/'IDENTITY.json',identity)
        else:
            meter=SocketMeter();meter.install()
            dump(out/'IDENTITY.json',{'python':sys.executable,'blender':str(BLENDER),'native_source_sha256':sha(HERE/'native_impl.py')})
        setup_ns=time.perf_counter_ns()-begun
        steps=range(7) if args.mode=='T' else range(3)
        for step in steps:
            if args.mode=='T' and step:
                mut=native.advance(step);dump(out/('MUTATION_%d.json'%step),mut)
            meter.reset();before={'actor':memory(),'host':memory(pid)};exception=None;value=None;wire=None;receipt=None;req=None
            mark=time.perf_counter_ns()
            try:
                if args.group=='N':
                    prefix=((HERE/'native_impl.py').read_text(encoding='utf8')+'\n_scale_solver=Solver()\n') if step==0 else ''
                    code=prefix+"_scale_result=_scale_solver.query("+repr('G' if args.mode=='G' else 'D')+","+str(mark+30*10**9)+")\nprint(json.dumps(_scale_result,allow_nan=False,separators=(',',':')))\n"
                    receipt=native.run(code,timeout_s=30);reply=receipt['response']
                    if reply.get('status')=='success':value=json.loads(reply['result']['result'])
                    else:value=reply
                    wire=encode(value)
                else:
                    name='human_eye_spatial_relations' if args.mode=='G' else 'human_eye_scene_observe'
                    arguments={'target':{'name':'Target'},'candidates':[{'name':'Peer_000'}]} if args.mode=='G' else {
                        'session_id':'scale-task','include_image':False,'query':{'mode':'surface_nearest','objects':[{'name':'Target'}]}}
                    req={'jsonrpc':'2.0','id':step+1,'method':'tools/call','params':{'name':name,'arguments':arguments}}
                    value=server.handle_jsonrpc_message(req);wire=encode(value)
                elapsed=time.perf_counter_ns()-mark
            except BaseException as exc:
                elapsed=time.perf_counter_ns()-mark;exception={'type':type(exc).__name__,'message':str(exc),'traceback':traceback.format_exc()}
            # Raw evidence publication does not replace actual result encoding.
            row={'group':args.group,'mode':args.mode,'scene':args.scene,'repeat_or_step':step,'entry_ns':elapsed,'cold':step==0,
                 'setup_ns_charged_to_cold':setup_ns if step==0 else 0,'rss_before':before,'rss_after':{'actor':memory(),'host':memory(pid)},
                 'response_bytes':None if wire is None else len(wire),'result':value,'exception':exception,
                 'meter':dict(meter.counts) if args.group=='N' else meter.snapshot()}
            rows.append(row);dump(out/('MEASUREMENT_%d.json'%step),row)
            if receipt is not None:dump(out/('NATIVE_RECEIPT_%d.json'%step),receipt)
            if req is not None:dump(out/('REQUEST_%d.json'%step),req)
            # Full readback is necessary evidence, additional RPC outside 78.
            if args.mode=='T':
                snap_receipt=native.run("print(_j.dumps(_scale_snapshot(),allow_nan=False,separators=(',',':')))\n",timeout_s=30)
                dump(out/('STATE_%d_RECEIPT.json'%step),snap_receipt)
                if snap_receipt['response'].get('status')!='success':raise ValueError('state_readback_failed')
                actual=json.loads(snap_receipt['response']['result']['result']);dump(out/('STATE_%d.json'%step),actual)
                e=load(HERE/'fixtures'/('T%d.json'%step));assert actual=={k:e[k] for k in ('unit_scale_m','objects')},'T_actual_mesh_binding'
            if exception:break
    except BaseException as exc:failed={'type':type(exc).__name__,'message':str(exc),'traceback':traceback.format_exc()}
    finally:
        if meter:meter.close()
        if service:
            try:service.host.close()
            except BaseException as exc:failed=failed or {'type':type(exc).__name__,'message':str(exc)}
        if native:
            close=native.close();dump(out/'WORKER_STATUS.json',native.status())
        dump(out/'CHAIN.json',{'group':args.group,'mode':args.mode,'scene':args.scene,'rows':len(rows),'error':failed,'pid':native.process.pid if native else None,
              'close':close,'whole_chain_ns':time.perf_counter_ns()-begun,'file_unchanged':sha(asset)==native.config['asset_sha256'] if native else None,
              'setup_ns':locals().get('setup_ns'),'rss':memory(),'entry_scope':'same owned socket/fingerprint helper; includes code/JSON/result encoding; raw evidence persistence tracked separately'})
    if failed:raise SystemExit(2)

def main():
    p=argparse.ArgumentParser();p.add_argument('--child',action='store_true');p.add_argument('--group');p.add_argument('--mode');p.add_argument('--scene');p.add_argument('--output');p.add_argument('--run',action='store_true');args=p.parse_args()
    if args.child:return child(args)
    assert args.run
    assert (HERE/'FREEZE.json').is_file(),'freeze_before_sampling'
    output=HERE/'measurements';output.mkdir(exist_ok=False)
    plan=[]
    for cell,scene,mode in [('G_low','G60_D12','G'),('G_mid','G508','G'),('G_high','G4092','G'),('D_low','G60_D12','D'),('D_mid','D48','D'),('D_high','D192','D')]:
        for group in ('N','P'):plan.append((cell,scene,mode,group))
    for repeat in range(3):
        for group in ('N','P'):plan.append(('T_round_%d'%repeat,'D48','T',group))
    receipts=[]
    for cell,scene,mode,group in plan:
        name=cell+'_'+group;folder=output/name;mark=time.perf_counter_ns()
        cmd=[str(PRODUCT_PY),'-I','-B','-X','utf8',str(Path(__file__).resolve()),'--child','--group',group,'--mode',mode,'--scene',scene,'--output',str(folder)]
        with (output/(name+'.stdout.txt')).open('wb') as stdout,(output/(name+'.stderr.txt')).open('wb') as stderr:
            process=subprocess.Popen(cmd,stdout=stdout,stderr=stderr,stdin=subprocess.DEVNULL,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            try:exitcode=process.wait(timeout=590)
            except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5);exitcode='coordinator_timeout'
        receipt={'cell':cell,'scene':scene,'mode':mode,'group':group,'actor_pid':process.pid,'exit_code':exitcode,'full_process_ns':time.perf_counter_ns()-mark}
        receipts.append(receipt);dump(output/'RUNS.json',receipts);print(json.dumps(receipt),flush=True)
    dump(output/'COMPLETE.json',{'physical_chains':len(receipts),'logical_expected':78,'runs':receipts})

if __name__=='__main__':main()
