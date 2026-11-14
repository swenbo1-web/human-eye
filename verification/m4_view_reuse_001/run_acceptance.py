"""Root-only installed integration and the preregistered five paired blocks."""

import argparse
import ast
import copy
import csv
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import statistics
import subprocess
import time
import zipfile


HERE = Path(__file__).resolve().parent
OLD = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_routed_task_benefit_001')
ORDER = [('old','new'),('new','old'),('old','new'),('new','old'),('old','new')]
OLD_SOURCE = '6d4f7d363aaa48081eff7db467fff20665419172560f19b3a4ccb0fbb46c900f'


def read(path):
    return json.loads(Path(path).read_bytes())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    with Path(path).open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2)
        stream.write('\n')


def verify_sources(bindings_path, frozen_path):
    frozen = read(frozen_path)
    for path, expected in frozen['files_sha256'].items():
        if sha(path) != expected:
            raise ValueError('frozen_source_changed:' + path)
    bindings = read(bindings_path)
    required = [HERE/'case_worker.py', HERE/'run_acceptance.py', HERE/'PLAN.json', Path(bindings_path),
                HERE/'bridge.py', HERE/'native_tools.py', HERE/'bootstrap.py',
                OLD/'bridge.py', OLD/'native_tools.py', OLD/'bootstrap.py']
    for key in ('base_python','verified_bootstrap','old_binding','new_binding'):
        item = bindings[key]
        if sha(item['path']) != item['sha256']:
            raise ValueError('bound_runtime_changed:' + key)
        required.append(Path(item['path']))
    for key in ('old_binding','new_binding'):
        binding = read(bindings[key]['path'])
        for row in binding['source_manifest']:
            path = Path(binding['install_root'])/row['path']
            if sha(path) != row['sha256']:
                raise ValueError('installed_source_changed:' + str(path))
            required.append(path)
    if read(bindings['old_binding']['path'])['source_sha256'] != OLD_SOURCE:
        raise ValueError('fixed_old_install_required')
    for path in required:
        absolute = str(path.resolve())
        if frozen['files_sha256'].get(absolute) != sha(path):
            raise ValueError('required_runtime_not_frozen:' + absolute)
    sources = {str(p.resolve()):sha(p) for p in required}
    return bindings, sources


def stop_helper():
    path = OLD.parent/'m4_active_coverage_003/launch.py'
    module_spec = importlib.util.spec_from_file_location('_view_reuse_accepted_process_cleanup',path)
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    return module.stop_process


def configuration(bindings, sample, mode, variant):
    previous = read(OLD/'inputs/SOURCES.json')
    specification = bindings['old_binding' if variant=='old' else 'new_binding']
    manifest = copy.deepcopy(previous)
    manifest['product_binding'] = specification
    manifest['budget_contract'] = dict(external_root=str(sample),formal_root=str(sample),
        preparation_root=str(sample/'unused_preparation'),ledger_root=str(sample/'ledger'),
        formal_cap=6,preparation_cap=0,per_slot_cap=6,total_cap=44)
    manifest_path = sample/'SOURCES.json'
    save(manifest_path,manifest)
    bridge = OLD/'bridge.py' if variant=='old' else HERE/'bridge.py'
    control = dict(mode=mode,variant=variant,output=str(sample/'w'),
                   bridge=dict(path=str(bridge),sha256=sha(bridge)))
    if mode=='legacy_capability':
        legacy = bindings['legacy_service_result']
        if sha(legacy['path'])!=legacy['sha256']:
            raise ValueError('sealed_legacy_source_changed')
        control['legacy_frame'] = next(f for f in read(legacy['path'])['frames'] if f['view_name']=='SCENE')
    config = dict(group='P' if mode in ('benchmark','product_then_reuse') else 'N',
        output=str(sample/'o'),endpoint=str(sample/'UNUSED_ENDPOINT.json'),
        worker_deadline_ns=time.perf_counter_ns()+450_000_000_000,
        input_manifest=str(manifest_path),max_tool_calls=12,max_render_attempts=6,
        phase='formal',budget_root=str(sample/'ledger'),whole_render_cap=44,phase_render_cap=6,
        runtime_binding=dict(binding=specification,verified_bootstrap=bindings['verified_bootstrap']),
        verification_control=control)
    path = sample/'CONFIG.json'
    save(path,config)
    return path,config


