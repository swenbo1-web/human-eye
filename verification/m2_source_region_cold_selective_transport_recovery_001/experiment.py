"""Recover the four-slot cold comparison with a shared live/replay caller."""

import argparse
from copy import deepcopy
import json
from pathlib import Path
from runpy import run_path
import subprocess
import sys
import time
from zipfile import ZipFile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0,str(HERE))
import host
from common import arguments,order

RUN = host.RUN
PRE = RUN/'preflight'
LABELS = tuple(host.LABELS)
PLAN = 'efb5d7358fd48349f195cc208cceff7a46cb472a:docs/M2_SOURCE_REGION_COLD_SELECTIVE_TRANSPORT_RECOVERY_001_PLAN.md'
OLD = run_path(str(host.PREVIOUS/'experiment.py'))
read,write,append,pin,git,require = (OLD[key] for key in ('read','write','append','pin','git','require'))
PREDECESSOR = host.OLD/'FROZEN.json'
TRUTH = Path('D:/he_m2_source_region_cold_selective_transport_001/preflight/controls_truth.json')
LEGACY = PRE/'LEGACY.json'
PACKETS = PRE/'PACKET_CONTROLS.json'
FROZEN = HERE/'FROZEN.json'
GATE = PRE/'ADMISSION.json'
JOURNAL = RUN/'FORMAL_SEQUENCE.jsonl'
PYTHON_SHA = '50f885251e42eb8cd1fbf5d4fbcc01efdbe8b9f4d4379e16664d4d0f3d4a9869'
OLD_COMMIT = 'f75b945498793ebeacfb242ada4635c6e12b0804'
VERIFY = HERE/'verify.py'


def command(entry,*args):
    return [sys.executable,'-IB','-X','utf8',str(HERE/entry),*map(str,args)]


def request_records(label):
    asset,_ = host.LABELS[label]
    result = read(PREDECESSOR)['requests'][asset]
    require(result == read(TRUTH)['fixtures'][asset]['requests'],'old_independent_request_truth_changed')
    order(result)
    return result


def dispatch(slot,record,index):
    arm = host.LABELS[slot.label][1]
    params = arguments(record,arm)
    slot.runtime.budget.admit_business(slot.label,'formal')
    ident = f'recovery-measure-{index}'
    started = time.perf_counter_ns()
    response = slot.client.call({'jsonrpc':'2.0','id':ident,'method':'tools/call','params':{
        'name':'human_eye_scene_observe' if arm=='A' else host.PRIVATE_TOOL,'arguments':params}})
    elapsed = time.perf_counter_ns()-started
    return response,{'response_id':response['id'],'wall_ns':elapsed}


def expect_reject(invoke, diagnostic):
    try:
        invoke()
    except (ValueError,RuntimeError) as error:
        require(str(error)==diagnostic,'unexpected_gate_error/'+str(error))
        return diagnostic
    raise ValueError('malformed_or_over_budget_request_was_admitted')


def run_calls(slot,records,result,*,offline):
    result['observations'] = []
    for index,record in enumerate(order(records),1):
        reply,row = dispatch(slot,record,index)
        result['observations'].append(row)
        require(reply['id']==f'recovery-measure-{index}' and reply['result']['isError'] is False
                and all(block['type']=='text' for block in reply['result']['content']),
                'actual_no_image_measurement_failed/'+str(reply))
    if offline:
        base = records[0]
        result['preflight_rejections'] = {
            'nested':expect_reject(lambda:dispatch(slot,{'query':base,'include_image':False},4),
                                   'one_source_region_world_box_query_required'),
            'wrong_scope':expect_reject(lambda:dispatch(slot,{'query':{**base['query'],'mode':'task'},
                                               'include_image':False},4),'one_source_region_world_box_query_required'),
            'incomplete':expect_reject(lambda:dispatch(slot,{'query':base['query']},4),
                                       'one_frozen_no_image_request_record_required'),
            'budget':expect_reject(lambda:dispatch(slot,base,4),'business_tool_budget_exhausted')}


