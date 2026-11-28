"""Bind four immutable natural A/B cells to the existing Blender/CLI recorder."""
import argparse
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
RETAINED = HERE.parent / 'm4_nearest_surface_natural_holdout_001'
spec = importlib.util.spec_from_file_location('retained_natural_runner', RETAINED/'natural.py')
old = importlib.util.module_from_spec(spec)
spec.loader.exec_module(old)
sys.path.insert(0, str(RETAINED))
pin, require, read, write = old.pin, old.require, old.read, old.write
confirmed, hash_file = old.confirmed, old.hash_file
BATCH = 'M1-NEAREST-SURFACE-ENTRY-DISCOVERY-001'
ADMIN = '62cd96e0673243bfb3f7cfaf183b79caacae52803c738cd706bece89d30400b9'
A_COMMIT = '4225256485a82a9ddbdeeca61e1bbd3275574a6e'
A_SOURCE = '60eabe4f875aabbd6c7b1c24c7498ed06b53d10b40a0e70a0ab920b4a64631e0'
A_WHEEL = '5b1f10708bc61cf21453ca0c72fb54cc8b7af19fc3925747bcef96499fd8e4fb'
A_CUSTODY = '60014204a745d00ea804dc06df0fff51dddecdbd16b5b6bcc22af01656ab117d'
TRANSPORT_RECEIPT = 'f1dac227875f0b20dd74ed101918cd54ceecf65db4243cbcfa4803f94e21d575'
ORDER = ('A1', 'B1', 'B2', 'A2')
TOPICS = {'1': 'K', '2': 'T'}
PLAN = 'preflight/NATURAL_PLAN.json'
COLD = 'preflight/NATURAL_COLD.json'
FREEZE = 'preflight/FROZEN_EXECUTION.json'
PRODUCT_GATE = 'preflight/ENTRY_PRODUCT_PREFLIGHT.json'
LAST_RUN = 'M4-NEAREST-SURFACE-NATURAL-HOLDOUT-001'
LIBRARIES = {'natural.py': '1155c2891b50c108c11855eb014c0b805cfb61e7dd3960c2a16c512b106ba4e5',
             'natural_evidence.py': '97ab32494a37bd36d56e571851575edfce2902af337f1eb0f67167ff5779cda3',
             'transport.py': '43b932de8d2805dcf3a6706bec139f25be0f2b72ab50c056280310b8d871534e'}


def admitted_install(root, label):
    path = (root.parent/'M4-NEAREST-SURFACE-FIRST-FOCUS-001/preflight/INSTALL_CUSTODY.json'
            if label == 'A' else root/'preflight/INSTALL_CUSTODY.json')
    value = read(path)
    present = pin(path)
    require(value['passed'] is True and value['runtime_sources'] == len(value['source_manifest']) == 146,
            'installed_arm_manifest_missing')
    if label == 'A':
        require(present['sha256'] == A_CUSTODY and value['candidate_commit'] == A_COMMIT
                and value['source_sha256'] == A_SOURCE and value['wheel']['sha256'] == A_WHEEL,
                'fixed_baseline_install_drift')
    else:
        same = subprocess.check_output(['git','-C',str(HERE.parents[1]),'rev-list','--parents','-n','1',
                                        value['candidate_commit']]).decode().split()
        require(same == [value['candidate_commit'], A_COMMIT] and value['source_sha256'] != A_SOURCE
                and value['wheel']['sha256'] != A_WHEEL, 'candidate_not_direct_child')
    installed = Path(value['installation']['path']).resolve(strict=True)
    source = [pin(installed / row['path']) for row in value['source_manifest']]
    require([row['sha256'] for row in source] == [row['sha256'] for row in value['source_manifest']],
            'installed_arm_source_drift')
    receipts = [present, *source]
    receipts.extend(pin(confirmed(value[name])) for name in ('wheel', 'build', 'blender', 'python'))
    receipts.extend(pin(confirmed(dep['module'])) for dep in value['dependencies'].values())
    return {'product': value['candidate_commit'], 'site': str(installed),
            'product_source_sha256': value['source_sha256'], 'product_source_files': value['runtime_sources'],
            'wheel': value['wheel'], 'custody': present}, value, receipts


