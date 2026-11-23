"""Freeze the paired production consumer and launch its two owned slots once."""

import argparse
from copy import deepcopy
import inspect
import json
import os
from pathlib import Path
from runpy import run_path
import subprocess
import sys
from time import perf_counter_ns
from zipfile import ZipFile

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import host

V=HERE.parent
ROOT=V.parent
RUN,PLAN=host.RUN,host.PLAN
SLOTS=tuple(host.SLOTS)
BASE=run_path(str(V/'m4_yanyite_bilateral_region_native_001/experiment.py'))
read,write,append,pin,git,require=(BASE[k] for k in ('read','write','append','pin','git','require'))
safe_to_continue=BASE['safe_to_continue']
LIMITS={'Blender_starts':2,'consumers':2,'business_per_slot':12,'rasters_per_slot':12,
        'task_seconds':450,'owned_seconds':600,'replacements':0}
MODEL=['0.152.1','gpt-6.1-sol','medium','default']
PREFLIGHT=RUN/'preflight'
TRUTH=PREFLIGHT/'TRUTH.json'
CUSTODY=PREFLIGHT/'CUSTODY.json'
REPLAY=PREFLIGHT/'replay_verified'
COLD=PREFLIGHT/'cold_start'
SCORES=PREFLIGHT/'SCORE_CONTROLS.json'
INITIAL_FAILURES=PREFLIGHT/'INITIAL_REPLAY_FAILURES.json'
GATE=PREFLIGHT/'ADMISSION.json'
JOURNAL=RUN/'FORMAL_SEQUENCE.jsonl'
FROZEN=HERE/'FROZEN.json'
ACCEPTED='2b3c8c2811c018ab8eda5e7c21b2bc51a442fa10'
MODE='source_region_measurement'


def command(*args):
    return [sys.executable,'-IB','-X','utf8',str(Path(__file__).resolve()),*args]


def catalogues(a,b):
    tool='human_eye_scene_observe'
    left,right=(deepcopy(next(row for row in rows if row['name']==tool)) for rows in (a,b))
    require([r['name'] for r in a]==[r['name'] for r in b]
            and [r['name'] for r,t in zip(a,b,strict=True) if r!=t]==[tool],
            'shared_tool_catalogue_changed')
    b_schema=right['inputSchema']
    query=b_schema['properties']['query']
    require(query['properties']['mode']['enum'].pop()==MODE
            and query['allOf'].pop()['if']['properties']['mode']['const']==MODE
            and b_schema['allOf'].pop()['if']['properties']['query']['properties']['mode']['const']==MODE
            and b_schema==left['inputSchema'],'scoped_is_the_only_schema_extension')
    require('Use source_region_measurement with include_image=false' in right['description']
            and MODE not in left['description'],'scoped_mode_declaration_changed')
    a_prefix,a_suffix=left['description'].split(' In this endpoint,',1)
    b_prefix,b_suffix=right['description'].split(' In this endpoint,',1)
    require(b_prefix.startswith(a_prefix+' Use source_region_measurement') and b_suffix==a_suffix,
            'shared_legacy_tool_description_changed')