def startup(label):
    root = host.ENTRY/label
    root.mkdir(parents=True,exist_ok=False)
    require(not (RUN/'slots').exists(),'reservation_preflight_before_live_only')
    _,arm = host.LABELS[label]
    trial = host.Slot(root,label,host.BINDINGS[arm],preflight=True)
    with trial:
        invalid = trial.client.call({'jsonrpc':'2.0','id':'invalid-image','method':'tools/call','params':{
            'name':'human_eye_scene_observe','arguments':{'include_image':'invalid'}}})
        require(invalid['result']['isError'] is True,'standard_invalid_input_not_rejected')
        catalogue = trial.client.call({'jsonrpc':'2.0','id':'confirm-standard','method':'tools/list'})['result']['tools']
        require(catalogue==read(host.CATALOGUE) and all(row['name']!=host.PRIVATE_TOOL for row in catalogue),
                'public_entry_catalogue_changed')
    close=trial.finish()
    probe=read(trial.folder/'mcp_io/REAL_HOST_STAGES.json')
    boundary=read(trial.folder/'PREFLIGHT_BOUNDARY.json')
    require(close['status']=='completed' and not any(close['budget']['counts'].values()) and not probe['requests']
            and boundary['actual_runtime_start_until_Budget_reserve'],'startup_crossed_reservation_or_bad_close')
    write(root/'RESULT.json',{'passed':True,'label':label,'source_sha256':trial.binding['source_sha256'],
          'actual_Blender':0,'boundary':pin(trial.folder/'PREFLIGHT_BOUNDARY.json'),
          'close':pin(trial.folder/'HOST_RECEIPT.json'),'catalogue':pin(host.CATALOGUE)})


def start_replay(root,label):
    args = command('replay_host.py','--label',label,'--slot-dir',root/'slots'/label)
    with (root/'REPLAY_STDOUT.bin').open('xb') as out,(root/'REPLAY_STDERR.bin').open('xb') as err:
        proc = subprocess.Popen(args,cwd=ROOT,stdin=subprocess.PIPE,stdout=out,stderr=err)
    return proc,args


def await_replay(root,proc,label):
    deadline=time.perf_counter()+45
    while not (root/'REPLAY_READY.json').is_file():
        require(proc.poll() is None and time.perf_counter() < deadline,'replay_server_never_ready')
        time.sleep(.025)
    ready=read(root/'REPLAY_READY.json')
    require(ready['pid']==proc.pid and ready['label']==label,'replay_child_ready_pid_mismatch')


def stop_replay(proc):
    try:
        proc.stdin.close()
        return proc.wait(timeout=30)
    except (subprocess.TimeoutExpired,OSError):
        proc.kill()
        proc.wait(timeout=15)
        raise


def live_admission(label):
    digest=verify_freeze()
    starts=[row for raw in JOURNAL.read_bytes().splitlines() if (row:=json.loads(raw))['event']=='start']
    require([r['label'] for r in starts]==list(LABELS[:LABELS.index(label)+1])
            and all(r['freeze_sha256']==digest for r in starts),'live_slot_not_registered_in_frozen_order')
    return digest


def run_slot(label,*,offline):
    asset,arm=host.LABELS[label]
    root=host.REPLAY/label if offline else RUN
    records=request_records(label)
    digest=None if offline else live_admission(label)
    require(offline or records==read(FROZEN)['requests'][asset],'actual_frozen_query_changed')
    if offline:
        root.mkdir(parents=True,exist_ok=False)
    started=time.perf_counter_ns()
    slot=host.Slot(root,label,host.BINDINGS[arm],preflight=offline,start_ns=started)
    result={'label':label,'asset':asset,'arm':arm,'offline_fixture':offline,'status':'failed',
            'freeze_sha256':digest,'observations':[]}
    proc=None
    try:
        if offline:
            proc,args=start_replay(root,label)
            result['replay_command']=args
            await_replay(root,proc,label)
        with slot:
            if not offline:
                result['initial']=pin(slot.source())
            run_calls(slot,records,result,offline=offline)
        closed=slot.finish()
        require(closed['status']=='completed' and (offline or closed['independent_before_after']['passed']),
                'actual_slot_readonly_close_failed')
        if offline:
            close_code=stop_replay(proc)
            require(close_code==0,'actual_replay_process_close_failed')
            result['replay']={name:pin(root/filename) for name,filename in (
                ('ready','REPLAY_READY.json'),('close','REPLAY_CLOSE.json'))}
        result['status']='completed'
    except Exception as error:
        result['error']={'type':type(error).__name__,'message':str(error)}
    finally:
        if proc is not None and proc.poll() is None:
            try:
                stop_replay(proc)
            except (OSError,subprocess.TimeoutExpired) as error:
                result['replay_cleanup_error']=str(error)
        result.update(closure=slot.receipt,window_ns=time.perf_counter_ns()-started)
        result_path=slot.folder/'SLOT_RESULT.json'
        write(result_path,result)
        write(slot.folder/'SLOT_PUBLICATION.json',{'label':label,'status':result['status'],'freeze_sha256':digest,
                    'offline_fixture':offline,'result':pin(result_path)})
        print(label,'offline' if offline else 'live',result['status'],result.get('error',''),flush=True)
    return int(result['status']!='completed')


