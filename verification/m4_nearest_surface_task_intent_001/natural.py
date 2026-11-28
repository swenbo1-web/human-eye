"""Replay the new intent fixture through Thin, then launch only the four frozen cells."""
import argparse
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
M1 = HERE.parent/'m1_nearest_surface_entry_discovery_001'
spec = importlib.util.spec_from_file_location('retained_entry_discovery_runner', M1/'natural.py')
m1 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m1)
old = m1.old
pin, read, write, require, confirmed = m1.pin, m1.read, m1.write, m1.require, m1.confirmed
BATCH = 'M4-NEAREST-SURFACE-TASK-INTENT-001'
ADMIN = 'd20126432117c340282ea9dc11b6964d7147c890cfa1d5f775b2bef8116d40eb'
PRODUCT = '2f7f492d7d0fd1af2ff956228d31bd57b5e31ddc'
SOURCE = '5c3ee219ae51a095ef26ec6bc71e11cafe937413372cc65a245e601a5710de85'
WHEEL = 'b839cbd608a7c18f59ce83b83a5df4f98d95903039c9aea4bdb0271d574d0719'
CUSTODY = '21d7fb4a0c97cb508135632418c7c6d4a43732c5c6c46ba763600b1e7ec23593'
PREVIOUS_RESULT = '55a6453591673aea1e1d1b43b1cc48bc5f9a01353233879ec269bc771d9c85a0'
M1_CODE = '6cb019fa3c74c5312679d949d70630a159c3b155bc7399f719957eccd59f858b'
ORDER, TOPICS = m1.ORDER, m1.TOPICS
TARGET = 'Item X'
REFERENCES = {'K':'Item G', 'T':'Item Q'}
PLAN, COLD, FREEZE = m1.PLAN, m1.COLD, m1.FREEZE
CAPTURE = 'preflight/INTENT_OFFLINE_CAPTURE.json'
QUALIFICATION = 'preflight/INTENT_PRODUCT_PREFLIGHT.json'


