"""Freeze and execute one real cold A/B slot for each of the two fixed assets."""

import argparse
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
from build import BASE, CANDIDATE, PYTHON_SHA


OLD = run_path(str(host.PREVIOUS/'experiment.py'))
read,write,pin,git,append,require = (OLD[key] for key in ('read','write','pin','git','append','require'))
RUN = host.RUN
PRE = RUN/'preflight'
PLAN = '7ea178e57eefc4a87a45b433bcfa12861813e56c:docs/M2_SOURCE_REGION_COLD_SELECTIVE_TRANSPORT_001_PLAN.md'
FROZEN = HERE/'FROZEN.json'
JOURNAL = RUN/'FORMAL_SEQUENCE.jsonl'
TRUTH = PRE/'controls_truth.json'
CONTROLS = PRE/'controls.json'
TCP_CONTROLS = PRE/'controls_tcp.json'
CLOSED_REPLAY = PRE/'CLOSED_WIRE_REPLAY.json'
LABELS = tuple(host.LABELS)


def argv(*args):
    return [sys.executable,'-IB','-X','utf8',str(Path(__file__).resolve()),*args]


def call_private(slot,query,identity,*,include_image=False,admit=True):
    if admit:
        slot.runtime.budget.admit_business(slot.label,'formal')
    return slot.client.call({'jsonrpc':'2.0','id':identity,'method':'tools/call','params':{
        'name':host.PRIVATE_TOOL,'arguments':{'include_image':include_image,'query':query}}})


def startup(label):
    """Drive the actual held entry to Blender reservation and check both dispositions."""
    require(not (RUN/'slots').exists(),'zero_live_slots_during_entry_preflight')
    root = PRE/'entry'/label
    root.mkdir(parents=True,exist_ok=False)
    asset,arm = host.LABELS[label]
    trial = host.Slot(root,label,host.BINDINGS[arm],preflight=True)
    with trial:
        query = read(TRUTH)['fixtures'][asset]['requests'][0]
        invalid = call_private(trial,query,'private-ineligible',include_image=True,admit=False)
        require(invalid['result']['isError'] is True,'private_ineligible_input_not_rejected')
        error = json.loads(invalid['result']['content'][0]['text'])['error']
        expected = 'selective_source_region_requires_no_image' if arm == 'B' else 'Unknown tool'
        require(expected.casefold() in error.casefold(),'actual_private_entry_error_mismatch/'+error)
        catalog = trial.client.call({'jsonrpc':'2.0','id':'recover-list','method':'tools/list'})['result']['tools']
        require(catalog == trial.product_tools and all(item['name'] != host.PRIVATE_TOOL for item in catalog),
                'private_tool_escaped_default_catalogue')
    closed = trial.finish()
    worker = read(trial.folder/'mcp_io/REAL_HOST_STAGES.json')
    boundary = read(trial.folder/'PREFLIGHT_BOUNDARY.json')
    require(closed['status'] == 'completed' and not any(closed['budget']['counts'].values())
            and not worker['requests'] and boundary['actual_runtime_start_until_Budget_reserve'],
            'actual_entry_did_not_stop_and_close_before_Blender')
    write(root/'RESULT.json',{'passed':True,'arm':arm,'asset':asset,'label':label,'catalogue':catalog,
         'private_error':error,'source_sha256':trial.binding['source_sha256'],
         'boundary':pin(trial.folder/'PREFLIGHT_BOUNDARY.json'),'close':pin(trial.folder/'HOST_RECEIPT.json')})


def freeze():
    require(not FROZEN.exists() and not (RUN/'slots').exists() and not JOURNAL.exists(),
            'one_frozen_preflight_required')
    require(pin(sys.executable)['sha256'] == PYTHON_SHA and (HERE/'PLAN.md').read_bytes() == git('show',PLAN),
            'fixed_interpreter_and_plan_required')
    paths = {Path(sys.executable),host.BLENDER,*host.retained_sources(),
             *(p for p in HERE.rglob('*') if p.is_file() and p.suffix in ('.py','.md','.json'))}
    for receipt_path in (TRUTH,CONTROLS,TCP_CONTROLS,CLOSED_REPLAY):
        receipt = read(receipt_path)
        require(receipt['passed'] is True,'preflight_receipt_failed/'+receipt_path.name)
        for p in receipt.get('source_pins',()):
            require(pin(p['path']) == p,'historical_control_input_changed/'+p['path'])
            paths.add(Path(p['path']))
    builds, catalogues = {}, []
    for label in LABELS:
        asset,arm = host.LABELS[label]
        result = read(PRE/'entry'/label/'RESULT.json')
        binding = host.binding_identity(label,host.BINDINGS[arm])
        require(result['passed'] and (result['asset'],result['arm']) == host.LABELS[label]
                and result['source_sha256'] == binding['source_sha256']
                and pin(result['close']['path']) == result['close'] and pin(result['boundary']['path']) == result['boundary'],
                'actual_cold_startup_admission_changed/'+label)
        catalogues.append(result['catalogue'])
        sidecar = Path(binding['wheel_path'])
        if arm not in builds:
            commit = {'A':BASE,'B':CANDIDATE}[arm]
            require(binding['preparation_git'] == commit,'fixed_installed_product_git_changed')
            with ZipFile(sidecar) as wheel:
                for p in binding['source_manifest']:
                    source = Path(binding['install_root'])/p['path']
                    require(pin(source)['sha256'] == p['sha256'] and source.read_bytes() == wheel.read(p['path'])
                            == git('show',commit+':'+p['path']),'actual_installed_source_changed/'+p['path'])
                    paths.add(source)
            paths.add(sidecar)
            builds[arm] = {key:binding[key] for key in ('preparation_git','source_sha256','wheel_sha256')}
        path,digest = host.ASSETS[asset]
        require(pin(path)['sha256'] == digest,'original_asset_changed')
    require(all(row == catalogues[0] for row in catalogues),'standard_product_tool_catalogues_changed')
    paths.update(p for p in PRE.rglob('*') if p.is_file())
    inputs = {row['path']:row for row in map(pin,paths)}
    write(FROZEN,{'plan':PLAN,'labels':list(LABELS),'builds':builds,'limits':host.LIMITS,
        'requests':{name:read(TRUTH)['fixtures'][name]['requests'] for name in host.ASSETS},
        'commands':{label:argv('slot',label) for label in LABELS},
        'preflight':{name:pin(path) for name,path in {'truth':TRUTH,'controls':CONTROLS,
                     'loopback':TCP_CONTROLS,'closed_replay':CLOSED_REPLAY}.items()},
        'inputs':[inputs[key] for key in sorted(inputs)]})
    print('Frozen',verify_freeze(),len(inputs),'inputs',flush=True)