def stable(value):
    return json.dumps(value,sort_keys=True,ensure_ascii=False,allow_nan=False,separators=(',',':'))


def evaluator():
    return run_path(str(VERIFY))


def select_metrics(slot):
    return {key:value for key,value in slot.items() if key not in ('terminal','source_pins','calls')} | {
        'calls':[{key:value for key,value in row.items() if key not in ('decoded_full','scoped_packet')}
                 for row in slot['calls']]}


def actual_admission():
    check=evaluator()
    truth=read(TRUTH)['fixtures']
    cases,pins,verified={}, {}, {}

    def bind(path):
        row=pin(path)
        require(pins.setdefault(row['path'],row)==row,'conflicting_closed_gate_source_identity')
        return row

    bind(LEGACY)
    bind(PACKETS)
    bind(TRUTH)
    bind(PREDECESSOR)
    historic=read(LEGACY)
    require(historic['passed'] is True and historic['previous_formal_passed'] is False,'original_failed_batch_not_preserved')
    for row in historic['source_pins']:
        require(bind(row['path'])==row,'bound_old_runtime_evidence_changed')
    require(read(PACKETS)['passed'] is True,'real_scoped_packet_negatives_required')
    for row in read(PACKETS).get('source_pins',()):
        require(bind(row['path'])==row,'private_packet_negative_control_source_changed')
    for label in LABELS:
        replay=host.REPLAY/label
        slot=replay/'slots'/label
        startup_root=host.ENTRY/label
        ingress=read(startup_root/'RESULT.json')
        old_binding=host.binding_identity(label,host.BINDINGS[host.LABELS[label][1]])
        require(ingress['passed'] is True and ingress['label']==label
                and ingress['actual_Blender']==0 and ingress['source_sha256']==old_binding['source_sha256']
                and ingress['catalogue']==pin(host.CATALOGUE)
                and ingress['close']==pin(ingress['close']['path'])
                and ingress['boundary']==pin(ingress['boundary']['path']),'real_reservation_preflight_bad')
        records=request_records(label)
        result=read(slot/'SLOT_RESULT.json')
        attempt=command('replay_host.py','--label',label,'--slot-dir',slot)
        require(result['preflight_rejections']=={
                   'nested':'one_source_region_world_box_query_required',
                   'wrong_scope':'one_source_region_world_box_query_required',
                   'incomplete':'one_frozen_no_image_request_record_required',
                   'budget':'business_tool_budget_exhausted'}
                and result['replay_command']==attempt
                and result['offline_fixture'] is True and result['status']=='completed',
                'same_formal_dispatch_or_replay_budget_not_qualified')
        check_slot=check['verify_slot'](slot,label,records,offline=True)
        require(len(check_slot['calls'])==3 and check_slot['budget']['business_admissions']==3,
                'three_actual_succeeded_public_worker_calls_required')
        for row in check_slot.get('source_pins',()):
            require(bind(row['path'])==row,'actual_closed_preflight_source_changed')
        verified[label]=check_slot
        cases[label]={'measurement':select_metrics(check_slot),'observed_call_count':3,'passed':True,
                     'replay_command':attempt,'controller_command':command('experiment.py','replay',label),
                     'result':bind(slot/'SLOT_RESULT.json'),'publication':bind(slot/'SLOT_PUBLICATION.json'),
                     'replay_ready':bind(replay/'REPLAY_READY.json'),'replay_close':bind(replay/'REPLAY_CLOSE.json'),
                     'startup':bind(startup_root/'RESULT.json'),
                     'requests':records,'rejections':result['preflight_rejections']}
    pairs={name:check['compare'](name,verified[left],verified[right],truth[name])
           for name,left,right in (('assembly','AA','AB'),('yanyite','YA','YB'))}
    return {'passed':True,'phase':'actual_installed_stdio_and_loopback_no_new_Blender',
            'registered_slots':list(LABELS),'actual_successful_measurements':12,'cases':cases,'pairs':pairs,
            'source_pins':[pins[key] for key in sorted(pins)],'actual_Blender':0,'actual_models':0,'actual_rasters':0}