def run_one(bindings, parent, name, mode, variant, cleanup):
    sample = parent/name
    sample.mkdir(parents=True,exist_ok=False)
    config_path,config = configuration(bindings,sample,mode,variant)
    command = [bindings['base_python']['path'],'-I','-B','-X','utf8',str(HERE/'bootstrap.py'),
               str(HERE/'case_worker.py'),'--config',str(config_path)]
    process = None
    errors = []
    worker = None
    process_cleanup = None
    started = time.perf_counter_ns()
    with (sample/'STDOUT.bin').open('wb') as stdout,(sample/'STDERR.bin').open('wb') as stderr:
        try:
            process = subprocess.Popen(command,stdin=subprocess.PIPE,stdout=stdout,stderr=stderr,cwd=sample,
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            process.wait(timeout=max(.01,(config['worker_deadline_ns']-time.perf_counter_ns())/1e9))
        except BaseException as error:
            errors.append(dict(type=type(error).__name__,message=str(error)))
        finally:
            if process is not None:
                process_cleanup = cleanup(process,timeout=5)
    closed = time.perf_counter_ns()
    result_path = sample/'w/WORKER_RESULT.json'
    if result_path.exists():
        worker = read(result_path)
        if process is None or worker['process_id']!=process.pid:
            errors.append(dict(type='ValueError',message='actual_base_worker_PID_mismatch'))
    else:
        errors.append(dict(type='ValueError',message='worker_result_missing'))
    passed = bool(worker and worker['passed'] and process_cleanup and process_cleanup['confirmed']
                  and process_cleanup['exit_code']==0 and not errors)
    row = dict(name=name,mode=mode,variant=variant,passed=passed,worker=worker,
        process_id=None if process is None else process.pid,process_cleanup=process_cleanup,errors=errors,
        command=command,started_ns=started,process_and_streams_closed_ns=closed,elapsed_ns=closed-started,
        scope='Parent Popen boundary through actual held-handle cleanup and stdout/stderr close. Configuration generation and this receipt publication excluded.',
        worker_result_path=str(result_path),worker_result_sha256=sha(result_path) if result_path.exists() else None)
    save(sample/'PROCESS_RESULT.json',row)
    return row


def npy_payload(raw):
    length_bytes=2 if raw[6]==1 else 4
    length=int.from_bytes(raw[8:8+length_bytes],'little')
    header=ast.literal_eval(raw[8+length_bytes:8+length_bytes+length].decode('latin1'))
    return header,raw[8+length_bytes+length:]


def unchanged_product_facts(bindings, sample):
    old_spec = bindings['legacy_service_result']
    if sha(old_spec['path'])!=old_spec['sha256']:
        raise ValueError('old_facts_changed')
    old = read(old_spec['path'])
    current = read(Path(sample['worker_result_path']).parents[1]/'o/product_call_01/SERVICE_RESULT.json')
    fields = ['regions','coverage','scope','inspection','region_evidence','location_conventions']
    checks = {name:old['facts'][name]==current['facts'][name] for name in fields}
    old_views=[entry['view_name'] for entry in old['facts']['observations']]
    new_views=[entry['view_name'] for entry in current['facts']['observations']]
    checks['observation_count_order_and_unique_views'] = (old_views==new_views
        and len(set(old_views))==len(old_views) and len(set(new_views))==len(new_views))
    old_frame_views=[entry['view_name'] for entry in old['frames']]
    new_frame_views=[entry['view_name'] for entry in current['frames']]
    checks['frame_count_order_and_unique_views'] = (old_frame_views==new_frame_views
        and len(set(old_frame_views))==len(old_frame_views) and len(set(new_frame_views))==len(new_frame_views))
    if not checks['observation_count_order_and_unique_views'] or not checks['frame_count_order_and_unique_views']:
        return dict(passed=False,checks=checks,old_observation_views=old_views,
                    new_observation_views=new_views,old_frame_views=old_frame_views,new_frame_views=new_frame_views)
    for old_observation,new_observation in zip(old['facts']['observations'],current['facts']['observations']):
        checks[old_observation['view_name']+':pixel_facts'] = old_observation['pixel_rows']==new_observation['pixel_rows']
    old_frames={f['view_name']:f for f in old['frames']}
    for new in current['frames']:
        prior=old_frames[new['view_name']]
        checks[new['view_name']+':PNG'] = sha(new['image_path'])==sha(prior['image_path'])
        with zipfile.ZipFile(prior['arrays_path']) as left,zipfile.ZipFile(new['arrays_path']) as right:
            for name in ('color','depth','owners','patch_owners'):
                checks[new['view_name']+':'+name] = npy_payload(left.read(name+'.npy'))==npy_payload(right.read(name+'.npy'))
    # Full/debug new metadata and changed refs are intentionally outside the
    # retained brief-v4 geometric/coverage/pixel facts compared here.
    return dict(passed=all(checks.values()),checks=checks,
                historical_service_sha256=old_spec['sha256'],current_service_sha256=sha(Path(sample['worker_result_path']).parents[1]/'o/product_call_01/SERVICE_RESULT.json'),
                comparison='All old geometric/coverage/pixel facts and original four image arrays. New raw/owner capabilities and versioned refs are separate.')


def installed(bindings,sources,root,cleanup):
    root.mkdir(parents=True,exist_ok=False)
    planned=['product_then_reuse','native_batch_fresh','legacy_capability','publication_failure']
    rows=[]
    stopped=False
    for mode in planned:
        if stopped:
            rows.append(dict(name=mode,passed=False,status='not_run'))
            continue
        row=run_one(bindings,root,mode,mode,'new',cleanup)
        rows.append(row)
        stopped=not row['passed']
    fact_check=None
    if rows[0].get('worker'):
        try:
            fact_check=unchanged_product_facts(bindings,rows[0])
        except BaseException as error:
            fact_check=dict(passed=False,error=dict(type=type(error).__name__,message=str(error)))
    result=dict(schema='view-reuse-installed-integration-v1',passed=all(r['passed'] for r in rows) and bool(fact_check and fact_check['passed']),
        registered_case_denominator=12,registered_owner_denominator=4,owners=rows,
        expected_actual_rasters=13,actual_rasters=sum(r['worker']['owner_close']['metrics']['common']['render_attempts']
            for r in rows if r.get('worker') and r['worker'].get('owner_close')),
        old_fact_and_array_comparison=fact_check,runtime_sources=sources,new_model_CLI_Blender_calls=0,
        scope='One installed integration attempt. Product focused19/units31 results are separate and are not rerun.')
    save(root/'INTEGRATION_RESULT.json',result)
    return result


def benchmark(bindings,sources,root,cleanup,integration):
    qualified=read(integration)
    if qualified['passed'] is not True or qualified['runtime_sources']!=sources:
        raise ValueError('same_runtime_installed_integration_required')
    root.mkdir(parents=True,exist_ok=False)
    save(root/'MEASUREMENT_STARTED.json',dict(started_ns=time.perf_counter_ns(),fixed_blocks=ORDER,
        integration_path=str(integration),integration_sha256=sha(integration),outer_retries=0))
    rows=[]
    stopped=False
    for block,order in enumerate(ORDER,1):
        for variant in order:
            name=f'b{block:02}_{variant}'
            if stopped:
                rows.append(dict(name=name,block=block,variant=variant,passed=False,status='not_run'))
                continue
            row=run_one(bindings,root,name,'benchmark',variant,cleanup)
            row['block']=block
            rows.append(row)
            stopped=not row['passed']
    complete=all(row['passed'] for row in rows)
    pairs=[]
    if complete:
        for block in range(1,6):
            arms={row['variant']:row for row in rows if row['block']==block}
            clocks={arm:arms[arm]['worker']['checkpoints'] for arm in arms}
            pairs.append(dict(block=block,order=list(ORDER[block-1]),
                raw_ns={key:{arm:clocks[arm][key]['elapsed_ns'] for arm in ('old','new')}
                        for key in ('first','first_plus_one_repeat','first_plus_three_repeats')}))
    summary={}
    if complete:
        for key in ('first','first_plus_one_repeat','first_plus_three_repeats'):
            old=[p['raw_ns'][key]['old'] for p in pairs];new=[p['raw_ns'][key]['new'] for p in pairs]
            summary[key]=dict(old_raw_ns=old,new_raw_ns=new,old_median_ns=statistics.median(old),
                new_median_ns=statistics.median(new),old_sum_ns=sum(old),new_sum_ns=sum(new),
                paired_new_over_old=[b/a for a,b in zip(old,new)],new_faster_pairs=sum(b<a for a,b in zip(old,new)))
    result=dict(schema='view-reuse-five-pair-cost-v1',passed=complete,block_denominator=5,sample_denominator=10,
        samples=rows,pairs=pairs,summary=summary,runtime_sources=sources,
        actual_rasters=sum(r['worker']['owner_close']['metrics']['common']['render_attempts']
            for r in rows if r.get('worker') and r['worker'].get('owner_close')),
        expected_rasters=45,ledger_scope='Ten independent per-owner6 ledgers; actual aggregate45 is not one legacy44 pool.',
        model_sessions=0,model_token_cash_benefit='unmeasured; no model consumer executed',
        limitations=['Five fixed paired blocks on one fixed source; no p95 or significance.','Worker first starts before bridge import and Owner arrays. Interpreter/verified-bootstrap startup and complete cleanup are separately retained in parent clocks.','Memory is unique observable arrays only; service temporary/allocator/RSS peak unknown.'])
    save(root/'COST_RESULT.json',result)
    with (root/'RAW_SAMPLES.csv').open('x',encoding='utf-8',newline='') as stream:
        writer=csv.writer(stream);writer.writerow(['block','variant','status','first_ns','first_plus_one_repeat_ns','first_plus_three_repeats_ns','rasters'])
        for row in rows:
            worker=row.get('worker') or {};clock=worker.get('checkpoints',{});close=worker.get('owner_close') or {}
            writer.writerow([row['block'],row['variant'],'passed' if row['passed'] else row.get('status','failed'),
                *[clock.get(key,{}).get('elapsed_ns') for key in ('first','first_plus_one_repeat','first_plus_three_repeats')],close.get('metrics',{}).get('common',{}).get('render_attempts')])
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode',choices=['installed','benchmark'],required=True)
    parser.add_argument('--bindings',type=Path,required=True)
    parser.add_argument('--freeze',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--integration',type=Path)
    args=parser.parse_args()
    bindings,sources=verify_sources(args.bindings,args.freeze)
    cleanup=stop_helper()
    if args.mode=='installed':result=installed(bindings,sources,args.output.resolve(),cleanup)
    else:
        if args.integration is None:raise ValueError('installed_integration_receipt_required')
        result=benchmark(bindings,sources,args.output.resolve(),cleanup,args.integration.resolve())
    verify_sources(args.bindings,args.freeze)
    print(json.dumps(dict(mode=args.mode,passed=result['passed'],actual_rasters=result['actual_rasters'],output=str(args.output))))
    return 0 if result['passed'] else 1


if __name__=='__main__':
    raise SystemExit(main())