def qualification():
    truth,custody,scores=(read(path) for path in (TRUTH,CUSTODY,SCORES))
    require(truth['passed'] is True and custody['passed'] is True and scores['passed'] is True,
            'actual_truth_custody_and_scorer_preflight_required')
    initial=read(INITIAL_FAILURES)
    require(len(initial['failures'])==3 and all(row['offline_only'] and not row['actual_blender']
            and not row['actual_models'] for row in initial['failures']), 'earlier_offline_failures_not_preserved')
    cases=scores['cases']
    require(len(cases)==10 and {row['slot'] for row in cases if row['case']=='healthy'}==set(SLOTS)
            and all(row['quality_complete'] is (row['case'] in ('healthy','absent_actual_exposure')) for row in cases),
            'same_formal_scorer_positive_and_rejection_controls_required')
    arms={}
    paths={TRUTH,CUSTODY,SCORES,INITIAL_FAILURES}
    for label in SLOTS:
        report=PREFLIGHT/'entry_v2'/label/'ARM.json'
        replay=(REPLAY if label=="A1" else PREFLIGHT/"replay_ready_verified")/label
        slot=replay/'slots'/label
        result=read(slot/'SLOT_RESULT.json')
        publication=read(slot/'SLOT_PUBLICATION.json')
        closed=read(replay/'REPLAY_CLOSE.json')
        ready=read(replay/'REPLAY_READY.json')
        ingress=read(report)
        arm=ingress['arms'][label]
        product=list(map(json.loads,(slot/'PUBLIC_REQUESTS.jsonl').read_bytes().splitlines()))
        flags=read(slot/'mcp_io/RUNTIME.json')['production_argv'][2:]
        require(ingress['passed'] is True and ingress['Blender']==ingress['models']==ingress['rasters']==0
                and arm['reached_before_Blender_reserve'] and arm['actual_product_handshake'] and arm['closed']
                and result['status']==publication['status']=='completed' and result['offline_fixture']
                and result['same_formal_owned_runtime'] and result['closure_verification']['passed']
                and result['actual_Blender_starts']==result['actual_models']==result['actual_rasters']==0
                and publication['result_sha256']==host.sha(slot/'SLOT_RESULT.json')
                and arm['tools']==result['actual_product_tools']
                and read(slot/'INSTALLED_TOOLS.json')==read(host.catalogue_path(label))
                and closed['actual_stdin_EOF'] and closed['listener_closed'] and closed['connections_completed']==2
                and closed['passed'] and result['fixture_peer_close']==pin(replay/'REPLAY_CLOSE.json')
                and flags==(['--region-task-evidence']+(['--source-region-measurement'] if label=='B1' else []))
                and len(product)==3 and [bool(row.get('producer_archive')) for row in product]==[True,False,True]
                and product[1]['response']['result']['isError'] is True
                and closed['ready']==pin(replay/'REPLAY_READY.json') and ready['product_git']==host.PRODUCT['commit'],
                'same_actual_owner_production_replay_and_frozen_catalogue_required/'+label)
        paths.update(p.resolve() for p in replay.rglob('*') if p.is_file())
        paths.add(report)
        arms[label]={'tools':arm['tools'],'ingress':pin(report),'result':pin(slot/'SLOT_RESULT.json'),
                     'publication':pin(slot/'SLOT_PUBLICATION.json'),'peer_close':pin(replay/'REPLAY_CLOSE.json')}
        for row in [*ingress['source_pins'],*ready['source_pins'],*closed['wire_pins']]:
            path=Path(row['path'])
            actual=pin(path)
            require(actual['sha256']==row['sha256'] and actual['bytes']==row['bytes'],'offline_source_or_wire_changed/'+str(path))
            paths.add(path)
    for proof in (truth,custody,scores,*initial['failures']):
        for row in proof.get('source_pins',()):
            path=Path(row['path'])
            actual=pin(path)
            require(actual['sha256']==row['sha256'] and actual['bytes']==row['bytes'],'offline_support_input_changed/'+str(path))
            paths.add(path)
    require(arms['A1']['tools']!=arms['B1']['tools'],'new_mode_not_exposed')
    catalogues(arms['A1']['tools'],arms['B1']['tools'])
    return {'passed':True,'kind':'actual_closed_offline_production_replay',
            'arms':arms,'scores':pin(SCORES),'truth':pin(TRUTH),'custody':pin(CUSTODY)},paths


def freeze():
    require(not FROZEN.exists() and not JOURNAL.exists() and not (RUN/'slots').exists(),
            'freeze_before_any_formal_slot_once')
    require((HERE/'PLAN.md').read_bytes()==git('show',PLAN) and pin(host.CLI)['sha256']==host.CLI_SHA
            and pin(sys.executable)['sha256']==host.PYTHON_SHA,'frozen_plan_CLI_or_execution_identity_changed')
    asset,digest=host.asset_identity()
    proof,paths=qualification()
    binding=host.fixed_binding()
    path=host.PRODUCT_BINDING
    require(path.read_bytes()==git('show',ACCEPTED+':'+path.relative_to(ROOT).as_posix()),
            'accepted_ba79_install_binding_changed')
    wheel=Path(binding['wheel_path'])
    names=[row['path'] for row in binding['source_manifest']]
    git_blob_module=V/'m4_cross_scale_local_first_view_001/install/build_install.py'
    blobs=run_path(str(git_blob_module))['git_blobs'](binding['preparation_git'],names)
    with ZipFile(wheel) as pack:
        for row in binding['source_manifest']:
            path=Path(binding['install_root'])/row['path']
            require(pin(path)['sha256']==row['sha256'] and path.read_bytes()==pack.read(row['path'])==blobs[row['path']],
                    'fixed_existing_ba79_Git_wheel_runtime_bytes_changed/'+row['path'])
            paths.add(path)
    paths.update((asset,wheel,git_blob_module,*host.retained_sources()))
    paths.update(p for p in HERE.rglob('*') if p.is_file() and p.suffix in ('.py','.md','.txt','.json'))
    write(GATE,proof)
    paths.add(GATE)
    inputs={str(p.resolve()):pin(p) for p in paths}
    write(FROZEN,{'plan':PLAN,'product':host.PRODUCT,'asset_sha256':digest,
          'terminal_sha256':host.TERMINAL_SHA256,'slots':list(SLOTS),'prompt':pin(host.PROMPT),'limits':LIMITS,
          'request_configuration':MODEL,'passed_offline_preflight':True,'gate':pin(GATE),
          'entry':pin(Path(__file__)),'commands':{label:command('slot',label) for label in SLOTS},
          'inputs':[inputs[p] for p in sorted(inputs)]})
    print('Frozen',verify_freeze(FROZEN),len(inputs),'inputs',flush=True)


