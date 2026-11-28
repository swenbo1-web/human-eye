"""Preserve Thin, CLI and Blender custody while running the component-reference A/B."""
import argparse
import importlib.util
import json
from hashlib import sha256
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time
from zipfile import ZipFile

HERE = Path(__file__).resolve().parent
RETAINED = HERE.parent/'m4_nearest_surface_task_intent_001'
spec = importlib.util.spec_from_file_location('retained_task_intent_runner',RETAINED/'natural.py')
previous = importlib.util.module_from_spec(spec)
spec.loader.exec_module(previous)
m1, old = previous.m1, previous.old
pin, read, write, confirmed, require = previous.pin, previous.read, previous.write, previous.confirmed, previous.require
BATCH = 'M4-NEAREST-SURFACE-COMPONENT-REF-001'
ADMIN = '45ca48b93c667b45ba9cc695aad53c0930bdb030527968ff9641425dd6762fab'
PRIOR_BATCH = 'M4-NEAREST-SURFACE-TASK-INTENT-001'
PRIOR_CODE = '8d3085ff5e23fb7a1183e85ff9d2a91618ad17b136c8474f01c2f44bf6bc30fa'
ARCHIVE = '8bbf01d17d7f197f21ff1101a2349cbd05603e638e72351e6badfc1463434d99'
INDEX = '66fc38d844eae6554b283f0b6278168c520ee125bb9f40a0361ded1be94f0d05'
CAPTURE = 'a920b0e2d5a233cfae36307e317cb85d3c4c554c096dbce3b2a9f79bb0483545'
ASSET = '2cb78efc91bfded88d8409f50e3de8e309f68a7b6d66ab0d05ad37a93dff0341'
PRIOR_COLD = 'ac36a5778de5dfcb269c723bc822719a6908994821a7e53d29eadba73916ea96'
ORDER, TOPICS = previous.ORDER, previous.TOPICS
TARGET, REFERENCE = previous.TARGET, previous.REFERENCES
PLAN, COLD, FREEZE = previous.PLAN, previous.COLD, previous.FREEZE
QUALIFICATION = 'preflight/COMPONENT_PRODUCT_PREFLIGHT.json'


def installs(root):
    proof = [
        root.parent/'M1-NEAREST-SURFACE-ENTRY-DISCOVERY-001/preflight/INSTALL_CUSTODY.json',
        root/'preflight/INSTALL_CUSTODY.json',
    ]
    a, b = map(read,proof)
    require(pin(proof[0])['sha256']==previous.CUSTODY and a['candidate_commit']==previous.PRODUCT
            and a['source_sha256']==previous.SOURCE and a['wheel']['sha256']==previous.WHEEL
            and a['blender']==b['blender'] and a['python']==b['python'] and a['dependencies']==b['dependencies']
            and Path(sys.executable).resolve()==confirmed(a['python']), 'asymmetric_or_changed_actual_install')
    lineage = subprocess.check_output(['git','-C',str(HERE.parents[1]),'rev-list','--parents','-n','1',
                                      b['candidate_commit']]).decode().split()
    require(lineage==[b['candidate_commit'],a['candidate_commit']] and b['source_sha256']!=a['source_sha256']
            and b['wheel']['sha256']!=a['wheel']['sha256'],'new_install_not_direct_isolated_candidate')
    arms, receipts = {}, []
    for arm, value, path in zip(('A','B'),(a,b),proof,strict=True):
        site = Path(value['installation']['path']).resolve(strict=True)
        manifest = value['source_manifest']
        loaded = [pin(site/row['path']) for row in manifest]
        require(value['passed'] is True and value['runtime_sources']==len(manifest)==146
                and all(item['sha256']==row['sha256'] for item,row in zip(loaded,manifest,strict=True)),
                'actual_installed_runtime_drift/'+arm)
        arms[arm] = {'product':value['candidate_commit'],'site':str(site),'product_source_sha256':value['source_sha256'],
                     'product_source_files':146,'wheel':value['wheel'],'custody':pin(path)}
        receipts.extend([pin(path), *loaded, *(value[k] for k in ('python','blender','wheel','build'))])
        receipts.extend(dep['module'] for dep in value['dependencies'].values())
    require(arms['A']['site']!=arms['B']['site'],'shared_candidate_install_path')
    return arms,a,receipts


