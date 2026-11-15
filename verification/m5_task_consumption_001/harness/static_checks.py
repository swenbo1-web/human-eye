"""No-live regression checks for A batching, public archives and limits."""
import ast
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
NAMESPACE = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(NAMESPACE))
from budget import Budget, save
import owned_runtime
import qual_driver
import run_formal


def pin(path):
    path = Path(path).resolve()
    raw = path.read_bytes()
    return dict(path=str(path), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())


class Client:
    def __init__(self, root):
        self.root = root
        self.records = []
        self.response = None

    def call(self, message):
        index = len(self.records)+1
        folder = self.root/'mcp'/('rpc_'+str(index).zfill(2))
        folder.mkdir(parents=True)
        response = {'jsonrpc':'2.0','id':message['id'],'result':{'isError':False,'content':[{
            'type':'text','text':json.dumps({'result_kind':'task_query','binding':{'objects':[{'name':'M4_Far_00','object_id':'test'}]}})}]}}
        tx = (json.dumps(message)+'\n').encode()
        rx = (json.dumps(response)+'\r\n').encode()
        (folder/'TX.bin').write_bytes(tx)
        (folder/'RX.bin').write_bytes(rx)
        started = time.perf_counter_ns()
        self.records.append(dict(index=index,started_ns=started,stdin_flushed_ns=started,
            received_complete_ns=started+1,closed_ns=started+2,TX_bytes=len(tx),RX_bytes=len(rx)))
        self.response=response
        return response