def prepare(root):
    admin = pin(root/'preflight/ADMIN_PLAN.md')
    require(root.name == BATCH and admin['sha256'] == ADMIN and sys.flags.isolated and sys.dont_write_bytecode,
            'wrong_natural_batch_or_interpreter')
    fixed = [admin, pin(Path(__file__)), pin(old.CLI), pin(old.prior.CLI_RECORD)]
    for name, digest in LIBRARIES.items():
        row = pin(RETAINED/name)
        require(row['sha256'] == digest, 'retained_natural_runtime_changed/' + name)
        fixed.append(row)
    fixed.extend(pin(p) for p in old.fixed_libraries())
    transport_receipt = pin(root.parent/LAST_RUN/'preflight/TRANSPORT_RESULT.json')
    transport = read(transport_receipt['path'])
    require(transport_receipt['sha256'] == TRANSPORT_RECEIPT and transport['passed'] is True
            and transport['Blender'] == transport['models'] == 0
            and transport['formal_transport'] == pin(RETAINED/'transport.py')
            and set(transport['cases']) == {'normal', 'missing_last', 'reset'}, 'retained_paired_close_not_authenticated')
    fixed.extend([transport_receipt, transport['plan'], *transport['cases'].values()])
    a, orig_a, evidence_a = admitted_install(root, 'A')
    b, orig_b, evidence_b = admitted_install(root, 'B')
    require(orig_a['python'] == orig_b['python'] and orig_a['blender'] == orig_b['blender']
            and orig_a['dependencies'] == orig_b['dependencies']
            and Path(sys.executable).resolve() == Path(orig_a['python']['path']),
            'asymmetric_actual_environment')
    fixed.extend(evidence_a)
    fixed.extend(evidence_b)
    fixture = root/'preflight/fixture'
    prompts = {label: pin(fixture/f'PROMPT_{label}.txt') for label in ('K','T')}
    login = subprocess.run([str(old.CLI), 'login', 'status'], capture_output=True, timeout=15,
                           check=True, creationflags=old.NO_WINDOW)
    require(b'Logged in using ChatGPT' in login.stdout + login.stderr, 'existing_chatgpt_login_not_available')
    version = subprocess.run([str(old.CLI), '--version'], capture_output=True, timeout=15,
                             check=True, creationflags=old.NO_WINDOW)
    require(version.stdout.strip().endswith(old.REQUESTED['version'].encode()), 'unexpected_cli_version')
    return {'batch': BATCH, 'order': list(ORDER), 'slots': list(ORDER),
            'limits': old.LIMITS, 'arms': {'A': a, 'B': b},
            'jobs': {label: {'arm': label[0], 'topic': TOPICS[label[1]],
                             'prompt': prompts[TOPICS[label[1]]]} for label in ORDER},
            'prompts': prompts, 'asset': pin(fixture/'main.blend'),
            'retained_transport': transport_receipt,
            'python': orig_a['python'], 'blender': orig_a['blender'], 'cli': pin(old.CLI),
            'cli_request': old.REQUESTED, 'cli_config': old.prior.consumer_config(),
            'chatgpt_login_status': 'existing_login_confirmed', 'inputs': fixed}


def checked_plan(root, check_files=True):
    plan = read(root/PLAN)
    require(plan['batch'] == BATCH and plan['order'] == list(ORDER) and plan['slots'] == list(ORDER)
            and plan['limits'] == old.LIMITS and plan['cli_request'] == old.REQUESTED
            and confirmed(plan['cli']) == old.CLI.resolve()
            and confirmed(plan['python']) == Path(sys.executable).resolve(), 'changed_natural_ab_plan')
    if check_files:
        for row in [*plan['inputs'], plan['asset'], *plan['prompts'].values()]:
            confirmed(row)
    return plan


def arm_config(plan, arm):
    return {**plan, **plan['arms'][arm]}


