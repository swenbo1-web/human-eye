"""One bounded fake-clock check: successful dispatch and exhausted setup.

Real frozen driver.prepare/run_models, fake files/actors/consumers only. The
root agent runs this script once; no original control or Blender suite runs.
"""
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
import traceback
import types
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
EVAL = HERE.parent
DRIVER_SHA = '21066d1a8b891784b2588626fb943e5b30a9ca8b6899dbcb7295724f562bf003'
S = 10**9
digest = lambda data: hashlib.sha256(data).hexdigest()


def put(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(data)


def fixture(out, label, original, driver):
    home = (out/'dummy'/label).resolve()
    home.mkdir(parents=True, exist_ok=False)
    plan, tasks = copy.deepcopy(original), copy.deepcopy(original['tasks'])
    for name in plan['dispatch_input_sha256']:
        if name not in ('TASKS.json', 'installation/READY.json'):
            put(home/name, (EVAL/name).read_bytes())
    for name in ('actor.py', 'consumer_transport.py', 'cli.bin'):
        put(home/name, b'FAKE NONEXECUTABLE DATA; never launch\n')
    for key, task in tasks.items():
        put(home/task['prompt'], (EVAL/task['prompt']).read_bytes())
        task.update(asset='fixtures/'+key+'.blend', snapshot='fixtures/'+key+'.json')
        put(home/task['asset'], b'FAKE NON-BLENDER ASSET\n')
        put(home/task['snapshot'], b'{"unit_scale_m":1,"objects":[]}')
        task['asset_sha256'] = digest((home/task['asset']).read_bytes())
        task['snapshot_sha256'] = digest((home/task['snapshot']).read_bytes())
        task['model_input_sha256'] = digest((home/'SESSION_RULES.txt').read_bytes()+b'\n'+(home/task['prompt']).read_bytes())
    ready = dict(source_sha256=driver.CANONICAL, dependency_python='FAKE-NOT-AN-EXECUTABLE', entry='FAKE', install_root='FAKE')
    put(home/'TASKS.json', json.dumps(tasks).encode())
    put(home/'installation/READY.json', json.dumps(ready).encode())
    plan.update(tasks=tasks, installation_ready=ready, preflight_driver_sha256=DRIVER_SHA,
        actor_sha256=digest((home/'actor.py').read_bytes()),
        consumer_transport_sha256=digest((home/'consumer_transport.py').read_bytes()),
        CLI_sha256=digest((home/'cli.bin').read_bytes()))
    plan['dispatch_input_sha256'] = {name:digest((home/name).read_bytes()) for name in plan['dispatch_input_sha256']}
    put(home/'PLAN.json', json.dumps(plan).encode())
    put(home/'GO.json', json.dumps(dict(task='M1-TASK-ENTRY-001_EVAL', authorized=True,
        plan_sha256=digest((home/'PLAN.json').read_bytes()), max_consumers=27)).encode())
    return home, plan


def check_branch(driver, original, out, expired):
    label = 'expired_during_ready_read' if expired else 'successful_including_last_accounting'
    home, plan = fixture(out, label, original, driver)
    initial = 1000*S
    clock = types.SimpleNamespace(now=initial, pending=None)
    starts, preparation_starts, spawned, consumed, closed, publications, accounting = [], [], [], [], [], [], []
    checks = 0
    actual_read, actual_sha, actual_save = driver.read, driver.sha, driver.save
    def sha(path):
        nonlocal checks
        if Path(path)==home/'TASKS.json':
            checks += 1
            if checks==1:
                clock.now += 7*S  # Initial batch input verification.
            else:
                starts.append(clock.now)  # Independent earliest cell origin.
                delay = 535 if expired or len(starts)>1 else 5
                clock.now += delay*S
        return actual_sha(path)
    def read(path):
        if Path(path)==home/'TASKS.json':
            preparation_starts.append(clock.now)
            clock.now += 11*S
        if Path(path)==home/'installation/READY.json':
            clock.now += (30 if expired else 13)*S
        return actual_read(path)
    def save(path, value):
        actual_save(path, value)
        if Path(path).name=='CONSUMER.json':
            accounting.append(dict(before=clock.now, after=clock.now+S))
            clock.now += S
        if Path(path)==home/'RUN_RESULT.json':
            before = clock.now
            clock.now += 4*S
            publications.append(dict(before=before, after=clock.now, summary='batch_ended_ns' in value))
    def popen(argv, **kwargs):
        config_path = Path(argv[argv.index('--config')+1])
        config = json.loads(config_path.read_bytes())
        folder = config_path.parent
        spawned.append(dict(config=config, folder=folder))
        clock.now += S
        clock.pending = (folder, config['task'])
        return types.SimpleNamespace(pid=9000+len(spawned), poll=lambda:None)
    def sleep(seconds):
        assert seconds==.02 and clock.pending is not None
        clock.now += S
        folder, task_id = clock.pending
        put(folder/'ENDPOINT.json', b'{"fake":true}')
        put(folder/'owner/INITIAL.json', (home/plan['tasks'][task_id]['snapshot']).read_bytes())
        clock.pending = None
    def consume(slot, config, frozen_plan, prompt):
        consumed.append(copy.deepcopy(slot))
        start = clock.now
        clock.now += 2*S
        return dict(started_ns=start, thread_id='fake-'+slot['cell'], safe_to_continue=True,
            exit_code=0, errors=[], unexpected_tool_deviations=[], final='unknown')
    def finish(folder, process):
        closed.append(folder.name)
        clock.now += 3*S
        return dict(confirmed=True, exit_code=0, close={'confirmed':True})
    transport = types.SimpleNamespace(EXE=home/'cli.bin', consume=consume)
    fake_time = types.SimpleNamespace(perf_counter_ns=lambda:clock.now, sleep=sleep)
    with patch.object(driver,'HERE',home), patch.object(driver,'time',fake_time), \
            patch.object(driver,'sha',sha), patch.object(driver,'read',read), patch.object(driver,'save',save), \
            patch.object(driver,'load',return_value=transport), patch.object(driver,'finish',finish), \
            patch.object(subprocess,'Popen',side_effect=popen):
        result = driver.run_models()  # Real prepare is deliberately unpatched.
    assert result['batch_started_ns']==initial
    assert starts[0]-initial==7*S and len(publications)==len(result['records'])+1
    assert publications[-1]['summary'] and not publications[-2]['summary']
    assert result['batch_ended_ns']==publications[-2]['after']==publications[-1]['before']
    assert clock.now-result['batch_ended_ns']==4*S  # Excluded summary's own publication.
    assert result['batch_ended_ns']-result['records'][-1]['cell_ended_ns']==(4 if expired else 5)*S
    assert result['batch_wall_ns']==result['batch_ended_ns']-initial
    if expired:
        assert len(spawned)==len(consumed)==len(closed)==0 and len(result['records'])==1
        assert accounting==[]
        row = result['records'][0]
        assert row['cell_started_ns']==starts[0] and row['full_cell_wall_ns']==576*S
        assert row['cell_ended_ns']-row['cell_started_ns']==576*S
        assert row['worker_deadline_ns']==starts[0]+570*S and not row['within_570s']
        assert any(e['type']=='TimeoutError' and e['message']=='original_full_cell_deadline_exceeded' for e in row['errors'])
        assert result['stop']=='original_full_cell_deadline_exceeded' and result['batch_wall_ns']==587*S
    else:
        assert consumed==plan['sequence'] and len(spawned)==len(closed)==27 and result['stop'] is None
        assert len(accounting)==27
        for index, row in enumerate(result['records']):
            delay = 5 if index==0 else 535
            start = starts[index]
            launch = json.loads((spawned[index]['folder']/'ACTOR_LAUNCH.json').read_bytes())
            assert row['cell_started_ns']==launch['cell_started_ns']==start
            assert preparation_starts[index]==launch['prepare_started_ns']==start+delay*S
            assert row['worker_deadline_ns']==launch['worker_deadline_ns']==spawned[index]['config']['worker_deadline_ns']==start+570*S
            assert launch['actor_startup_deadline_ns']==min(start+570*S,start+(delay+40)*S)
            assert row['consumer']['pre_consumer_setup_ns']==(delay+26)*S
            assert row['full_cell_wall_ns']==row['consumer']['total_task_wall_ns']==(delay+31)*S
            assert row['cell_ended_ns']-start==row['full_cell_wall_ns'] and row['within_570s']
        assert result['batch_wall_ns']==14894*S  # 7 + (36+1+4) + 26*(566+1+4).
    return dict(branch=label, passed=True, Popen=len(spawned), consumers=len(consumed),
        expected_cell_full_s=[576] if expired else [36]+[566]*26,
        expected_setup_s=[] if expired else [31]+[561]*26,
        original_run_result=result, statistics_publications=publications, consumer_accounting_publications=accounting,
        fake_clock_return_ns=clock.now, real_model_calls=0, real_Blender_calls=0)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('output',help='new immediate child, normally clock_check_01')
    args=p.parse_args()
    assert Path(args.output).name==args.output and args.output not in ('.','..')
    out=(HERE/args.output).resolve()
    assert out.parent==HERE.resolve() and not (EVAL/'GO.json').exists()
    out.mkdir(exist_ok=False)
    raw=(EVAL/'driver.py').read_bytes()
    assert digest(raw)==DRIVER_SHA
    driver=types.ModuleType('_m1_finalize_fake_clock_real_driver')
    driver.__file__=str(EVAL/'driver.py')
    records, blocked, success=[],[],False
    def forbidden(*args,**kwargs):
        blocked.append('real process/network/signal')
        raise AssertionError(blocked[-1])
    try:
        with ExitStack() as guards:
            for name in ('Popen','run','call','check_call','check_output'):
                guards.enter_context(patch.object(subprocess,name,side_effect=forbidden))
            for name in ('socket','create_connection'):
                guards.enter_context(patch.object(socket,name,side_effect=forbidden))
            for name in ('kill','system'):
                guards.enter_context(patch.object(os,name,side_effect=forbidden))
            exec(compile(raw,'verified-driver:'+DRIVER_SHA,'exec'),driver.__dict__)
            plan=json.loads((EVAL/'PLAN.json').read_bytes())
            assert len(plan['sequence'])==27 and len(plan['dispatch_input_sha256'])==7
            for expired in (False,True): records.append(check_branch(driver,plan,out,expired))
            assert not blocked and (EVAL/'driver.py').read_bytes()==raw and not (EVAL/'GO.json').exists()
            success=True
    except BaseException:
        (out/'FAILURE.txt').write_text(traceback.format_exc(),encoding='utf8')
        raise
    finally:
        (out/'RESULTS.json').write_text(json.dumps(dict(passed=success,branches=records,blocked_attempts=blocked,
            driver_sha256=DRIVER_SHA,test_sha256=digest(Path(__file__).read_bytes()),
            scope='fake-clock dispatch/preparation timing only; no original tests, product, model or Blender'),indent=2)+'\n',encoding='utf8')
        if success:
            owned=(out/'dummy').resolve()
            assert out.is_absolute() and owned.is_absolute() and owned.parent==out and owned.is_relative_to(out)
            shutil.rmtree(owned)
    print(json.dumps(dict(passed=True,branches=len(records),output=str(out))))


if __name__=='__main__': main()