def main():
    out = NAMESPACE/'STATIC_CHECKS'
    out.mkdir(exist_ok=False)
    checks=[]

    def check(name, condition):
        checks.append(dict(name=name,passed=bool(condition)))
        if not condition:
            raise ValueError(name)

    for path in sorted(HERE.rglob('*.py')):
        ast.parse(path.read_text(encoding='utf8'))
    check('all harness source parses without runtime', True)
    for group, expected in [('A',2),('B',1)]:
        calls=[]
        def observe(query=None,include_image=True):
            calls.append(dict(kind='observe',query=query,include_image=include_image))
            return {'current':'original_observation'}
        def task(query):
            calls.append(dict(kind='task',query=query))
            return {'current':'original_measurement'}
        with contextlib.redirect_stdout(io.StringIO()):
            exec(compile(qual_driver.qualification_code(group),'<mock-qualification>','exec'),dict(observe=observe,task=task))
        check(group+'/one execute performs exact internal public request count',len(calls)==expected)
        if group=='A':
            check('A/single-tool batch preserves observe then legacy task',calls[0]['kind']=='observe'
                  and calls[1]['kind']=='task' and calls[1]['query']['requested_facts']==['surface_proximity'])
        else:
            check('B/one original joint query',calls[0]['query']['task_query']['objects']
                  ==[{'name':'M4_Far_00'},{'name':'M4_Near'}])
    ledger=Budget(out/'ledger')
    for number in range(6):
        ledger.reserve('consumer_task','C'+str(number),'formal',1)
    try:
        ledger.reserve('consumer_task','C7','formal',1)
    except RuntimeError as error:
        check('seventh consumer rejected by persistent admission',str(error)=='consumer_task_budget_exhausted_or_wrong_phase')
    else:
        raise ValueError('seventh consumer accepted')
    for number in range(12):
        ledger.reserve('business_tool','same_slot','formal',1)
    try:
        ledger.reserve('business_tool','same_slot','formal',1)
    except RuntimeError:
        check('outer business tool thirteenth rejected',True)
    else:
        raise ValueError('outer tool overrun accepted')
    for number in range(6):
        ledger.reserve('raster_attempt','render_slot','formal',1)
    try:
        ledger.reserve('raster_attempt','render_slot','formal',1)
    except RuntimeError:
        check('unknown raster reservations retain six-slot upper bound',ledger.snapshot()['slots']['render_slot']['raster_upper']==6)
    else:
        raise ValueError('seventh raster accepted')
    root=out/'ordinary_task'
    root.mkdir()
    producer=root/'product_full/call_001'
    producer.mkdir(parents=True)
    raw={'result_kind':'task_query','binding':{'objects':[{'name':'M4_Far_00','object_id':'test'}]}}
    save(producer/'SERVICE_RESULT.json',raw)
    entry=dict(index=1,path=str(producer/'SERVICE_RESULT.json'),sha256=pin(producer/'SERVICE_RESULT.json')['sha256'])
    (root/'product_full/INDEX.jsonl').write_text(json.dumps(entry)+'\n',encoding='utf8')
    runtime=owned_runtime.RootRuntime()
    runtime.consumer_deadline_ns=time.perf_counter_ns()+60_000_000_000
    runtime.poisoned=False
    runtime.native=None
    runtime.runroot=root
    runtime.group='A'
    runtime.label='mock_A'
    runtime.binding={'source_sha256':owned_runtime.PRODUCT_SHA256['A']}
    runtime._product_calls=0
    runtime.public_requests=[]
    runtime.source_reads=[]
    runtime.by_ref={}
    runtime.client=Client(root)
    arguments={'query':{'mode':'task','objects':[{'name':'M4_Far_00'},{'name':'M4_Near'}],
        'requested_facts':['surface_proximity']},'include_image':False}
    response=runtime.public_request(arguments)
    check('ordinary task without object_index passes no-frame archive',response is runtime.client.response)
    check('public arguments transparent and detail remains omitted',runtime.public_requests[0]['request']['params']['arguments']==arguments
          and 'response_detail' not in runtime.public_requests[0]['request']['params']['arguments'])
    record=runtime.public_requests[0]
    check('actual internal request response wire pins and producer index saved',
          Path(record['actual_RX_path']).exists() and Path(record['response_path']).exists()
          and record['producer_archive_index']==record['internal_public_call_index']==1)
    check('internal public request does not increment outer business budget',ledger.snapshot()['counts']['business_admissions']==12)
    source=HERE/'mcp_entry.py'
    tree=ast.parse(source.read_text())
    main_node=next(node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name=='main')
    observer=next(node for node in main_node.body if isinstance(node,ast.ClassDef) and node.name=='ObservedService')
    spec=importlib.util.spec_from_file_location('_m5_static_mcp_entry',source)
    entry_module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(entry_module)
    archive=out/'observer'
    archive.mkdir()
    sentinel={'result_kind':'task_query','binding':{'objects':[]}}
    class Service:
        def __init__(self,*args,**kwargs):
            pass
        def observe(self,*args,**kwargs):
            return sentinel
    namespace=dict(entry_module.__dict__,LiveSpatialService=Service,args=SimpleNamespace(archive=archive))
    exec(compile(ast.Module(body=[observer],type_ignores=[]),str(source),'exec'),namespace)
    observed=namespace['ObservedService']()
    returned=observed.observe()
    check('same producer returned and archived once before formatter',returned is sentinel
          and len(list(archive.glob('call_*')))==1
          and json.loads((archive/'call_001/SERVICE_RESULT.json').read_bytes())==sentinel)
    check('passive read context archive present', (archive/'call_001/READ_CONTEXT.json').exists())
    check('formal fixed order and both actual products held',run_formal.SEQUENCE==[
        ('A1','A'),('B1','B'),('B2','B'),('A2','A'),('A3','A'),('B3','B')])
    files=sorted(HERE.rglob('*.py'))
    report=dict(schema='m5-task-harness-static-v1',passed=True,checks=checks,
        source_pins=[pin(path) for path in files],actual_Blender_starts=0,actual_MCP_starts=0,
        actual_model_consumers=0,actual_rasters=0,
        scope='Synthetic ledgers/public packets only. Real Blender, default brief, image delivery and source/measurement acceptance still require root A/B qualification.')
    save(out/'RESULT.json',report)
    print(json.dumps(dict(passed=True,checks=len(checks),result_sha256=pin(out/'RESULT.json')['sha256'])))


if __name__=='__main__':
    main()
