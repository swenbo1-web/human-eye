"""The one frozen 27 pure-directory plus 9 continuous-two-step matrix."""
import argparse
import hashlib
import json
from pathlib import Path
import time
import traceback

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OLD_READY = ROOT/'verification/m4_selected_geometry_consumption_001/installation/READY.json'
NEW_READY = HERE.parent/'installation/READY.json'


def save(path, value):
    with Path(path).open('x', encoding='utf8', newline='\n') as stream:
        json.dump(value,stream,indent=2,allow_nan=False)
        stream.write('\n')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def schedule():
    result = []
    assets = ('simple_boxes','peripheral','rotated_asymmetric')
    orders = (('old','new','native'),('native','old','new'),('new','native','old'))
    for asset in assets:
        for repetition,order in enumerate(orders,1):
            for lane in order:
                result.append({'case_id':f'dir_{asset}_{repetition}_{lane}', 'asset':asset,
                               'lane':lane,'repetition':repetition,'two_step':False,'warm_count':10})
    for asset,order in zip(assets,orders):
        for lane in order:
            result.append({'case_id':f'two_{asset}_{lane}','asset':asset,'lane':lane,
                           'repetition':1,'two_step':True,'warm_count':0})
    return result


def prepare(output, old_ready, new_ready):
    old,new = [json.loads(path.read_bytes()) for path in (old_ready,new_ready)]
    assert old['source_count']==new['source_count']==137
    assert old['source_sha256']=='4ebc3910652ee461d9fa7476c8df0ecf6312580d6a02e1066c0eac88bef5c76c'
    assert new['source_sha256']=='6acb3ac7f014a590a279994f44be07c581af53a2da4dafae8dba9cd58eaea0bb'
    assert old['commit']=='00b13060a3cbe709b38f6e98ce04a6e5c3dabfb4'
    assert new['commit']=='fac9b4373575d653cc96f39f1dcb225300cd5977'
    assets = json.loads((HERE/'assets_01/INPUTS.json').read_bytes())['inputs']
    for asset in assets:
        assert sha(asset['asset'])==asset['asset_sha256']
    paths = [HERE/name for name in ('matrix.py','sample.py','probe.py','owned_native.py',
        'wire_meter.py','native_directory.py','reused/scene_residency.py','CONTRACT.md','analyze_saved.py',
        'BASELINE_FROZEN.json','assets_01/INPUTS.json','build_inputs.py',
        'check_native_cache.py','NATIVE_CACHE_CHECK_01.json','NATIVE_FORWARD_CHECK_02.json')]
    paths += [old_ready,new_ready,
        ROOT/'verification/m1_task_entry_001_eval/actor.py',
        ROOT/'verification/m1_task_entry_001_eval/preflight_client.py',
        ROOT/'verification/native_plugin_complex_003/actor.py',
        ROOT/'verification/native_plugin_complex_003/reused/accepted_native.py',HERE.parent/'check_native_forward.py']
    binding = {'schema':'m2-tight-directory-measurement-v1','schedule':schedule(),
        'source_files':{str(path.resolve()):sha(path) for path in paths},
        'old':old,'new':new,'assets':assets,'models':0,'profiler':False,
        'pure_sessions':27,'two_step_sessions':9,'pure_requests_per_session':11,
        'two_step_requests_per_session':2,
        'timing_scope':'actual Peer MCP complete call or original native execute complete call; entry layers differ',
        'instrumentation_scope':'same existing worker guards plus in-memory actual socket recording and resource counter scans; overhead retained',
        'native_freshness':'same reused SceneResidency notifications, finite fake-handler 16-case regression; actual Blender all-event native invalidation unmeasured',
        'native_correctness':'independent oracle exact equality for all vertices of the three fixed assets; general Python sum equivalence unproven',
        'new_source_first_recorded_before_final_matrix':True}
    output.mkdir(parents=True,exist_ok=False)
    save(output/'INPUT_BINDINGS.json',binding)
    return binding


def run(binding, output):
    import runpy
    assert not (HERE/'MATRIX_STARTED.json').exists(), 'one_matrix_already_reserved'
    for path,expected in binding['source_files'].items():
        assert sha(path)==expected,(path,'source_changed_before_matrix')
    module = runpy.run_path(str(HERE/'sample.py'),run_name='_m2_fixed_sample')
    started = time.perf_counter_ns()
    save(HERE/'MATRIX_STARTED.json',{'output':str(output),'started_ns':started,
        'input_bindings_sha256':sha(output/'INPUT_BINDINGS.json'),'sessions':36})
    result = {'started_ns':started,'schedule':binding['schedule'],'cases':[],'errors':[],
              'performance_retries':0,'all_planned_dispatched':False}
    try:
        for case in binding['schedule']:
            for path,expected in binding['source_files'].items():
                assert sha(path)==expected,(path,'source_changed_during_matrix')
            asset = next(value for value in binding['assets'] if value['name']==case['asset'])
            ready = binding['new'] if case['lane']=='new' else binding['old']
            value = module['run'](asset,ready,output/case['case_id'],case['lane'],
                two_step=case['two_step'],warm_count=case['warm_count'])
            result['cases'].append({'case':case,'result':str(output/case['case_id']/'RESULTS.json'),
                                    'passed':value['passed']})
            print(json.dumps({'case':case['case_id'],'passed':value['passed'],
                              'completed':len(result['cases']),'planned':36}),flush=True)
            if not value['passed']:
                raise RuntimeError('fixed_matrix_stop_on_sample_failure:'+case['case_id'])
        result['all_planned_dispatched'] = True
    except BaseException as exc:
        result['errors'].append({'type':type(exc).__name__,'message':str(exc),'traceback':traceback.format_exc()})
    result['ended_ns'] = time.perf_counter_ns()
    result['wall_ns'] = result['ended_ns']-started
    result['passed'] = result['all_planned_dispatched'] and not result['errors']
    result['source_files_unchanged'] = all(sha(path)==expected for path,expected in binding['source_files'].items())
    save(output/'RESULTS.json',result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--old-ready',type=Path,default=OLD_READY)
    parser.add_argument('--new-ready',type=Path,default=NEW_READY)
    parser.add_argument('--run',action='store_true',help='execute the single fixed matrix after preparation')
    args = parser.parse_args()
    output = args.output.resolve()
    binding = prepare(output,args.old_ready.resolve(),args.new_ready.resolve())
    if not args.run:
        print(json.dumps({'status':'prepared_only','bindings':str(output/'INPUT_BINDINGS.json')}))
        return 0
    result = run(binding,output)
    return 0 if result['passed'] else 1


if __name__=='__main__':
    raise SystemExit(main())
