"""Source and synthetic budget checks for this batch's finite live caller."""

import ast
import importlib.util
import json
from pathlib import Path
import tempfile

HERE=Path(__file__).resolve().parent


def main():
    checks=[]
    for path in sorted((HERE/'harness').rglob('*.py')):
        ast.parse(path.read_bytes())
        checks.append(dict(name='parse/'+path.name,passed=True))
    spec=importlib.util.spec_from_file_location('_cross_budget_test',HERE/'harness/budget.py')
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    def rejects(name,operation):
        try:
            operation()
        except RuntimeError:
            checks.append(dict(name=name,passed=True))
        else:
            checks.append(dict(name=name,passed=False))
    with tempfile.TemporaryDirectory(prefix='cross_budget_') as directory:
        budget=module.Budget(directory)
        for index in range(8):
            token=budget.reserve('Blender_start','synthetic_'+str(index))
            budget.settle_start(token,pid=1,spawn_status='synthetic',outcome='test')
        for index in range(64):
            token=budget.reserve('raster_attempt','synthetic')
            budget.settle_rasters(token,actual=1,lower_bound=1,evidence=dict(synthetic=True),outcome='test')
        rejects('ninth_owned_rejected',lambda:budget.reserve('Blender_start','ninth'))
        rejects('sixty_fifth_raster_rejected',lambda:budget.reserve('raster_attempt','synthetic'))
        rejects('model_consumer_rejected',lambda:budget.reserve('consumer_task','synthetic'))
    original=ast.parse((HERE.with_name('m4_global_local_qualification_001')/'harness/owned_runtime.py').read_bytes())
    current=ast.parse((HERE/'harness/owned_runtime.py').read_bytes())
    for name in ('correlate_archive','public_request','close','_start_mcp'):
        left=next(node for node in ast.walk(original) if isinstance(node,ast.FunctionDef) and node.name==name)
        right=next(node for node in ast.walk(current) if isinstance(node,ast.FunctionDef) and node.name==name)
        checks.append(dict(name='accepted_runtime_AST/'+name,passed=ast.dump(left)==ast.dump(right)))
    result=dict(passed=all(row['passed'] for row in checks),checks=checks,actual_Blender=0,actual_raster=0,model_calls=0)
    with (HERE/'HARNESS_PURE.json').open('x',encoding='utf8',newline='\n') as stream:
        json.dump(result,stream,sort_keys=True,indent=2)
        stream.write('\n')
    print(json.dumps(dict(passed=result['passed'],checks=len(checks))))
    if not result['passed']:
        raise SystemExit(1)


if __name__=='__main__':
    main()