def verify_freeze(path):
    require(Path(path).resolve(strict=True)==FROZEN,'only_current_freeze')
    receipt=read(FROZEN)
    require(receipt['plan']==PLAN and receipt['product']==host.PRODUCT and receipt['slots']==list(SLOTS)
            and receipt['asset_sha256']==host.ASSET_SHA256 and receipt['terminal_sha256']==host.TERMINAL_SHA256
            and receipt['prompt']==pin(host.PROMPT) and receipt['limits']==LIMITS
            and receipt['request_configuration']==MODEL and receipt['passed_offline_preflight'] is True
            and receipt['gate']==pin(GATE) and read(GATE)['passed'] is True
            and receipt['entry']==pin(Path(__file__))
            and receipt['commands']=={label:command('slot',label) for label in SLOTS}
            and all(pin(row['path'])==row for row in receipt['inputs']),
            'fixed_formal_inputs_or_admission_changed')
    return pin(FROZEN)['sha256']


def publication(label,digest,root=RUN):
    folder=root/'slots'/label
    result=read(folder/'SLOT_RESULT.json')
    receipt=read(folder/'SLOT_PUBLICATION.json')
    require(result['label']==receipt['label']==label and result['freeze_sha256']==digest
            and receipt['result_sha256']==host.sha(folder/'SLOT_RESULT.json')
            and result['status']==receipt['status'],'same_owned_slot_publication_required/'+label)
    return result,receipt


def admission(label,path,root):
    require(label in SLOTS,'unregistered_live_slot')
    digest=verify_freeze(path)
    prior=SLOTS[:SLOTS.index(label)]
    folders={p.name for p in (root/'slots').iterdir()} if (root/'slots').exists() else set()
    rows=list(map(json.loads,(root/JOURNAL.name).read_bytes().splitlines()))
    starts=[row for row in rows if row['event']=='start']
    require(folders==set(prior) and [row['label'] for row in starts]==[*prior,label]
            and all(row['freeze_sha256']==digest for row in starts)
            and all(safe_to_continue(*publication(l,digest,root)) for l in prior),
            'wrong_formal_order_or_previous_slot_not_closed')
    return {'freeze_sha256':digest,'qualification_gate_sha256':pin(GATE)['sha256']}


def cold_child(label):
    root=COLD/label
    root.mkdir(parents=True,exist_ok=False)
    digest=verify_freeze(FROZEN)
    preceding=SLOTS[:SLOTS.index(label)]
    for earlier in preceding:
        directory=root/'slots'/earlier
        directory.mkdir(parents=True)
        path=directory/'SLOT_RESULT.json'
        write(path,{'label':earlier,'freeze_sha256':digest,'status':'completed',
             'paid_API_calls':0,'actual_model_admitted':False,'consumer':None,
             'closure_verification':{'passed':True,'status':'ready_closed'},
             'independent_before_after':{'passed':True},'owner_close':{'confirmed':True},
             'budget':{'counts':{'Blender_spawned_unknown':0,'pending_raster_reservations':0}},
             'kind':'offline_simulated_order_prerequisite_only'})
        write(directory/'SLOT_PUBLICATION.json',{'label':earlier,'status':'completed',
              'owned_budget_passed':True,'result_sha256':host.sha(path),
              'kind':'offline_simulated_order_prerequisite_only'})
    for key in (*preceding,label):
        append(root/JOURNAL.name,{'event':'start','label':key,'freeze_sha256':digest,
                                 'offline_cold_start':True})
    common,module,_,_,_=host.runtime_graph(root,label)
    original_start,original_init=module.Runtime.start,module.Runtime.__init__
    observed={}
    def init(runtime,*args):
        original_init(runtime,*args)
        runtime.budget=host.Gate(runtime.budget,label)
        require(runtime.budget.root.resolve()==root/'budget','cold_owned_budget_root_changed')
        observed['runtime_class']=inspect.getsourcefile(type(runtime))
    def start(runtime):
        try:
            original_start(runtime)
        except host.PreflightBoundary:
            require(runtime.budget.reached and not runtime.native_start_entered and runtime.native is None
                    and runtime.claim is None,'cold_entry_crossed_real_Blender_budget')
            observed.update(reached_before_Blender_reserve=True,counts=runtime.budget.snapshot()['counts'],
                            start_implementation=inspect.getsourcefile(original_start))
            raise
        raise RuntimeError('actual_formal_runner_did_not_use_original_budget')
    module.Runtime.__init__,module.Runtime.start=init,start
    runner=host.prepared_runner(common,lambda name,path:admission(name,path,root))
    require(runner.__globals__['EXTERNAL']==root,'cold_formal_entry_used_wrong_root')
    try:
        code=runner(label)
    finally:
        module.Runtime.__init__,module.Runtime.start=original_init,original_start
    path=root/'slots'/label/'SLOT_RESULT.json'
    row=read(path)
    require(code==1 and row['freeze_sha256']==digest and observed.get('reached_before_Blender_reserve')
            and row['qualification_gate_sha256']==host.sha(GATE) and not row['actual_model_admitted']
            and not (path.parent/'native').exists()
            and not any(observed['counts'][k] for k in ('Blender_start_attempts','consumer_admissions','all_raster_upper'))
            and any(r['type']=='PreflightBoundary' and r['stage']=='runtime_start' for r in row['errors']),
            'real_formal_cold_boundary_missing')
    files={Path(file).resolve() for module in tuple(sys.modules.values())
           if isinstance(file:=getattr(module,'__file__',None),str) and Path(file).is_file()}
    write(root/'COLD_START.json',{'passed':True,'label':label,'pid':os.getpid(),'freeze_sha256':digest,
          'no_Blender_or_model':True,'same_formal_run_callable':True,'slot_receipt':pin(path),
          'offline_simulated_preceding_slots':list(preceding),'observed':observed,
          'imported_sources':[pin(p) for p in sorted(files)]})


