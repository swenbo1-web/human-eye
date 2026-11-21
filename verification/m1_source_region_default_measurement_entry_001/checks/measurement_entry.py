"""Compare reference-backed default, brief and full calls on the installed public stdio entry."""

import argparse
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from runpy import run_path
import subprocess
import sys
from zipfile import ZipFile


NS = Path(__file__).resolve().parents[1]
V = NS.parent
RUN = Path('D:/he_perf050_source_scope_rank_transfer_recovery_001')
SLOT = RUN/'slots/P1'
REQ = SLOT/'mcp/rpc_04/TX.bin'
ORIGINAL = SLOT/'mcp/rpc_04/RX.bin'
PRODUCER = SLOT/'product_full/call_001/SERVICE_RESULT.json'
BASE = V/'m1_sampled_image_path_producer_reuse_001/install/PRODUCT_RUN_BINDING.json'
NEW = NS/'install/PRODUCT_RUN_BINDING.json'
MEASUREMENT_BYTES = {'full':39717,'brief':7042,'default':7042}
OLD_SENTENCE = 'Brief and full return the source scope, display participation, distance, witness and native image references.'
NEW_SENTENCE = ('Default brief includes distance, nearest points with source faces, and region_ref. '
                'Use response_detail=full for face mappings and diagnostics.')


def read(path):
    return json.loads(path.read_bytes())


def pin(path):
    raw = path.read_bytes()
    return {'path':str(path),'bytes':len(raw),'sha256':sha256(raw).hexdigest()}


def require(value, reason):
    if not value:
        raise ValueError(reason)