def check_gate(declared,actual):
    require(declared.get('passed') is True,'failed_preflight_cannot_freeze')
    require(declared.get('registered_slots')==list(LABELS)
            and set(declared.get('cases',{}))==set(LABELS),'missing_successful_preflight_slot')
    require(declared.get('actual_successful_measurements')==12
            and all(declared['cases'][label]['observed_call_count']==3 for label in LABELS),
            'wrong_preflight_success_or_budget_count')
    require(all(declared['cases'][label]['passed'] is True for label in LABELS),'failed_preflight_cannot_freeze')
    require(stable(declared)==stable(actual),'actual_measurement_request_or_evidence_binding_changed')


def qualify():
    require(not FROZEN.exists() and not (RUN/'slots').exists(),'preflight_cannot_follow_live_execution')
    actual=actual_admission()
    rejected={}
    for name in ('missing_success','failed','extra_budget','wrong_query','nested_query','wrong_binding'):
        changed=deepcopy(actual)
        if name=='missing_success':
            changed['cases'].pop('YB')
        elif name=='failed':
            changed['cases']['AB']['passed']=False
        elif name=='extra_budget':
            changed['cases']['AA']['observed_call_count']=4
        elif name=='wrong_query':
            changed['cases']['YA']['requests'][0]['query']['mode']='task'
        elif name=='nested_query':
            row=changed['cases']['YB']['requests'][0]
            changed['cases']['YB']['requests'][0]={'query':row,'include_image':False}
        else:
            changed['cases']['AB']['replay_close']['sha256']='0'*64
        try:
            check_gate(changed,actual)
        except ValueError as error:
            rejected[name]=str(error)
        else:
            raise ValueError('negative_preflight_admission_control_passed/'+name)
    write(GATE,{'passed':True,'actual':actual,'rejected_admission_controls':rejected})
    print('Qualified 4 actual held stdio and TCP replays, 12 successful measures',flush=True)


def freeze():
    require(not FROZEN.exists() and not (RUN/'slots').exists() and not JOURNAL.exists(),
            'once_only_frozen_recovery_required')
    require(pin(sys.executable)['sha256']==PYTHON_SHA and (HERE/'PLAN.md').read_bytes()==git('show',PLAN)
            and PREDECESSOR.read_bytes()==git('show',OLD_COMMIT+':'+PREDECESSOR.relative_to(ROOT).as_posix()),
            'fixed_recovery_plan_or_historical_freeze_changed')
    gate=read(GATE)
    require(gate['passed'] is True and len(gate['rejected_admission_controls'])==6,
            'preflight_rejection_controls_required')
    check_gate(gate['actual'],actual_admission())
    paths={Path(sys.executable),host.BLENDER,GATE,PREDECESSOR,TRUTH,*host.retained_sources(),
        *(p for p in HERE.iterdir() if p.is_file() and p.suffix in ('.py','.json','.md')),
        *(p for folder in (host.ENTRY,host.REPLAY) for p in folder.rglob('*') if p.is_file()),
        *(Path(row['path']) for row in gate['actual']['source_pins'])}
    builds=read(PREDECESSOR)['builds']
    for label,arm in (('AA','A'),('AB','B')):
        binding=host.binding_identity(label,host.BINDINGS[arm])
        commit=binding['preparation_git']
        require({key:binding[key] for key in builds[arm]}==builds[arm],'existing_install_identity_changed')
        wheel_path=Path(binding['wheel_path'])
        paths.update((wheel_path,host.BINDINGS[arm]))
        with ZipFile(wheel_path) as pack:
            for row in binding['source_manifest']:
                source=Path(binding['install_root'])/row['path']
                require(pin(source)['sha256']==row['sha256'] and source.read_bytes()==pack.read(row['path'])
                        ==git('show',commit+':'+row['path']),'existing_installed_source_changed/'+row['path'])
                paths.add(source)
    inputs={row['path']:row for row in map(pin,paths)}
    write(FROZEN,{'passed':True,'plan':PLAN,'previous_freeze':pin(PREDECESSOR),'admission':pin(GATE),
                  'builds':builds,'labels':list(LABELS),'limits':host.LIMITS,
                  'requests':{name:request_records(label) for label,(name,arm) in host.LABELS.items() if arm=='A'},
                  'formal_commands':{label:command('experiment.py','slot',label) for label in LABELS},
                  'inputs':[inputs[key] for key in sorted(inputs)]})
    print('Frozen',verify_freeze(),len(inputs),'inputs',flush=True)