def check_cold(digest):
    rows=[read(COLD/label/'COLD_START.json') for label in SLOTS]
    require(len({row['pid'] for row in rows})==len(SLOTS),'cold_entries_did_not_use_distinct_fresh_processes')
    for index,(label,row) in enumerate(zip(SLOTS,rows,strict=True)):
        require(row['passed'] and row['label']==label and row['freeze_sha256']==digest
                and row['no_Blender_or_model'] and row['same_formal_run_callable']
                and row['observed']['reached_before_Blender_reserve']
                and row['offline_simulated_preceding_slots']==list(SLOTS[:index])
                and pin(row['slot_receipt']['path'])==row['slot_receipt']
                and all(pin(v['path'])==v for v in row['imported_sources']),'cold_formal_guard_failed/'+label)


def cold():
    digest=verify_freeze(FROZEN)
    require(not COLD.exists() and not JOURNAL.exists() and not (RUN/'slots').exists(),
            'actual_cold_gate_before_live_slots_only')
    for label in SLOTS:
        subprocess.run(command('cold-child',label),cwd=ROOT,check=True,timeout=95)
    check_cold(digest)
    print('Qualified both fresh formal entrance paths before Blender reservation',flush=True)


def live_slot(label,path):
    check_cold(verify_freeze(path))
    return admission(label,path,RUN)


def formal():
    digest=verify_freeze(FROZEN)
    check_cold(digest)
    require(not (RUN/'slots').exists() and not JOURNAL.exists(),'zero_replacement_actual_consumer_pair')
    JOURNAL.touch(exist_ok=False)
    for index,label in enumerate(SLOTS):
        started=perf_counter_ns()
        append(JOURNAL,{'event':'start','label':label,'perf_ns':started,'freeze_sha256':digest})
        child=subprocess.run(command('slot',label),cwd=ROOT,timeout=620)
        finished=perf_counter_ns()
        pub=RUN/'slots'/label/'SLOT_PUBLICATION.json'
        row={'event':'exit','label':label,'perf_ns':finished,'controller_wall_ns':finished-started,
             'exit_code':child.returncode,'status':'missing','safe_to_continue':False}
        if pub.is_file():
            result,receipt=publication(label,digest)
            row.update(status=result['status'],publication=pin(pub),safe_to_continue=safe_to_continue(result,receipt))
        append(JOURNAL,row)
        if not row['safe_to_continue']:
            append(JOURNAL,{'event':'blocked','label':label,'unrun':list(SLOTS[index+1:]),
                            'reason':'previous_owned_runtime_or_consumer_cleanup_not_confirmed'})
            return 1
    return 0


if __name__=='__main__':
    require(sys.flags.isolated and sys.dont_write_bytecode,'fixed_isolated_interpreter_required')
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage',choices=('ingress','freeze','cold','cold-child','formal','slot'))
    parser.add_argument('label',choices=SLOTS,nargs='?')
    args=parser.parse_args()
    require((args.stage in ('ingress','cold-child','slot'))==bool(args.label),'registered_label_required')
    if args.stage=='ingress':
        host._preflight_arm(PREFLIGHT/'entry_v2'/args.label/'ARM.json',args.label)
    elif args.stage=='cold-child':
        cold_child(args.label)
    elif args.stage=='slot':
        raise SystemExit(host.run_slot(args.label,live_slot))
    else:
        raise SystemExit(globals()[args.stage]())