def frozen_fixture(root):
    origin = root.parent/PRIOR_BATCH
    archive = pin(origin/'sealed/ORIGINAL_RUNTIME.zip')
    index = pin(origin/'sealed/RAW_INDEX.json')
    custody = pin(root/'preflight/FIXTURE_CUSTODY.json')
    receipt, manifest = read(custody['path']),read(index['path'])
    require(archive['sha256']==receipt['prior_archive_sha256']==ARCHIVE
            and index['sha256']==receipt['prior_manifest_sha256']==INDEX and receipt['new_Blender']==0
            and receipt['source_slot']=='A1' and receipt['source_record']=='slots/A1/post_capture.json',
            'prior_sealed_fixture_not_bound')
    capture = receipt['capture']
    require(confirmed(capture)==(root/'preflight/SEALED_CAPTURE.json').resolve() and capture['sha256']==CAPTURE,
            'current_replay_not_exact_old_terminal')
    prompts, argument_pins, arguments = {},{},{}
    with ZipFile(archive['path']) as bundle:
        def original(name):
            raw = bundle.read(name)
            require(manifest['members'][name]=={'bytes':len(raw),'sha256':sha256(raw).hexdigest()},
                    'old_sealed_member_changed/'+name)
            return raw

        for name, item in receipt['copied_asset_inputs'].items():
            require(confirmed(item)==(root/'preflight/fixture'/name).resolve()
                    and Path(item['path']).read_bytes()==original('preflight/fixture/'+name),
                    'current_fixture_file_not_exact_original/'+name)
        require(Path(capture['path']).read_bytes()==original(receipt['source_record']),
                'current_replay_does_not_match_original_terminal')
        closed = json.loads(original('slots/A1/closed.json'))
        require(closed['same_before_after_capture'] is True and closed['safe_to_continue'] is True
                and closed['blender_exit']==closed['cli_exit']==0 and closed['post_capture']['sha256']==CAPTURE
                and closed['fixture_sha256_before']==closed['fixture_sha256_after']==ASSET,
                'original_slot_not_safely_closed_or_frozen')
        for topic,slot in (('K','A1'),('T','B2')):
            name = f'slots/{slot}/wire/004/TX.bin'
            raw = original(name)
            outer = json.loads(raw)
            require(outer['method']=='tools/call' and outer['params']['name']==old.PRODUCT, 'wrong_prior_focus_tool')
            args = outer['params']['arguments']
            require(args['query']=={'mode':'active_observation','objects':[{'name':TARGET}],
               'focus':{'task_region':{'reference':{'name':REFERENCE[topic]},'relation':'nearest_surface'}}},
               'wrong_prior_active_focus_arguments')
            arguments[topic] = args
            argument_pins[topic] = {'archive_member':name,'sha256':sha256(raw).hexdigest(),'bytes':len(raw)}
    asset = receipt['copied_asset_inputs']['main.blend']
    require(asset['sha256']==ASSET,'different_new_formal_asset')
    prompts.update(A1=receipt['copied_asset_inputs']['PROMPT_A_K.txt'],
                   B1=receipt['copied_asset_inputs']['PROMPT_A_K.txt'],
                   B2=receipt['copied_asset_inputs']['PROMPT_B_T.txt'],
                   A2=receipt['copied_asset_inputs']['PROMPT_B_T.txt'])
    return asset,prompts,capture,arguments,argument_pins,[archive,index,custody,*receipt['copied_asset_inputs'].values()]