def prepare(root):
    admin = pin(root/'preflight/ADMIN_PLAN.md')
    require(root.name == BATCH and admin['sha256']==ADMIN and sys.flags.isolated and sys.dont_write_bytecode
            and pin(M1/'natural.py')['sha256']==M1_CODE, 'wrong_batch_or_existing_runner')
    retained = root.parent/'M1-NEAREST-SURFACE-ENTRY-DISCOVERY-001'
    custody = pin(retained/'preflight/INSTALL_CUSTODY.json')
    install = read(custody['path'])
    require(custody['sha256']==CUSTODY and install['passed'] is True and install['candidate_commit']==PRODUCT
            and install['source_sha256']==SOURCE and install['wheel']['sha256']==WHEEL
            and install['runtime_sources']==len(install['source_manifest'])==146
            and Path(sys.executable).resolve()==confirmed(install['python']), 'wrong_identical_arm_install')
    site = Path(install['installation']['path']).resolve(strict=True)
    earlier = pin(retained/'preflight/NATURAL_COLD.json')
    receipt = read(earlier['path'])
    require(earlier['sha256']==PREVIOUS_RESULT and receipt['passed'] is True and receipt['arms']['B']['passed'] is True,
            'prior_actual_catalogue_or_cold_changed')
    prior_transport = receipt['retained_transport']
    source_path = confirmed(prior_transport)
    require(prior_transport['sha256']==m1.TRANSPORT_RECEIPT, 'prior_close_material_changed')
    transport = read(source_path)
    require(transport['passed'] is True and transport['Blender']==transport['models']==0
            and set(transport['cases'])=={'normal','missing_last','reset'}
            and transport['formal_transport']==pin(m1.RETAINED/'transport.py'), 'prior_paired_close_not_accepted')
    inputs = [admin, pin(__file__), pin(M1/'natural.py'), custody, earlier, prior_transport,
              pin(old.CLI), pin(old.prior.CLI_RECORD), transport['plan'], *transport['cases'].values(),
              *(pin(f) for f in old.fixed_libraries())]
    for name, digest in m1.LIBRARIES.items():
        known = pin(m1.RETAINED/name)
        require(known['sha256']==digest, 'prior_pinned_ordinary_or_transport_code_mismatch')
        inputs.append(known)
    for file in install['source_manifest']:
        actual = pin(site/file['path'])
        require(actual['sha256']==file['sha256'], 'actual_product_file_changed/'+file['path'])
        inputs.append(actual)
    inputs.extend(install[k] for k in ('blender','python','wheel','build'))
    inputs.extend(dep['module'] for dep in install['dependencies'].values())
    for item in inputs:
        confirmed(item)
    fixture = root/'preflight/fixture'
    prompts = {label:pin(fixture/f'PROMPT_{label[0]}_{TOPICS[label[1]]}.txt') for label in ORDER}
    found = {label:Path(record['path']).read_bytes() for label,record in prompts.items()}
    a1,b1,b2,a2 = [found[label] for label in ORDER]
    suffix = b1[len(a1):]
    ref_k,ref_t = [REFERENCES[k].encode() for k in ('K','T')]
    require(suffix and b1==a1+suffix and b2==a2+suffix and a1.count(ref_k)==b1.count(ref_k)==1
            and a1.replace(ref_k,ref_t)==a2 and b1.replace(ref_k,ref_t)==b2, 'intent_prompt_delta_not_single_suffix')
    source = pin(fixture/'EVALUATED_SOURCE.json')
    replay = pin(root/CAPTURE)
    asset = pin(fixture/'main.blend')
    verify_replay(read(replay['path']),read(source['path']),asset['sha256'])
    options = old.prior.consumer_config()
    login = subprocess.run([str(old.CLI),'login','status'],capture_output=True,timeout=15,check=True,
                           creationflags=old.NO_WINDOW)
    require(b'Logged in using ChatGPT' in login.stdout+login.stderr, 'existing_chatgpt_login_not_available')
    version = subprocess.run([str(old.CLI),'--version'],capture_output=True,timeout=15,check=True,
                             creationflags=old.NO_WINDOW)
    require(version.stdout.strip().endswith(old.REQUESTED['version'].encode()), 'unexpected_cli_version')
    return {'batch':BATCH,'order':list(ORDER),'slots':list(ORDER),'limits':old.LIMITS,
            'product':PRODUCT,'product_source_sha256':SOURCE,'product_source_files':146,'site':str(site),
            'wheel':install['wheel'],'blender':install['blender'],'python':install['python'],'cli':pin(old.CLI),
            'cli_config':options,'cli_request':old.REQUESTED,'asset':asset,'prompts':prompts,
            'jobs':{label:{'arm':label[0],'topic':TOPICS[label[1]],'prompt':prompts[label]} for label in ORDER},
            'prior_actual_catalogue':receipt['arms']['B']['actual_tools'],'prior_actual_catalogue_receipt':earlier,
            'retained_transport':prior_transport,'source_for_cold':source,'replay_for_cold':replay,
            'chatgpt_login_status':'existing_login_confirmed','inputs':inputs}


def verify_replay(replay, source, identity):
    independent = {mesh['name']:mesh for mesh in source['objects']}
    displayed = {row['host_id']:row for row in replay['display_snapshot']['objects']}
    require(source['asset_sha256']==identity and len(independent)==len(replay['meshes'])
            and set(independent)=={TARGET,*REFERENCES.values()}, 'offline_capture_asset_or_names_not_bound')
    for mesh in replay['meshes']:
        expected = independent[mesh['name']]
        flags = displayed[mesh['object_id']]
        require(mesh['vertices']==expected['vertices'] and mesh['faces']==expected['faces']
                and flags['visible_get']==expected['displayed']
                and flags['instance_id']==replay['host_identity']['object_instances'][mesh['object_id']],
                'offline_capture_source_rows_changed/'+mesh['name'])


def checked_plan(root):
    plan = read(root/PLAN)
    require(plan['batch']==BATCH and plan['order']==list(ORDER) and plan['slots']==list(ORDER)
            and plan['limits']==old.LIMITS and plan['product']==PRODUCT and plan['product_source_sha256']==SOURCE
            and plan['cli_request']==old.REQUESTED and confirmed(plan['python'])==Path(sys.executable).resolve()
            and confirmed(plan['cli'])==old.CLI.resolve(), 'changed_task_intent_natural_plan')
    for item in [plan['asset'],*plan['prompts'].values(),*plan['inputs']]:
        confirmed(item)
    return plan