def verify_freeze():
    row=read(FROZEN)
    require(row['passed'] is True and row['plan']==PLAN and row['previous_freeze']==pin(PREDECESSOR)
            and row['admission']==pin(GATE) and row['limits']==host.LIMITS and row['labels']==list(LABELS)
            and row['formal_commands']=={label:command('experiment.py','slot',label) for label in LABELS}
            and all(pin(value['path'])==value for value in row['inputs']),
            'frozen_live_recovery_inputs_changed')
    return pin(FROZEN)['sha256']


def score():
    digest=verify_freeze()
    check=evaluator()
    truth=read(TRUTH)['fixtures']
    slots,errors,pairs={},{},{}
    for label in LABELS:
        try:
            slot=RUN/'slots'/label
            require(read(slot/'SLOT_RESULT.json')['freeze_sha256']==digest,'closed_live_slot_freeze_mismatch')
            slots[label]=check['verify_slot'](slot,label,request_records(label),offline=False)
        except (OSError,KeyError,TypeError,ValueError,IndexError) as error:
            errors[label]={'type':type(error).__name__,'message':str(error)}
    for name,left,right in (('assembly','AA','AB'),('yanyite','YA','YB')):
        if left in slots and right in slots:
            try:
                pairs[name]=check['compare'](name,slots[left],slots[right],truth[name])
            except (OSError,KeyError,TypeError,ValueError,IndexError) as error:
                errors[name]={'type':type(error).__name__,'message':str(error)}
    report={'freeze_sha256':digest,'passed':len(pairs)==2 and not errors and
            all(pair['cold_transmission_reduced'] for pair in pairs.values()),
            'arms':{label:select_metrics(slot) for label,slot in slots.items()},'pairs':pairs,'errors':errors}
    write(RUN/'SCORE.json',report)
    print({key:report[key] for key in ('passed','pairs','errors')},flush=True)
    return int(not report['passed'])


def formal():
    digest=verify_freeze()
    require(not (RUN/'slots').exists() and not JOURNAL.exists(),'single_run_no_formal_replacements')
    JOURNAL.open('x').close()
    failed=False
    for n,label in enumerate(LABELS):
        cap=read(FROZEN)['formal_commands'][label]
        append(JOURNAL,{'event':'start','label':label,'freeze_sha256':digest,'argv':cap,'perf_ns':time.perf_counter_ns()})
        child=subprocess.run(cap,cwd=ROOT,timeout=610)
        publication=RUN/'slots'/label/'SLOT_PUBLICATION.json'
        close_path=publication.with_name('HOST_RECEIPT.json')
        safe=close_path.is_file() and (read(close_path).get('closure_verification') or {}).get('passed') is True
        append(JOURNAL,{'event':'exit','label':label,'exit_code':child.returncode,'safe_closed':safe,
                       'publication':pin(publication) if publication.is_file() else None,'perf_ns':time.perf_counter_ns()})
        failed |= bool(child.returncode)
        if not safe:
            append(JOURNAL,{'event':'blocked','label':label,'unrun':list(LABELS[n+1:]),
                           'reason':'owned_readonly_shutdown_not_confirmed'})
            return 1
    return int(failed)


def archive():
    seal=OLD['archive']
    seal.__globals__['RUN']=RUN
    seal()


if __name__ == '__main__':
    require(sys.flags.isolated and sys.dont_write_bytecode,'fixed_isolated_controller_required')
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('phase',choices=('startup','replay','qualify','freeze','formal','slot','score','archive'))
    cli.add_argument('label',choices=LABELS,nargs='?')
    args=cli.parse_args()
    require((args.phase in ('startup','replay','slot'))==bool(args.label),'registered_phase_label_required')
    if args.phase=='startup':
        startup(args.label)
    elif args.phase in ('replay','slot'):
        raise SystemExit(run_slot(args.label,offline=args.phase=='replay'))
    else:
        raise SystemExit(globals()[args.phase]())