def prepare(root):
    admin = pin(root/'preflight/ADMIN_PLAN.md')
    require(root.name==BATCH and admin['sha256']==ADMIN and pin(RETAINED/'natural.py')['sha256']==PRIOR_CODE
            and sys.flags.isolated and sys.dont_write_bytecode, 'wrong_batch_or_previous_runner')
    arms, base, receipts = installs(root)
    asset,prompts,capture,arguments,arg_receipts,assets = frozen_fixture(root)
    older = pin(root.parent/PRIOR_BATCH/'preflight/NATURAL_COLD.json')
    status = read(older['path'])
    prior_transport = status['retained_transport']
    close = read(confirmed(prior_transport))
    require(older['sha256']==PRIOR_COLD and status['passed'] is True and status['same_actual_catalogue'] is True
            and prior_transport['sha256']==m1.TRANSPORT_RECEIPT and close['passed'] is True
            and close['formal_transport']==pin(m1.RETAINED/'transport.py') and close['Blender']==close['models']==0,
            'changed_formal_thin_or_previous_catalogue')
    code = [pin(Path(__file__)),pin(RETAINED/'natural.py'),pin(previous.M1/'natural.py'),
            pin(old.CLI),pin(old.prior.CLI_RECORD),*(pin(s) for s in old.fixed_libraries())]
    for name,digest in m1.LIBRARIES.items():
        record = pin(m1.RETAINED/name)
        require(record['sha256']==digest,'previous_shared_recorder_changed/'+name)
        code.append(record)
    inputs = [admin,older,prior_transport,close['plan'],*close['cases'].values(),*code,*receipts,*assets]
    for item in inputs:
        confirmed(item)
    options = old.prior.consumer_config()
    login = subprocess.run([str(old.CLI),'login','status'],capture_output=True,timeout=15,check=True,
                           creationflags=old.NO_WINDOW)
    require(b'Logged in using ChatGPT' in login.stdout+login.stderr,'fixed_existing_chatgpt_login_unavailable')
    version = subprocess.run([str(old.CLI),'--version'],capture_output=True,timeout=15,check=True,
                             creationflags=old.NO_WINDOW)
    require(version.stdout.strip().endswith(old.REQUESTED['version'].encode()),'fixed_cli_version_changed')
    return {'batch':BATCH,'order':list(ORDER),'slots':list(ORDER),'limits':old.LIMITS,'arms':arms,
            'asset':asset,'prompts':prompts,'source_for_cold':capture,'active_arguments':arguments,
            'prior_active_wires':arg_receipts,'prior_actual_catalogue':status['arms']['A']['actual_tools'],
            'retained_transport':prior_transport,'blender':base['blender'],'python':base['python'],'cli':pin(old.CLI),
            'cli_request':old.REQUESTED,'cli_config':options,
            'jobs':{cell:{'arm':cell[0],'topic':TOPICS[cell[1]],'prompt':prompts[cell]} for cell in ORDER},
            'inputs':inputs}


def checked_plan(root):
    plan = read(root/PLAN)
    require(plan['batch']==BATCH and plan['order']==plan['slots']==list(ORDER)
            and plan['limits']==old.LIMITS and plan['cli_request']==old.REQUESTED
            and plan['arms']['A']['product']==previous.PRODUCT and plan['asset']['sha256']==ASSET
            and confirmed(plan['python'])==Path(sys.executable).resolve() and confirmed(plan['cli'])==old.CLI.resolve()
            and confirmed(plan['source_for_cold'])==(root/'preflight/SEALED_CAPTURE.json').resolve(),
            'changed_component_natural_plan')
    for item in [plan['asset'],*plan['prompts'].values(),*plan['inputs']]:
        confirmed(item)
    return plan


def arm_settings(plan,arm):
    return {**plan,**plan['arms'][arm]}