def cold_arm(root, arm):
    from transport import start_transport

    plan = checked_plan(root)
    source = confirmed(plan['source_for_cold'])
    replay = confirmed(plan['replay_for_cold'])
    geometry = read(replay)
    verify_replay(geometry,read(source),plan['asset']['sha256'])
    folder = root/'preflight/natural_cold'/arm
    workspace = folder/'workspace'
    workspace.mkdir(parents=True)
    deadline = time.perf_counter_ns() + 65_000_000_000
    bridge = old.bridge_for(plan,folder,old.prior.ReplayHost(geometry),deadline)
    requests = []

    def add(method, params, label):
        packet = {'jsonrpc':'2.0','id':len(requests)+1,'method':method,'params':params}
        requests.append((label,packet))

    def call(name, arguments, label):
        add('tools/call',{'name':name,'arguments':arguments},label)

    add('initialize',{'protocolVersion':'2025-03-26','capabilities':{},
        'clientInfo':{'name':'owned-task-intent-cold','version':'1'}},'initialize')
    add('tools/list',{},'directory')
    call('execute_python',{'code':'import numpy as np\ns = np.arange(3)'},'ordinary_bind')
    call('execute_python',{'code':'print(int(s.sum()))'},'ordinary_read')
    call('read_scene',{'objects':[TARGET,*REFERENCES.values()]},'ordinary_scene')
    for label,reference in REFERENCES.items():
        call(old.PRODUCT,{'query':{'mode':'active_observation','objects':[{'name':TARGET}],
             'focus':{'task_region':{'reference':{'name':reference},'relation':'nearest_surface'}}}},label)
    call('read_images',{'refs':['unknown-reference']},'terminal_refusal')
    data = b''.join(old.encode(packet) + b'\n' for _,packet in requests)
    (folder/'THIN_STDIN.bin').write_bytes(data)
    owner = start_transport(folder,bridge,deadline)
    command = [plan['python']['path'],'-IB','-X','utf8',str(m1.RETAINED/'transport.py'),'thin',str(owner.endpoint)]
    child,code,out,err = None,None,b'',b''
    try:
        child = subprocess.Popen(command,cwd=workspace,stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE,creationflags=old.NO_WINDOW)
        owner.bind_cli(child.pid)
        out,err = child.communicate(data,timeout=54)
        code = child.returncode
    except subprocess.TimeoutExpired:
        child.kill()
        out,err = child.communicate(timeout=8)
        code = child.returncode
    finally:
        closure = owner.finish()
    (folder/'THIN_STDOUT.bin').write_bytes(out)
    (folder/'THIN_STDERR.bin').write_bytes(err)
    try:
        replies = [json.loads(line) for line in out.splitlines()]
        require(code==0 and closure['closed'] and closure['zero_in_flight'] and closure['transport_eof']
                and closure['error'] is None and closure['paired_exchanges']==len(requests)==8
                and [r['id'] for r in replies]==list(range(1,9)), 'actual_intent_Thin_delivery_or_close_failed')
        tools = replies[1]['result']['tools']
        require(replies[0]['result']['_meta']['human_eye']['source_sha256']==SOURCE
                and tools==plan['prior_actual_catalogue'], 'identical_real_intent_catalogue_not_preserved')
        statuses = [reply['result']['isError'] for reply in replies[2:]]
        require(statuses==[False,False,False,False,False,True]
                and json.loads(replies[3]['result']['content'][0]['text'])['stdout'].strip()=='3'
                and all(any(x['type']=='image' for x in reply['result']['content']) for reply in replies[5:7]),
                'ordinary_or_new_fixture_nearest_image_not_delivered')
        physical = folder/'physical_frames.jsonl'
        frames = [json.loads(line) for line in physical.read_bytes().splitlines()]
        require(2<=len(frames)<=old.MAX_RASTERS and all(item['frame_status']=='bound' for item in frames),
                'offline_software_frame_not_bound_to_actual_producer')
        argv = old.cli_argv(workspace,folder,owner.endpoint,plan,[tool['name'] for tool in tools])
        require(argv[-1]=='-' and '--ephemeral' in argv and 'resume' not in argv, 'natural_client_not_fresh')
        verdict = {'passed':True,'actual_tools':tools,'actual_tools_sha256':sha256(old.encode(tools)).hexdigest(),
                   'actual_catalogue_wire':pin(folder/'wire/002/RX.bin'),'actual_wire':pin(folder/'wire/INDEX.jsonl'),
                   'physical_frames':pin(physical),'statuses':statuses,'cold_cli_argv':argv,
                   'fixture_cases':{name:{'outer_tx':pin(folder/f'wire/{packet["id"]:03d}/TX.bin'),
                      'outer_rx':pin(folder/f'wire/{packet["id"]:03d}/RX.bin'),
                      'producer':pin(folder/f'wire/{packet["id"]:03d}/PRODUCER.json')}
                       for name,packet in requests if name in REFERENCES}}
    except (ValueError,KeyError,TypeError,IndexError,OSError) as error:
        verdict = {'passed':False,'failure':str(error)}
    write(folder/'RESULT.json',{'batch':BATCH,'arm':arm,'plan':pin(root/PLAN),'source':pin(source),'replay':pin(replay),
         'closure':closure,'actual_thin_exit':code,'actual_Blender':0,'models':0,**verdict})
    return int(not verdict['passed'])


