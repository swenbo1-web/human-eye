"""One authorized fixed driver invocation; no retry, scoring or arm analysis."""
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import time
import traceback

HERE=Path(__file__).resolve().parent
BATCH=HERE.parent
sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()


def save(name,value):
    with (HERE/name).open('x',encoding='utf8') as stream:
        json.dump(value,stream,indent=2,ensure_ascii=True)
        stream.write('\n')


def main():
    plan=json.loads((BATCH/'PLAN.json').read_bytes())
    assert not any((BATCH/name).exists() for name in ('STARTED.json','RUN_RESULT.json','cells'))
    path=BATCH/'runtime/driver.py'
    assert sha(path)==plan['preflight_driver_sha256']
    save('LAUNCH.json',{'controller_pid':os.getpid(),'controller_parent_pid':os.getppid(),
        'python':sys.executable,'argv':sys.argv,'started_utc':datetime.now(timezone.utc).isoformat(),
        'launcher_started_ns':time.perf_counter_ns(),'driver_sha256':sha(path),
        'plan_sha256':sha(BATCH/'PLAN.json'),'GO_sha256':sha(BATCH/'GO.json'),
        'one_driver_invocation':True,'maximum_consumers':6})
    spec=importlib.util.spec_from_file_location('_m4_formal_fixed_driver',path)
    driver=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(driver)
    value=None;error=None
    try:
        value=driver.run_models()
    except BaseException as exc:
        error={'type':type(exc).__name__,'message':str(exc),'traceback':traceback.format_exc()}
    finally:
        receipt={'controller_ended_utc':datetime.now(timezone.utc).isoformat(),
            'controller_ended_ns':time.perf_counter_ns(),'driver_returned':value is not None,
            'controller_error':error,'started_cells':None if value is None else value['started_cells'],
            'stop':None if value is None else value['stop'],
            'all_planned_dispatched':None if value is None else value['all_planned_dispatched'],
            'scope':'control/lifecycle receipt only; no scoring or group/cost analysis'}
        save('CONTROLLER_RETURN.json',receipt)
        print(json.dumps(receipt,ensure_ascii=True),flush=True)
    return 1 if error else 0


if __name__=='__main__':raise SystemExit(main())