def nearest_ref(reply, component=False):
    content = reply['result']['content']
    require(not reply['result']['isError'] and any(item['type']=='image' for item in content),
            'first_active_observation_not_delivered')
    focus = json.loads(next(row['text'] for row in content if row['type']=='text'))['facts']['focus']
    if not component:
        require(focus['region_ref']['source_triangle_indices']==[focus['primary_source_triangle_index']],
                'baseline_focus_single_ref_changed')
        return focus['region_ref']
    nearest = focus['nearest_surface']
    comp = nearest['component']
    require(comp['status']=='measured' and comp['scope']=='one_target_vertex_connected_component_to_reference_whole_object'
            and comp['distance_m']==nearest['distance_m']
            and focus['primary_source_triangle_index'] in comp['region_ref']['source_triangle_indices'],
            'unusable_whole_component_ref')
    return comp['region_ref']


def cold_arm(root,arm):
    from transport import MAX_WIRE, start_transport

    plan = checked_plan(root)
    settings = arm_settings(plan,arm)
    folder = root/'preflight/natural_cold'/arm
    workspace = folder/'workspace'
    workspace.mkdir(parents=True,exist_ok=False)
    source = confirmed(plan['source_for_cold'])
    deadline = time.perf_counter_ns()+65_000_000_000
    bridge = old.bridge_for(settings,folder,old.prior.ReplayHost(read(source)),deadline)
    owner = start_transport(folder,bridge,deadline)
    command = [settings['python']['path'],'-IB','-X','utf8',str(m1.RETAINED/'transport.py'),'thin',str(owner.endpoint)]
    calls, replies, stdout_queue = [],[],queue.Queue()
    child,status,error,reader = None,None,None,None
    with (folder/'THIN_STDERR.bin').open('xb') as stderr, (folder/'THIN_STDIN.bin').open('xb') as tx_log, \
         (folder/'THIN_STDOUT.bin').open('xb') as rx_log:
        try:
            child = subprocess.Popen(command,cwd=workspace,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=stderr,
                                     creationflags=old.NO_WINDOW)
            owner.bind_cli(child.pid)

            def receive():
                try:
                    while raw := child.stdout.readline(MAX_WIRE+1):
                        stdout_queue.put(raw)
                except (OSError, ValueError) as failure:
                    stdout_queue.put(failure)
                finally:
                    stdout_queue.put(None)

            reader = threading.Thread(target=receive,daemon=True)
            reader.start()

            def add(method,params,label):
                request = {'jsonrpc':'2.0','id':len(calls)+1,'method':method,'params':params}
                raw = old.encode(request)+b'\n'
                calls.append((label,request))
                tx_log.write(raw)
                tx_log.flush()
                child.stdin.write(raw)
                child.stdin.flush()
                rx = stdout_queue.get(timeout=max(1,min(25,(deadline-time.perf_counter_ns())/1e9)))
                require(type(rx) is bytes and len(rx)<=MAX_WIRE and rx.endswith(b'\n'), 'incomplete_actual_Thin_response')
                rx_log.write(rx)
                rx_log.flush()
                reply = json.loads(rx)
                require(reply['jsonrpc']=='2.0' and reply['id']==request['id'],'changed_response_identity')
                replies.append(reply)
                return reply

            def call(name,args,label):
                reply = add('tools/call',{'name':name,'arguments':args},label)
                if reply['result']['isError']:
                    detail = next((item.get('text','') for item in reply['result'].get('content', [])), '')
                    raise ValueError('actual_cold_tool_error/'+label+'/'+detail[:300])
                return reply

            add('initialize',{'protocolVersion':'2025-03-26','capabilities':{},
                'clientInfo':{'name':'owned-component-reference-cold','version':'1'}},'initialize')
            add('tools/list',{},'directory')
            call('execute_python',{'code':'import numpy as np\ns = np.arange(3)'},'ordinary_bind')
            computed = call('execute_python',{'code':'print(int(s.sum()))'},'ordinary_read')
            require(json.loads(computed['result']['content'][0]['text'])['stdout'].strip()=='3',
                    'ordinary_persistent_computation_failed')
            call('read_scene',{'objects':[TARGET,*REFERENCE.values()]},'ordinary_scene')
            focuses = {topic:call(old.PRODUCT,plan['active_arguments'][topic],topic+'_active') for topic in REFERENCE}

            def follow(topic, component):
                cited = nearest_ref(focuses[topic],component)
                scope = 'component' if component else 'single'
                call(old.PRODUCT,{'query':{'mode':'source_region','region_ref':cited,
                   'reference':{'name':REFERENCE[topic]},'requested_facts':['surface_proximity']},
                   'include_image':False,'response_detail':'brief'},topic+'_'+scope)

            for topic in REFERENCE:
                follow(topic,arm=='B')
            if arm=='B':
                follow('K',False)
        except (ValueError,TypeError,KeyError,IndexError,OSError,queue.Empty) as failure:
            error = type(failure).__name__+': '+str(failure)
        finally:
            if child is not None:
                child.stdin.close()
                try:
                    status = child.wait(timeout=11)
                except subprocess.TimeoutExpired:
                    child.kill()
                    status = child.wait(timeout=8)
                    error = error or 'owned_thin_close_timeout'
                if reader:
                    reader.join(4)
                child.stdout.close()
            closure = owner.finish()
    try:
        expected = 9 if arm=='A' else 10
        require(error is None and status==0 and closure['closed'] and closure['zero_in_flight']
                and closure['transport_eof'] and closure['error'] is None
                and closure['paired_exchanges']==len(calls)==len(replies)==expected,
                'actual_thin_pairing_failed/'+str(error))
        tools = replies[1]['result']['tools']
        require(replies[0]['result']['_meta']['human_eye']['source_sha256']==settings['product_source_sha256']
                and tools==plan['prior_actual_catalogue'], 'changed_natural_tools_list_or_install')
        physical = folder/'physical_frames.jsonl'
        frames = [json.loads(line) for line in physical.read_bytes().splitlines()]
        require(2<=len(frames)<=4 and all(item['frame_status']=='bound' for item in frames),
                'offline_physical_frame_not_bound')
        recorded = {}
        for label,packet in calls:
            if label.endswith(('_active','_single','_component')):
                directory = folder/f'wire/{packet["id"]:03d}'
                recorded[label] = {'ordinal':packet['id'],'tx':pin(directory/'TX.bin'),'rx':pin(directory/'RX.bin'),
                                   'producer':pin(directory/'PRODUCER.json')}
        verdict = {'passed':True,'actual_tools':tools,'actual_tools_sha256':sha256(old.encode(tools)).hexdigest(),
                   'actual_catalogue_wire':pin(folder/'wire/002/RX.bin'),'actual_wire':pin(folder/'wire/INDEX.jsonl'),
                   'physical_frames':pin(physical),'fixture_calls':recorded,
                   'cold_cli_argv':old.cli_argv(workspace,folder,owner.endpoint,settings,[tool['name'] for tool in tools])}
    except (ValueError,TypeError,KeyError,IndexError,OSError) as failure:
        verdict = {'passed':False,'failure':str(failure)}
    write(folder/'RESULT.json',{'batch':BATCH,'arm':arm,'plan':pin(root/PLAN),'source':pin(source),
      'closure':closure,'actual_thin_exit':status,'actual_Blender':0,'models':0,
      'attempted_labels':[name for name,_ in calls],**verdict})
    return int(not verdict['passed'])


