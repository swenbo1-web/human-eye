"""Check changed recovery context and fixed sequence without live execution."""
import ast
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
NAMESPACE=HERE.parent
sys.path.insert(0,str(HERE))
import budget
import owned_runtime
import qual_driver
import run_slot


def pin(path):
    path=Path(path).resolve()
    raw=path.read_bytes()
    return dict(path=str(path),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())


def function_ast(path,name,class_name=None):
    tree=ast.parse(Path(path).read_text(encoding='utf8'))
    body=tree.body if class_name is None else next(node for node in tree.body if isinstance(node,ast.ClassDef) and node.name==class_name).body
    node=next(node for node in body if isinstance(node,ast.FunctionDef) and node.name==name)
    return ast.dump(node,include_attributes=False)


def main():
    out=NAMESPACE/'MIGRATION_CHECKS'
    out.mkdir(exist_ok=False)
    checks=[]
    def check(name,value):
        checks.append(dict(name=name,passed=bool(value)))
        if not value:
            raise ValueError(name)
    original=NAMESPACE.parent/'m5_task_consumption_001/recovery_candidate/owned_runtime.py'
    check('approved candidate source unchanged',pin(original)['sha256']=='371049158c7370a0e29e30992e5b1fe2cd6d6ba726688e77017ca44c27f94318')
    for name,owner in [('correlate_archive',None),('public_request','RootRuntime')]:
        check('correlation algorithm unchanged/'+name,
              function_ast(original,name,owner)==function_ast(HERE/'owned_runtime.py',name,owner))
    check('new owned namespace and root',owned_runtime.HERE==HERE and owned_runtime.NAMESPACE==NAMESPACE
          and owned_runtime.EXTERNAL==Path('D:/he_m5_harness_recovery_001'))
    check('new root-held driver context',run_slot.HERE==HERE and run_slot.NAMESPACE==NAMESPACE
          and run_slot.EXTERNAL==Path('D:/he_m5_harness_recovery_001'))
    source=(HERE/'owned_runtime.py').read_text()
    driver_source=(HERE/'run_slot.py').read_text()
    check('worker uses original600 window',
          'self.consumer_deadline_ns = self.deadline_ns\n' in source
          and 'consumer_deadline = owned_deadline\n' in driver_source
          and '450_000_000_000' not in source+driver_source
          and 'launcher.py' not in driver_source)
    check('only new global budgets',budget.LIMITS==dict(Blender_start_attempts=2,all_rasters=12,consumer_tasks=0))
    ledger=budget.Budget(out/'mock_budget')
    for _ in range(2):
        ledger.reserve('Blender_start','mock')
    try:
        ledger.reserve('Blender_start','mock')
    except RuntimeError:
        check('third owned admission rejected',True)
    else:
        raise ValueError('third owned admitted')
    for _ in range(13):
        ledger.reserve('business_tool','same_mock')
    check('old twelve-tool model limit removed',ledger.snapshot()['counts']['business_admissions']==13)
    for _ in range(12):
        ledger.reserve('raster_attempt','same_mock')
    check('one session can use new total bound without old six-slot cap',ledger.snapshot()['slots']['same_mock']['raster_upper']==12)
    try:
        ledger.reserve('raster_attempt','same_mock')
    except RuntimeError as error:
        check('thirteenth raster rejected against total',str(error)=='recovery_total_raster_budget_exhausted')
    else:
        raise ValueError('thirteenth raster admitted')
    try:
        ledger.reserve('consumer_task','mock','formal')
    except RuntimeError as error:
        check('model consumer admission rejected',str(error)=='recovery_model_consumers_forbidden')
    else:
        raise ValueError('model consumer admitted')
    request_file=json.loads((HERE/'REQUESTS.json').read_bytes())
    check('frozen4outer5inner expectation',request_file['outer_tool_calls']==4 and request_file['internal_public_calls']==5
          and request_file['expected_service_indices']==[1,None,2,3,4])
    for group in ['A','B']:
        messages=qual_driver.recovery_messages(group)
        check(group+'/registered programs exact',messages==request_file['groups'][group])
        namespace={}
        calls=[]
        replies=[]
        def observe(query=None,include_image=True):
            error='target' in query
            result=dict(status='error' if error else 'partial' if 'closed_solid_relation' in query.get('requested_facts',[]) else 'complete',
                        test_query=query)
            namespace['last_product_is_error']=error
            calls.append(query)
            replies.append(result)
            return result
        namespace.update(observe=observe,task=lambda query:observe(query,False))
        markers=[]
        for message in messages:
            stdout=io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exec(message['params']['arguments']['code'],namespace)
            markers.extend(json.loads(line[len(qual_driver.MARKER):]) for line in stdout.getvalue().splitlines())
        check(group+'/five original snapshots and isError markers',len(calls)==5
            and [m['step'] for m in markers]==request_file['expected_markers']
            and [m['isError'] for m in markers]==[False,True,False,False,False]
            and [m['public_result'] for m in markers]==replies)
    result=dict(schema='m5-harness-recovery-migration-checks-v1',passed=True,checks=checks,
        input_pins=[pin(original),pin(Path(__file__)),pin(HERE/'REQUESTS.json')]
            +[pin(path) for path in sorted(HERE.rglob('*.py'))],
        historical_pure_reference=dict(path=str((NAMESPACE.parent/'m5_task_consumption_001/recovery_candidate/PURE_01/RESULT.json').resolve()),
            sha256='7dc9867f224e313aa70bcbbb55296313dbec0369eb66327014959606009ee89e',reexecuted=False),
        actual_Blender_MCP_models_rasters=0,
        scope='Only changed paths/deadlines/globalbudget and the fixed ordinary Python programs. Existing correlation matrix referenced; independent new controls separately review continuous rejection/service gaps.')
    budget.save(out/'RESULT.json',result)
    print(json.dumps(dict(passed=True,checks=len(checks),sha256=pin(out/'RESULT.json')['sha256'])))


if __name__=='__main__':
    main()