def cold_arm(root, arm):
    from transport import start_transport

    plan = checked_plan(root)
    settings = arm_config(plan, arm)
    folder = root/'preflight/natural_cold'/arm
    workspace = folder/'workspace'
    workspace.mkdir(parents=True)
    source = old.cold_source(root)
    deadline = time.perf_counter_ns() + 65_000_000_000
    bridge = old.bridge_for(settings, folder, old.prior.ReplayHost(read(source)), deadline)
    requests = []

    def add(method, params):
        requests.append({'jsonrpc':'2.0','id':len(requests)+1, 'method':method, 'params':params})

    def call(tool, arguments):
        add('tools/call', {'name':tool, 'arguments':arguments})

    add('initialize', {'protocolVersion':'2025-03-26','capabilities':{},
                       'clientInfo':{'name':'owned-entry-discovery-cold','version':'1'}})
    add('tools/list', {})
    call('execute_python', {'code': 'import numpy as np\ns = np.arange(3)'})
    call('execute_python', {'code': 'print(int(s.sum()))'})
    call('execute_python', {'code': 'import os'})
    call('read_scene', {'objects':['Part M','Fixture T']})
    call('render_view', {'object':'Part M','view':'TOP','source_triangle_indices':[2,3]})
    call(old.PRODUCT, {'query':{'mode':'active_observation','objects':[{'name':'Part M'}],
                      'focus':{'task_region':{'reference':{'name':'Fixture T'},'relation':'nearest_surface'}}},
                      'include_image':True, 'response_detail':'full'})
    call('read_images', {'refs':['unknown-reference']})
    data = b''.join(old.encode(item) + b'\n' for item in requests)
    (folder/'THIN_STDIN.bin').write_bytes(data)
    owner = start_transport(folder, bridge, deadline)
    thin = None
    code, out, err, problem = None, b'', b'', None
    cmd = [settings['python']['path'], '-IB', '-X', 'utf8', str(RETAINED/'transport.py'),
           'thin', str(owner.endpoint)]
    try:
        thin = subprocess.Popen(cmd, cwd=workspace, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, creationflags=old.NO_WINDOW)
        owner.bind_cli(thin.pid)
        out, err = thin.communicate(input=data, timeout=54)
        code = thin.returncode
    except subprocess.TimeoutExpired:
        thin.kill()
        out, err = thin.communicate(timeout=8)
        code = thin.returncode
        problem = 'cold_thin_timeout'
    finally:
        closure = owner.finish()
    (folder/'THIN_STDOUT.bin').write_bytes(out)
    (folder/'THIN_STDERR.bin').write_bytes(err)
    try:
        replies = [json.loads(line) for line in out.splitlines()]
        require(problem is None and code == 0 and closure['closed'] and closure['zero_in_flight']
                and closure['transport_eof'] and closure['error'] is None
                and closure['paired_exchanges'] == len(requests) == 9
                and [r['id'] for r in replies] == list(range(1,len(requests)+1)), 'actual_shared_Thin_close_failed')
        tools = replies[1]['result']['tools']
        names = [t['name'] for t in tools]
        require(replies[0]['result']['_meta']['human_eye']['source_sha256'] == settings['product_source_sha256']
                and tools[:-1] == old.TOOLS and names == [t['name'] for t in old.TOOLS]+[old.PRODUCT],
                'actual_cold_catalogue_or_runtime_drift')
        statuses = [r['result']['isError'] for r in replies[2:]]
        require(statuses == [False,False,True,False,False,False,True]
                and json.loads(replies[3]['result']['content'][0]['text'])['stdout'].strip() == '3'
                and all(any(block['type']=='image' for block in r['result']['content']) for r in replies[6:8]),
                'actual_cold_ordinary_or_nearest_surface_dispatch_failed')
        physical = folder/'physical_frames.jsonl'
        frames = [json.loads(row) for row in physical.read_bytes().splitlines()]
        require(2 <= len(frames) <= old.MAX_RASTERS and all(row['frame_status']=='bound' for row in frames),
                'actual_cold_first_frame_binding_failed')
        argv = old.cli_argv(workspace, folder, owner.endpoint, settings, names)
        require(argv[-1]=='-' and '--ephemeral' in argv and 'resume' not in argv, 'new_model_slot_not_ephemeral')
        verdict = {'passed':True, 'actual_tools':tools, 'actual_tools_sha256':sha256(old.encode(tools)).hexdigest(),
                   'actual_catalogue_wire':pin(folder/'wire/002/RX.bin'),
                   'actual_wire':pin(folder/'wire/INDEX.jsonl'), 'physical_frames':pin(physical),
                   'statuses':statuses, 'cold_cli_argv':argv}
    except (ValueError, TypeError, KeyError, IndexError, OSError) as error:
        verdict = {'passed':False, 'failure':str(error)}
    write(folder/'RESULT.json', {'batch':BATCH, 'arm':arm, 'plan':pin(root/PLAN), 'source':pin(source),
           'actual_Blender':0, 'models':0, 'closure':closure, 'actual_thin_exit':code, **verdict})
    return int(not verdict['passed'])


def compare_catalogues(a, b):
    def brief(tools):
        observer, = [item for item in tools if item['name'] == old.PRODUCT]
        common = [{k:v for k,v in item.items() if not (item is observer and k=='description')} for item in tools]
        return observer['description'].encode('utf8'), common

    old_desc, a_rest = brief(a)
    new_desc, b_rest = brief(b)
    require(a_rest == b_rest and old_desc != new_desc, 'public_difference_exceeds_one_description')
    return {'all_other_semantics_equal':True,
            'baseline_description_bytes':len(old_desc), 'candidate_description_bytes':len(new_desc),
            'description_byte_delta':len(new_desc)-len(old_desc),
            'baseline_catalogue_bytes':len(old.encode(a)), 'candidate_catalogue_bytes':len(old.encode(b)),
            'catalogue_byte_delta':len(old.encode(b))-len(old.encode(a))}


