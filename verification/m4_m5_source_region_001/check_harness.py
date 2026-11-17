"""Check the fixed owned/raster admission and the actual public-ref handoff."""

import ast
import hashlib
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
    spec=importlib.util.spec_from_file_location('_source_region_budget',HERE/'harness/budget.py')
    ledger=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ledger)
    def reject(name,operation):
        try:
            operation()
        except RuntimeError:
            checks.append(dict(name=name,passed=True))
        else:
            checks.append(dict(name=name,passed=False))
    with tempfile.TemporaryDirectory(prefix='source_region_budget_') as temporary:
        budget=ledger.Budget(temporary)
        for i in range(8):
            token=budget.reserve('Blender_start','synthetic_'+str(i))
            budget.settle_start(token,pid=1,spawn_status='synthetic',outcome='test')
        for i in range(24):
            token=budget.reserve('raster_attempt','synthetic')
            budget.settle_rasters(token,actual=1,lower_bound=1,evidence=dict(synthetic=True),outcome='test')
        reject('ninth_owned',lambda:budget.reserve('Blender_start','ninth'))
        reject('twenty_fifth_raster',lambda:budget.reserve('raster_attempt','synthetic'))
        reject('model_consumer',lambda:budget.reserve('consumer_task','synthetic'))
    runner=(HERE/'harness/run_slot.py').read_text(encoding='utf8')
    checks.append(dict(name='original_public_ref_handoff',passed="completed['public_result']['region_ref']" in runner))
    checks.append(dict(name='error_outcome_checked_before_next_stage',passed='is_error != expected_error' in runner))
    result=dict(schema='source-region-harness-controls-v1',passed=all(row['passed'] for row in checks),checks=checks,
        fixture_preparation_count=1,live_qualification_starts=0,live_raster=0,model_consumers=0,
        source_pins=[dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest()) for path in (HERE/'harness/run_slot.py',HERE/'harness/budget.py')])
    with (HERE/'HARNESS_CONTROLS.json').open('x',encoding='utf8',newline='\n') as stream:
        json.dump(result,stream,sort_keys=True,indent=2)
        stream.write('\n')
    print(json.dumps(dict(passed=result['passed'],checks=len(checks))))
    if not result['passed']:
        raise SystemExit(1)


if __name__=='__main__':
    main()