def verify_freeze():
    result = read(FROZEN)
    require(result['plan'] == PLAN and result['labels'] == list(LABELS) and result['limits'] == host.LIMITS
            and result['commands'] == {label:argv('slot',label) for label in LABELS}
            and all(pin(row['path']) == row for row in result['inputs']),'frozen_selective_transport_inputs_changed')
    return pin(FROZEN)['sha256']


def live_slot(label):
    digest = verify_freeze()
    starts = [row for line in JOURNAL.read_bytes().splitlines() if (row:=json.loads(line))['event']=='start']
    require([row['label'] for row in starts] == list(LABELS[:LABELS.index(label)+1])
            and all(row['freeze_sha256'] == digest for row in starts),'owned_live_slot_not_admitted')
    asset,arm = host.LABELS[label]
    first,second = read(FROZEN)['requests'][asset]
    started = time.perf_counter_ns()
    slot = host.Slot(RUN,label,host.BINDINGS[arm],start_ns=started)
    result = {'label':label,'asset':asset,'arm':arm,'status':'failed','freeze_sha256':digest,'observations':[]}
    completed = False
    try:
        with slot:
            result['initial'] = pin(slot.source())
            for number,query in enumerate((first,first,second),1):
                begin = time.perf_counter_ns()
                if arm == 'A':
                    response,proof = slot.observe({'query':query,'include_image':False,'response_detail':'full'})
                    result['observations'].append({'response_id':response['id'],'public_request':proof,
                                                    'wall_ns':time.perf_counter_ns()-begin})
                else:
                    response = call_private(slot,query,f'private-observe-{number}')
                    result['observations'].append({'response_id':response['id'],'wall_ns':time.perf_counter_ns()-begin})
                content = response['result']
                require(content['isError'] is False and all(row['type']=='text' for row in content['content']),
                        'actual_no_image_measurement_failed/'+str(content))
        closed = slot.finish()
        require(closed['status'] == 'completed' and closed['independent_before_after']['passed'] is True,
                'actual_owned_readonly_close_failed')
        result['status'] = 'completed'
        completed = True
    except Exception as exc:
        result['error'] = {'type':type(exc).__name__,'message':str(exc)}
    finally:
        result.update(closure=slot.receipt,window_ns=time.perf_counter_ns()-started)
        result_path = slot.folder/'SLOT_RESULT.json'
        write(result_path,result)
        write(slot.folder/'SLOT_PUBLICATION.json',{'label':label,'status':result['status'],
              'freeze_sha256':digest,'result':pin(result_path)})
        print(label,result['status'],round(result['window_ns']/1e6,2),'ms',result.get('error',''),flush=True)
    return int(not completed)


def formal():
    digest = verify_freeze()
    require(not (RUN/'slots').exists(),'no_replacement_owned_slots')
    JOURNAL.open('x').close()
    for index,label in enumerate(LABELS):
        append(JOURNAL,{'event':'start','label':label,'freeze_sha256':digest,'perf_ns':time.perf_counter_ns()})
        child = subprocess.run(argv('slot',label),cwd=ROOT,timeout=610)
        path = RUN/'slots'/label/'SLOT_PUBLICATION.json'
        closure = read(RUN/'slots'/label/'HOST_RECEIPT.json') if path.is_file() else {}
        safe = closure.get('status') == 'completed' or bool((closure.get('closure_verification') or {}).get('passed'))
        append(JOURNAL,{'event':'exit','label':label,'exit_code':child.returncode,'safe_closed':safe,
                       'publication':pin(path) if path.is_file() else None,'perf_ns':time.perf_counter_ns()})
        if not safe:
            append(JOURNAL,{'event':'blocked','label':label,'unrun':list(LABELS[index+1:]),
                            'reason':'owned_readonly_shutdown_not_confirmed'})
            return 1
    return 0


def archive():
    seal = OLD['archive']
    seal.__globals__['RUN'] = RUN
    seal()


if __name__ == '__main__':
    require(sys.flags.isolated and sys.dont_write_bytecode,'fixed_isolated_interpreter_required')
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('phase',choices=('startup','freeze','formal','slot','archive'))
    p.add_argument('label',choices=LABELS,nargs='?')
    a = p.parse_args()
    require((a.phase in ('startup','slot')) == bool(a.label),'one_registered_label_when_required')
    if a.phase == 'startup':
        startup(a.label)
    elif a.phase == 'slot':
        raise SystemExit(live_slot(a.label))
    else:
        raise SystemExit(globals()[a.phase]())