def cold(root):
    plan = checked_plan(root)
    group = root/'preflight/natural_cold'
    group.mkdir(exist_ok=False)
    arms = {}
    for arm in ('A','B'):
        capture = group/f'{arm}_CHILD_STDOUT.bin'
        errors = group/f'{arm}_CHILD_STDERR.bin'
        cmd = [sys.executable, '-IB', '-X','utf8', str(Path(__file__)),str(root),'cold-arm',arm]
        with capture.open('xb') as out, errors.open('xb') as err:
            try:
                with subprocess.Popen(cmd, cwd=group, stdin=subprocess.DEVNULL, stdout=out, stderr=err,
                                      creationflags=old.NO_WINDOW) as proc:
                    try:
                        code = proc.wait(timeout=75)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait(8)
                        code = None
            except OSError:
                code = None
        result = group/arm/'RESULT.json'
        arms[arm] = (read(result) | {'result':pin(result), 'exit':code}) if result.is_file() else {
            'passed':False,'exit':code,'missing_child_result':True}
        arms[arm].update(child_stdout=pin(capture), child_stderr=pin(errors))
    passed = all(row['passed'] and row['exit']==0 for row in arms.values())
    difference, failure = None, None
    if passed:
        try:
            difference = compare_catalogues(arms['A']['actual_tools'],arms['B']['actual_tools'])
        except ValueError as error:
            passed,failure=False,str(error)
    write(root/COLD, {'batch':BATCH, 'passed':passed, 'plan':pin(root/PLAN), 'arms':arms,
          'catalogue_delta':difference, 'failure':failure, 'no_Blender_or_model':True,
          'retained_transport':plan['retained_transport']})
    return int(not passed)


def admitted(root, label):
    plan = checked_plan(root)
    freeze = read(root/FREEZE)
    require(freeze['batch']==BATCH and freeze['order']==list(ORDER)
            and confirmed(freeze['natural_plan'])==(root/PLAN).resolve()
            and confirmed(freeze['natural_cold'])==(root/COLD).resolve()
            and confirmed(freeze['product_preflight'])==(root/PRODUCT_GATE).resolve()
            and freeze['transport_preflight']==plan['retained_transport'], 'unbound_natural_ab_freeze')
    for item in freeze['inputs']:
        confirmed(item)
    require(freeze['fixture']['blend']==plan['asset'] and freeze['fixture']['prompts']==plan['prompts'],
            'frozen_natural_ab_fixture_or_prompt_changed')
    gate = read(root/COLD)
    require(read(root/PRODUCT_GATE)['passed'] is True, 'installed_arm_product_preflight_not_passed')
    require(gate['passed'] is True and gate['plan']==pin(root/PLAN) and gate['no_Blender_or_model'] is True
            and gate['retained_transport']==plan['retained_transport'], 'current_natural_ab_cold_not_accepted')
    prompt_plan = plan['jobs'][label]
    index = ORDER.index(label)
    for earlier in ORDER[:index]:
        require(read(root/'slots'/earlier/'closed.json')['safe_to_continue'] is True,
                'earlier_slot_not_proven_safe_to_continue/'+earlier)
    require(all(not (root/'slots'/later).exists() for later in ORDER[index:]),
            'same_or_future_natural_cell_already_used')
    arm = prompt_plan['arm']
    selected = gate['arms'][arm]
    confirmed(selected['result'])
    confirmed(selected['actual_catalogue_wire'])
    settings = arm_config(plan,arm)
    # The unchanged runner picks the last character of the slot label.
    # Map those two numeric labels to the same original frozen prompt pins.
    settings['prompts'] = {number:plan['prompts'][topic] for number,topic in TOPICS.items()}
    return settings,selected


def run(root, label):
    old.BATCH = BATCH
    old.admitted = admitted
    return old.run(root,label)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root',type=lambda value:Path(value).resolve(strict=True))
    parser.add_argument('phase',choices=('plan','cold','cold-arm','run'))
    parser.add_argument('label',nargs='?')
    args=parser.parse_args()
    if args.phase=='plan':
        write(args.root/PLAN,prepare(args.root))
    elif args.phase=='cold':
        raise SystemExit(cold(args.root))
    elif args.phase=='cold-arm':
        require(args.label in ('A','B'),'cold_arm_missing')
        raise SystemExit(cold_arm(args.root,args.label))
    else:
        require(args.label in ORDER,'formal_case_missing')
        raise SystemExit(run(args.root,args.label))