def write(path, data):
    path.write_bytes((json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode())


def public_body(reply):
    result = reply['result']
    require(result['isError'] is False and len(result['content'])==1 and result['content'][0]['type']=='text',
            'expected_successful_no_image_rpc')
    return result['content'][0]['text']


def original_files():
    outer = SLOT/'owner/tool_01/RESPONSE.json'
    stdout = SLOT/'consumer/stdout.raw.bin'
    files = (REQ,ORIGINAL,PRODUCER,outer,stdout,SLOT/'product_calls/call_001/REQUEST.json')
    archive = RUN/'ORIGINAL_RUNTIME.zip'
    require(pin(archive)['sha256']=='fef71aa0e06b589e386783f800ee67f507cc10b8a78bcd69de29d3b02f93810c','historical_archive_changed')
    with ZipFile(archive) as z:
        require(all(path.read_bytes()==z.read(path.relative_to(RUN).as_posix()) for path in files),'historical_member_bytes_changed')
    history = [json.loads(line) for line in stdout.read_bytes().splitlines() if line.strip()]
    item, = [entry['item'] for entry in history if entry.get('type')=='item.completed'
             and entry.get('item',{}).get('id')=='item_3' and entry['item'].get('type')=='mcp_tool_call']
    body = public_body(read(ORIGINAL))
    require(public_body(read(outer))==body and item['result']['content'][0]['text']==body
            and item['arguments']==read(REQ)['params']['arguments'], 'original_CLI_content_not_the_same_as_stdio')
    raw = json.loads(body)
    binding, task = raw['binding'], raw['task_result']
    compact = lambda value: json.dumps(value,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode()
    size = len(compact(binding))
    require(compact(binding)==compact(task['binding']) and size==16230 and body.count(compact(binding).decode())==2
            and len(body.encode())==39717 and raw['region_ref']==task['region_ref'], 'original_duplicate_binding_changed')
    return raw, [pin(path) for path in (*files,archive)], {'text_bytes':len(body.encode()),'duplicate_binding_bytes_each':size,
        'duplicate_binding_instances':2,'outer_and_CLI_original_body_exact':True,'actual_CLI_item':item['id'],
        'actual_provider_context_observed':None}


def worker(binding_path, notes):
    binding = read(binding_path)
    sys.path[:0] = [binding['install_root'],binding['dependency_root']]
    from human_eye_plugin import live_spatial_mcp as mcp
    from human_eye_plugin.runtime_identity import runtime_identity

    require(runtime_identity()['source_sha256']==binding['source_sha256']
        and Path(mcp.__file__).resolve().is_relative_to(binding['install_root']), 'wrong_installed_source')
    original = read(PRODUCER)
    arguments = read(REQ)['params']['arguments']

    class SavedMeasurement:
        def __init__(self):
            self.state_path = SLOT/'product_state.json'
            self.budget = []
            self.observations = []
            self.closed = False

        def observe(self, _session, *, query, include_image, **_other):
            require(query==arguments['query'] and include_image is False and original['frames']==[],
                    'public_dispatch_changed_query_or_image_setting')
            self.observations.append(deepcopy(query))
            return deepcopy(original)

        def _check_request_budget(self, phase, *, publication=False):
            self.budget.append((phase,publication))

        def close(self):
            self.closed = True

    service = SavedMeasurement()
    mcp._configure_utf8_stdio()
    mcp.run_stdio_mcp_server(service)
    lifecycle=[('before_task_publication',False),('before_stdio_write',True)]*3
    require(service.closed and service.budget==lifecycle and len(service.observations)==3,'unexpected_stdio_publish_or_EOF')
    write(notes,{'passed':True,'runtime_source':binding['source_sha256'],'phase_events':service.budget,
                 'observe_calls':len(service.observations),'EOF_closed':service.closed})


def component_profile(packets):
    helpers, policy = run_path(str(V/'m4_cross_scale_live_qualification_001/checks/delivery.py'))['budget_helpers']()
    require((policy['MCP_bytes'],policy['history_approximate_tokens'])==(12000,3000),'wrong_registered_fixed_budget')
    sys.path.insert(0,str(V/'m5_global_observe_measure_qualification_001/checks'))
    omitted_paths = run_path(str(V/'m5_global_observe_measure_qualification_001/checks/live_wire.py'))['omitted_paths']
    stages = {}
    for label, reply in packets.items():
        text = public_body(reply)
        stages[label] = []
        for seconds in ('0.0000','10.0000','100.0000'):
            items = helpers['model_items'](reply['result'],seconds)
            first = helpers['truncate_items'](items,12000)
            second = helpers['truncate_items'](first,3000,token_mode=True)
            head = len(items[0]['text'].encode())
            for phase, delivered in (('tool',first),('history',second)):
                retained = [part['text'] for part in delivered if part['type']=='input_text'][1]
                lost = omitted_paths(text,retained)
                relevant = [row for row in lost if row[:2] in (('task_result','facts'),('task_result','source_mapping'))
                            or row and row[0]=='region_ref']
                if label in ('default','brief'):
                    require(retained==text and not relevant,'normal_brief_fixed_budget_lost_required_data')
                elif label=='historical_full':
                    require(relevant and ('task_result','facts','surface_proximity','value','distance_m') in relevant
                            and any(row[0]=='region_ref' for row in relevant),'historical_full_fixed_budget_loss_changed')
                stages[label].append({'head_bytes':head,'phase':phase,'body_bytes':len(retained.encode()),
                    'retained_text_sha256':sha256(retained.encode()).hexdigest(),
                    'body_fully_retained':retained==text,'lost_relevant_leaves':relevant})
    return stages


def run(out):
    original, sources, historical = original_files()
    out.mkdir(parents=True,exist_ok=False)
    req = read(REQ)
    def detail(key):
        request = deepcopy(req)
        request['id'] = key
        if key=='brief':
            request['params']['arguments']['response_detail']='brief'
        else:
            request['params']['arguments'].pop('response_detail')
        return json.dumps(request,ensure_ascii=False).encode()

    requests = [json.dumps({'jsonrpc':'2.0','id':'list','method':'tools/list'}).encode(),REQ.read_bytes().rstrip(b'\r\n'),
                detail('brief'),detail('default')]
    tx=b'\n'.join(requests)+b'\n'
    (out/'TX.bin').write_bytes(tx)
    arms={}
    for label, binding in (('A',BASE),('B',NEW)):
        receipt = out/f'{label}_LIFECYCLE.json'
        process = subprocess.run([sys.executable,'-IB',str(Path(__file__).resolve()),'--worker',str(binding),'--notes',str(receipt)],
            input=tx,capture_output=True,timeout=60)
        process.check_returncode()
        require(not process.stderr,'unexpected_installed_endpoint_stderr')
        lines=process.stdout.splitlines(keepends=True)
        replies=[json.loads(line) for line in lines]
        require([obj['id'] for obj in replies]==['list',req['id'],'brief','default'],'installed_endpoint_response_id_changed')
        for key,line in zip(('TOOLS','FULL','BRIEF','DEFAULT'),lines,strict=True):
            (out/f'{label}_{key}_RX.bin').write_bytes(line)
        arms[label]={'tools':replies[0]['result']['tools'],'full':replies[1],'brief':replies[2],'default':replies[3]}
    left,right = (arms[label] for label in ('A','B'))
    tool_name='human_eye_scene_observe'
    tool, = [row for row in left['tools'] if row['name']==tool_name]
    expected=[{**row,'description':row['description'].replace(OLD_SENTENCE,NEW_SENTENCE)}
                if row['name']==tool_name else row for row in left['tools']]
    require(len(left['tools'])==5 and tool['description'].count(OLD_SENTENCE)==1 and right['tools']==expected,
            'public_tools_list_diff_outside_registered_sentence')
    for key,size in MEASUREMENT_BYTES.items():
        expected_wire=(out/f'A_{key.upper()}_RX.bin').read_bytes()
        require(expected_wire==(out/f'B_{key.upper()}_RX.bin').read_bytes() and len(public_body(right[key]).encode())==size,
                'fixed_measurement_reply_changed/'+key)
    require(public_body(right['brief'])==public_body(right['default']) and json.loads(public_body(right['full']))==original,
            'default_brief_or_original_full_changed')
    normal=json.loads(public_body(right['default']))
    task=normal['task_result']
    require(normal['region_ref']==original['region_ref'] and task['measurement_scope']==original['task_result']['measurement_scope']
            and task['facts']==original['task_result']['facts'] and task['source_mapping']['nearest_witness']==original['task_result']['source_mapping']['nearest_witness']
            and normal['observation_status']=='image_not_requested' and normal['images']==[], 'default_lost_required_measurement_reference_or_status')
    stages=component_profile({**{k:right[k] for k in ('brief','default','full')},'historical_full':read(ORIGINAL)})
    after_tool=next(row for row in right['tools'] if row['name']==tool_name)
    receipt={'passed':True,'actual_installations':{arm:pin(path) for arm,path in (('A',BASE),('B',NEW))},
             'historical':historical,'source_pins':sources,'actual_tool_count':len(left['tools']),
             'only_directory_delta':tool_name+'.description','description_bytes':{'A':len(tool['description'].encode()),'B':len(after_tool['description'].encode())},
             'stdio_requests':6,'raw_A_B_identical_measurement_cases':3,'actual_text_UTF8_bytes':MEASUREMENT_BYTES,
             'explicit_brief_matches_default_in_body_bytes':True,'full_semantics_equal_to_historical_original':True,
             'actual_default_measurement':{'task_result':task,'region_ref':normal['region_ref'],'status':normal['observation_status']},
             'fixed_CLI_stages':stages,'brief_or_default_stages_retained':12,'original_full_required_loss_stages':6,
             'new_Blender':0,'new_rasters':0,'new_model':0,'actual_authorship_or_billing_measured':False,
             'artifacts':[pin(path) for path in sorted(out.iterdir())]}
    write(out/'MEASUREMENT_ENTRY.json',receipt)
    print(json.dumps({'passed':True,'bytes':MEASUREMENT_BYTES,'description':receipt['description_bytes'],'output':str(out)}))


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worker',type=Path)
    parser.add_argument('--notes',type=Path)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    require(sys.flags.isolated and sys.dont_write_bytecode,'use_pinned_implementation_I_B')
    if args.worker:
        worker(args.worker,args.notes)
    else:
        run(args.output)
