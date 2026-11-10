"""Five dispatch-only counterexamples; never load a consumer or product."""
import argparse
from contextlib import ExitStack
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import time
import traceback
import types
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
digest = lambda raw: hashlib.sha256(raw).hexdigest()


def put(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(raw)


def run_case(driver, real_plan, out, case):
    home = (out/'dummy'/case).resolve()
    home.mkdir(parents=True, exist_ok=False)
    plan = copy.deepcopy(real_plan)
    for name in plan['dispatch_input_sha256']:
        put(home/name, (HERE/name).read_bytes())
    for name in ('consumer_transport.py', 'actor.py'):
        put(home/name, b'FAKE DATA ONLY: never execute this file\n')
    put(home/'cli.bin', b'FAKE NONEXECUTABLE CLI\n')
    for key, task in plan['tasks'].items():
        put(home/task['prompt'], (HERE/task['prompt']).read_bytes())
        task['snapshot'] = 'snapshots/'+key+'.json'
        snapshot = b'{"unit_scale_m":1,"objects":[]}'
        put(home/task['snapshot'], snapshot)
        task['snapshot_sha256'] = digest(snapshot)
        task['model_input_sha256'] = digest((home/'SESSION_RULES.txt').read_bytes()+b'\n'+(home/task['prompt']).read_bytes())
    plan.update(consumer_transport_sha256=digest((home/'consumer_transport.py').read_bytes()),
        actor_sha256=digest((home/'actor.py').read_bytes()), preflight_driver_sha256=digest(Path(driver.__file__).read_bytes()),
        CLI_sha256=digest((home/'cli.bin').read_bytes()))
    plan['installation_ready'] = {'dependency_python': 'FAKE-NOT-AN-EXECUTABLE'}
    put(home/'PLAN.json', (json.dumps(plan, sort_keys=True)+'\n').encode())
    put(home/'GO.json', json.dumps({'task':'M1-TASK-ENTRY-001_EVAL','authorized':True,
        'plan_sha256':digest((home/'PLAN.json').read_bytes()),'max_consumers':27}).encode())
    if case == 'frozen_tasks_drift':
        with (home/'TASKS.json').open('ab') as stream:
            stream.write(b'\n')
    consumed, prepared, finished, loaded = [], [], [], []
    def consume(slot, config, ignored_plan, prompt):
        consumed.append(copy.deepcopy(slot))
        result = dict(thread_id='fake-thread-'+slot['cell'], safe_to_continue=True,
            errors=[], exit_code=0, started_ns=time.perf_counter_ns(), final='unknown', unexpected_tool_deviations=[])
        if case == 'cli_configuration_failure':
            result.update(thread_id=None, exit_code=2, errors=[{'type':'ValueError','message':'CLI configuration rejected'}])
        if case == 'known_450s_timeout':
            result.update(exit_code=1, errors=[{'type':'TimeoutError','message':'original_absolute_session_deadline'}])
        return result
    def prepare(slot, *, output):
        prepared.append(copy.deepcopy(slot))
        put(output/'owner/INITIAL.json', (home/plan['tasks'][slot['task']]['snapshot']).read_bytes())
        return output, object(), time.perf_counter_ns()-(571*10**9 if case=='full_570s_exceeded' else 0)
    def finish(folder, process):
        finished.append(folder.name)
        return {'confirmed':True, 'exit_code':0, 'close':{'confirmed':True}}
    def load(name, path):
        assert Path(path)==home/'consumer_transport.py'
        loaded.append(name)
        return types.SimpleNamespace(EXE=home/'cli.bin', consume=consume)
    result, error = None, None
    with patch.object(driver,'HERE',home), patch.object(driver,'load',load), \
            patch.object(driver,'prepare',prepare), patch.object(driver,'finish',finish):
        try:
            result = driver.run_models()
        except AssertionError as exc:
            error = str(exc)
    expected = 0 if case=='frozen_tasks_drift' else 1 if case in ('cli_configuration_failure','full_570s_exceeded') else 27
    assert len(consumed)==len(prepared)==len(finished)==expected
    assert consumed==prepared==plan['sequence'][:expected]
    assert finished==[slot['cell'] for slot in plan['sequence'][:expected]]
    if case=='frozen_tasks_drift':
        assert error=='frozen_dispatch_input_changed: TASKS.json' and not loaded and not (home/'STARTED.json').exists()
    else:
        expected_stop = {'cli_configuration_failure':'CLI_launch_configuration_or_protocol_failure; no repeated consumers',
            'full_570s_exceeded':'original_full_cell_deadline_exceeded'}.get(case)
        assert error is None and result['stop']==expected_stop and len(result['records'])==expected
        assert len(loaded)==1
        if case in ('normal_unknown','known_450s_timeout'):
            assert all(row['consumer']['final']=='unknown' and row['finish']['confirmed'] for row in result['records'])
    return {'case':case,'passed':True,'consumed':len(consumed),'prepared':len(prepared),'finished':len(finished),
        'stop':None if result is None else result['stop'],'exception':error,'consumed_sequence':consumed,
        'fake_GO_only':str(home/'GO.json'),'real_consumer_transport_loaded':False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', help='new immediate child output directory, e.g. dispatch_control_01')
    args = parser.parse_args()
    assert Path(args.output).name==args.output and args.output not in ('.','..')
    out = (HERE/args.output).resolve()
    assert out.parent==HERE.resolve() and not (HERE/'GO.json').exists(), 'no real GO permitted in this test'
    out.mkdir(exist_ok=False)
    raw = (HERE/'driver.py').read_bytes()
    driver = types.ModuleType('_m1_dispatch_control_real_driver')
    driver.__file__ = str(HERE/'driver.py')
    records, blocked = [], []
    def forbidden(*args, **kwargs):
        blocked.append('subprocess/socket/signal')
        raise AssertionError(blocked[-1])
    success = False
    try:
        with ExitStack() as guards:
            for name in ('Popen','run','call','check_call','check_output'):
                guards.enter_context(patch.object(subprocess,name,side_effect=forbidden))
            for name in ('system','kill'):
                guards.enter_context(patch.object(os,name,side_effect=forbidden))
            for name in ('socket','create_connection'):
                guards.enter_context(patch.object(socket,name,side_effect=forbidden))
            exec(compile(raw,'verified-driver:'+digest(raw),'exec'),driver.__dict__)
            plan = json.loads((HERE/'PLAN.json').read_bytes())
            assert len(plan['sequence'])==27 and len(plan['dispatch_input_sha256'])==7
            for case in ('cli_configuration_failure','full_570s_exceeded','normal_unknown','known_450s_timeout','frozen_tasks_drift'):
                records.append(run_case(driver,plan,out,case))
            assert not blocked and (HERE/'driver.py').read_bytes()==raw and not (HERE/'GO.json').exists()
            success = True
    except BaseException:
        (out/'FAILURE.txt').write_text(traceback.format_exc(),encoding='utf8')
        raise
    finally:
        (out/'RESULTS.json').write_text(json.dumps({'passed':success,'cases':records,'blocked_attempts':blocked,
            'driver_sha256':digest(raw),'test_sha256':digest(Path(__file__).read_bytes()),'real_model_calls':0,
            'real_Blender_calls':0,'production_calls':0,'fake_domains_retained_on_failure':not success},indent=2)+'\n',encoding='utf8')
        if success:
            owned=(out/'dummy').resolve()
            assert out.is_absolute() and owned.is_absolute() and owned.parent==out and owned.is_relative_to(out)
            shutil.rmtree(owned)
    print(json.dumps({'passed':True,'cases':len(records),'output':str(out)}))


if __name__=='__main__': main()