def cold(root):
    plan = checked_plan(root)
    group = root/'preflight/natural_cold'
    group.mkdir(exist_ok=False)
    arms = {}
    for arm in ('A','B'):
        stdout,stderr = group/f'{arm}_CHILD_STDOUT.bin', group/f'{arm}_CHILD_STDERR.bin'
        args = [sys.executable,'-IB','-X','utf8',str(Path(__file__)),str(root),'cold-arm',arm]
        with stdout.open('xb') as out,stderr.open('xb') as err:
            try:
                result = subprocess.run(args,cwd=group,stdin=subprocess.DEVNULL,stdout=out,stderr=err,
                                        creationflags=old.NO_WINDOW,timeout=75)
                code = result.returncode
            except subprocess.TimeoutExpired:
                code = None
        file = group/arm/'RESULT.json'
        arms[arm] = (read(file) | {'result':pin(file)}) if file.is_file() else {'passed':False,'missing_result':True}
        arms[arm].update(exit=code,child_stdout=pin(stdout),child_stderr=pin(stderr))
    same = all(row['passed'] and row['exit']==0 for row in arms.values()) and (
          arms['A']['actual_tools']==arms['B']['actual_tools']==plan['prior_actual_catalogue'])
    write(root/COLD,{'batch':BATCH,'plan':pin(root/PLAN),'passed':same,'arms':arms,
        'same_actual_catalogue':same,'catalogue_delta_bytes':0 if same else None,
        'retained_transport':plan['retained_transport'],'no_Blender_or_model':True})
    return int(not same)


def admitted(root,label):
    plan = checked_plan(root)
    frozen = read(root/FREEZE)
    require(frozen['batch']==BATCH and frozen['order']==list(ORDER)
            and confirmed(frozen['natural_plan'])==(root/PLAN).resolve()
            and confirmed(frozen['natural_cold'])==(root/COLD).resolve()
            and confirmed(frozen['product_preflight'])==(root/QUALIFICATION).resolve()
            and frozen['transport_preflight']==plan['retained_transport'], 'unbound_task_intent_frozen_launch')
    for item in frozen['inputs']:
        confirmed(item)
    require(frozen['fixture']['blend']==plan['asset'] and frozen['fixture']['prompts']==plan['prompts']
            and read(root/QUALIFICATION)['passed'] is True, 'frozen_fixture_or_current_product_probe_changed')
    gate = read(root/COLD)
    require(gate['passed'] is True and gate['plan']==pin(root/PLAN) and gate['same_actual_catalogue'] is True
            and gate['retained_transport']==plan['retained_transport'], 'current_actor_cold_not_bound')
    index = ORDER.index(label)
    for previous in ORDER[:index]:
        require(read(root/'slots'/previous/'closed.json')['safe_to_continue'] is True,
                'prior_intent_slot_not_safe/'+previous)
    require(all(not (root/'slots'/later).exists() for later in ORDER[index:]), 'same_or_future_intent_slot_used')
    callback = gate['arms'][label[0]]
    confirmed(callback['result'])
    confirmed(callback['actual_catalogue_wire'])
    require(plan['jobs'][label]['prompt']==plan['prompts'][label], 'per_slot_prompt_binding_changed')
    return {**plan,'prompts':{label[-1]:plan['prompts'][label]}},callback


def run(root,label):
    old.admitted = admitted
    old.BATCH = BATCH
    return old.run(root,label)


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root',type=lambda value:Path(value).resolve(strict=True))
    parser.add_argument('action',choices=('plan','cold','cold-arm','run'))
    parser.add_argument('label',nargs='?')
    args = parser.parse_args()
    if args.action=='plan':
        write(args.root/PLAN,prepare(args.root))
    elif args.action=='cold':
        raise SystemExit(cold(args.root))
    elif args.action=='cold-arm':
        require(args.label in ('A','B'),'missing_cold_arm')
        raise SystemExit(cold_arm(args.root,args.label))
    else:
        require(args.label in ORDER,'missing_formal_slot')
        raise SystemExit(run(args.root,args.label))