def cold(root):
    plan = checked_plan(root)
    group = root/'preflight/natural_cold'
    group.mkdir(exist_ok=False)
    arms = {}
    for arm in ('A','B'):
        stdout,stderr = group/f'{arm}_CHILD_STDOUT.bin',group/f'{arm}_CHILD_STDERR.bin'
        args = [sys.executable,'-IB','-X','utf8',str(Path(__file__)),str(root),'cold-arm',arm]
        with stdout.open('xb') as out,stderr.open('xb') as err:
            try:
                result = subprocess.run(args,cwd=group,stdin=subprocess.DEVNULL,stdout=out,stderr=err,
                                        creationflags=old.NO_WINDOW,timeout=75)
                code=result.returncode
            except subprocess.TimeoutExpired:
                code=None
        record = group/arm/'RESULT.json'
        arms[arm] = (read(record)|{'result':pin(record)}) if record.is_file() else {'passed':False,'missing_result':True}
        arms[arm].update(exit=code,child_stdout=pin(stdout),child_stderr=pin(stderr))
    same = all(a['passed'] and a['exit']==0 for a in arms.values()) and (
          arms['A']['actual_tools']==arms['B']['actual_tools']==plan['prior_actual_catalogue'])
    write(root/COLD,{'batch':BATCH,'plan':pin(root/PLAN),'passed':same,'arms':arms,'same_actual_catalogue':same,
      'catalogue_delta_bytes':0 if same else None,'retained_transport':plan['retained_transport'],
      'no_Blender_or_model':True,'source':plan['source_for_cold']})
    return int(not same)


def admitted(root,label):
    plan = checked_plan(root)
    freeze = read(root/FREEZE)
    require(freeze['batch']==BATCH and freeze['order']==list(ORDER)
            and confirmed(freeze['natural_plan'])==(root/PLAN).resolve()
            and confirmed(freeze['natural_cold'])==(root/COLD).resolve()
            and confirmed(freeze['product_preflight'])==(root/QUALIFICATION).resolve()
            and freeze['transport_preflight']==plan['retained_transport'], 'unbound_component_frozen_launch')
    for record in [*freeze['inputs'],freeze['score_controls']]:
        confirmed(record)
    require(freeze['fixture']['blend']==plan['asset'] and freeze['fixture']['prompts']==plan['prompts']
            and read(root/QUALIFICATION)['passed'] is True and read(freeze['score_controls']['path'])['passed'] is True,
            'frozen_component_product_or_scorer_controls_not_accepted')
    gate = read(root/COLD)
    require(gate['passed'] is True and gate['plan']==pin(root/PLAN) and gate['same_actual_catalogue'] is True
            and gate['retained_transport']==plan['retained_transport'], 'current_shared_Thin_preflight_not_admitted')
    index = ORDER.index(label)
    for earlier in ORDER[:index]:
        require(read(root/'slots'/earlier/'closed.json')['safe_to_continue'] is True,
                'previous_component_slot_not_safe/'+earlier)
    require(all(not (root/'slots'/later).exists() for later in ORDER[index:]),'same_or_future_slot_already_used')
    require(plan['jobs'][label]['prompt']==plan['prompts'][label],'slot_prompt_binding_changed')
    arm = plan['jobs'][label]['arm']
    selected = gate['arms'][arm]
    confirmed(selected['result'])
    confirmed(selected['actual_catalogue_wire'])
    return {**arm_settings(plan,arm),'prompts':{label[-1]:plan['prompts'][label]}},selected


def run(root,label):
    old.BATCH = BATCH
    old.admitted = admitted
    return old.run(root,label)


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root',type=lambda path:Path(path).resolve(strict=True))
    parser.add_argument('phase',choices=('plan','cold','cold-arm','run'))
    parser.add_argument('label',nargs='?')
    args = parser.parse_args()
    if args.phase=='plan':
        write(args.root/PLAN,prepare(args.root))
    elif args.phase=='cold':
        raise SystemExit(cold(args.root))
    elif args.phase=='cold-arm':
        require(args.label in ('A','B'),'missing_cold_arm')
        raise SystemExit(cold_arm(args.root,args.label))
    else:
        require(args.label in ORDER,'missing_formal_slot')
        raise SystemExit(run(args.root,args.label))
