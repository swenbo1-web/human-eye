"""Replay the original sampled frame and a retained-frame hit through installed MCP."""

import argparse
import base64
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from runpy import run_path
import subprocess
import sys
from types import SimpleNamespace
from zipfile import ZipFile


NS = Path(__file__).resolve().parents[1]
V = NS.parent
RUN = Path('D:/he_perf050_source_scope_rank_transfer_recovery_001')
SLOT = RUN/'slots/P1'
ARCHIVE_SHA = 'fef71aa0e06b589e386783f800ee67f507cc10b8a78bcd69de29d3b02f93810c'
BASE = V/'m1_source_region_sampled_image_path_001/install/PRODUCT_RUN_BINDING.json'
CANDIDATE = NS/'install/PRODUCT_RUN_BINDING.json'
REQ = SLOT/'mcp/rpc_05/TX.bin'
RX = SLOT/'mcp/rpc_05/RX.bin'
SOURCE = SLOT/'product_full/call_002/SERVICE_RESULT.json'
IMAGE_SHA = '815eed92ff73118535035ce7f9faf4bfbc798cae0f527ad0c3c7ecd624c4546f'
ORIGINAL_TEXT_BYTES = 7879


def read(path):
    return json.loads(path.read_bytes())


def digest(raw):
    return sha256(raw).hexdigest()


def pin(path):
    data = path.read_bytes()
    return {'path':str(path),'bytes':len(data),'sha256':digest(data)}


def require(value, reason):
    if not value:
        raise ValueError(reason)


def frozen_media():
    frame, = read(SOURCE)['frames']
    png, arrays = (Path(frame[key]) for key in ('image_path','arrays_path'))
    files = (REQ,RX,SOURCE,png,arrays,SLOT/'product_calls/call_001/RESPONSE.json',SLOT/'owner/tool_06/RESPONSE.json',
        SLOT/'consumer/stdout.raw.bin',SLOT/'consumer/PUBLIC_FINAL.txt',SLOT/'SLOT_RESULT.json')
    archive = RUN/'ORIGINAL_RUNTIME.zip'
    require(pin(archive)['sha256']==ARCHIVE_SHA,'original_archive_binding_changed')
    with ZipFile(archive) as original:
        require(all(path.read_bytes()==original.read(path.relative_to(RUN).as_posix()) for path in files),'original_runtime_members_changed')
    initial = read(RX)['result']['content']
    next_result = read(SLOT/'owner/tool_06/RESPONSE.json')['result']['content']
    ordinary = json.loads(next_result[0]['text'].split('\n',1)[1])
    stdout = [json.loads(line) for line in (SLOT/'consumer/stdout.raw.bin').read_bytes().splitlines() if line.strip()]
    final, = [row['item']['text'].encode() for row in stdout if row.get('type')=='item.completed'
              and row.get('item',{}).get('type')=='agent_message' and row['item'].get('id')=='item_11']
    raw = png.read_bytes()
    require(len(raw)==4015 and digest(raw)==IMAGE_SHA and base64.b64decode(initial[1]['data'],validate=True)==raw
        and next_result[1]==initial[1] and ordinary['image_sha256']==IMAGE_SHA
        and ordinary['local_image_path']==png.as_posix() and png.resolve(strict=True)==png
        and png.as_posix() in final.decode() and final==(SLOT/'consumer/PUBLIC_FINAL.txt').read_bytes()
        and read(SLOT/'SLOT_RESULT.json')['closure_verification']['passed'] is True
        and len(initial[0]['text'].encode())==ORIGINAL_TEXT_BYTES and 'local_image_path' not in json.loads(initial[0]['text'])['images'][0],
        'raw_inner_outer_final_and_closed_PNG_not_the_same')
    return raw, png, [pin(path) for path in (*files,archive)]


def worker(binding_path, notes):
    binding = read(binding_path)
    sys.path[:0] = [binding['install_root'],binding['dependency_root']]
    from human_eye_plugin import live_spatial_mcp as mcp, source_region
    from human_eye_plugin.live_service import LiveSpatialService
    from human_eye_plugin.read_context import ReadContext
    from human_eye_plugin.runtime_identity import runtime_identity

    require(runtime_identity()['source_sha256']==binding['source_sha256']
            and Path(mcp.__file__).resolve().is_relative_to(binding['install_root']), 'replay_wrong_installed_product')
    value = read(SOURCE)
    frame, = value['frames']
    original_directory = Path(frame['image_path']).parent
    args = read(REQ)['params']['arguments']

    class ReplayedSourceRegion:
        _source_region_sample_directory = getattr(LiveSpatialService,'_source_region_sample_directory',None)
        _source_region_sample_path = getattr(LiveSpatialService,'_source_region_sample_path',None)

        def __init__(self):
            self._read_context = ReadContext()
            self.state_path = SLOT/'product_state.json'
            self.temp = []
            self.calls = []
            self.budget = []
            self.closed = False
            # Restore the producer's pre-service binding, then the archived task fields on return.
            original = {k:deepcopy(v) for k,v in value.items() if k not in ('session_id','task_result','request_trace')}
            for key in ('runtime_source_sha256','source_status','disk_status','source_check_scope'):
                original['binding'].pop(key,None)
            self.prepared = SimpleNamespace(binding=original['binding'],region_ref=original['region_ref'],
                 images=SimpleNamespace(output_directory=original_directory),observation=original)
            ref = self.prepared.region_ref['region_id']
            self._read_context.activate(self.prepared.binding,'source_region')
            self._read_context.prepared('source_regions',lambda:{'regions':{ref:self.prepared}})

        def observe(self, _session, *, query, include_image, **_ignore):
            require(query==args['query'] and include_image is True,'archived_replay_argument_changed')
            self.calls.append('cold' if not self.calls else 'retained_frame_hit')
            if len(self.calls)==1:
                return deepcopy(value)
            if len(self.calls)==3:
                self._read_context.activate({'capture_state':{**value['binding']['capture_state'],
                    'revision':value['binding']['capture_state']['revision']+1}},'source_region')
            returned = source_region.observe_region(self.prepared,None,include_image=True)
            require(returned['frames']==value['frames'] and returned['work']['raster_attempts']==0
                    and returned['work']['frame_reuses']==1
                    and returned['facts']['visibility']==value['facts']['visibility'],'actual_retained_frame_branch_changed')
            return {**returned,'task_result':deepcopy(value['task_result']), 'session_id':value['session_id'],
                    'binding':deepcopy(value['binding'])}

        def record_event(self, event, **data):
            if event=='source_region_mcp_content':
                self.temp.append(data['image_delivery'])

        def _check_request_budget(self, phase, *, publication=False):
            self.budget.append((phase,publication))

        def close(self):
            self.closed=True

    service = ReplayedSourceRegion()
    mcp._configure_utf8_stdio()
    mcp.run_stdio_mcp_server(service)
    expected = [('before_task_publication',False),('before_stdio_write',True)]*3
    require(service.closed and service.budget==expected and len(service.temp)==len(service.calls)==3,
            'real_stdio_publication_or_EOF_changed')
    notes.write_bytes((json.dumps({'calls':service.calls,'budget':service.budget,'audits':service.temp,
                    'closed':service.closed,'installed_source':binding['source_sha256']},indent=2)+'\n').encode())


def profile(reply):
    budget = run_path(str(V/'m4_cross_scale_live_qualification_001/checks/delivery.py'))['budget_helpers']
    helpers, policy = budget()
    require((policy['MCP_bytes'],policy['history_approximate_tokens'])==(12000,3000),'wrong_fixed_CLI_budget')
    original = reply['result']
    full = original['content'][0]['text']
    rows=[]
    for secs in ('0.0000','10.0000','100.0000'):
        header = helpers['model_items'](original,secs)
        tool = helpers['truncate_items'](header,12000)
        history = helpers['truncate_items'](tool,3000,token_mode=True)
        for stage, retained in (('tool',tool),('history',history)):
            text = [row['text'] for row in retained if row['type']=='input_text'][1]
            images = [digest(base64.b64decode(row['image_url'].split(',',1)[1],validate=True))
                      for row in retained if row['type']=='input_image']
            require(text==full and images==[IMAGE_SHA],'fixed_CLI_body_or_original_PNG_changed')
            rows.append({'head_bytes':len(header[0]['text'].encode()),'stage':stage,'text_sha256':digest(text.encode()),
                        'text_bytes':len(text.encode()),'native_image_sha256':images[0],'passed':True})
    return rows


def run(output):
    png, path, files = frozen_media()
    output.mkdir(parents=True,exist_ok=False)
    cold = REQ.read_bytes()
    registry = {'jsonrpc':'2.0','id':'list','method':'tools/list'}
    request = read(REQ)
    commands = [cold.rstrip(b'\r\n')]+[json.dumps({**request,'id':key}).encode() for key in ('warm','stale')]
    payload = b'\n'.join([json.dumps(registry).encode(),*commands])+b'\n'
    (output/'INPUT.bin').write_bytes(payload)
    result = {}
    for arm, binding in (('baseline',BASE),('candidate',CANDIDATE)):
        note = output/f'{arm}_AUDIT.json'
        process = subprocess.run([sys.executable,'-IB',str(Path(__file__).resolve()),'--worker',str(binding),
             '--notes',str(note)],input=payload,capture_output=True,timeout=60)
        process.check_returncode()
        require(not process.stderr,'unexpected_stderr_in_installed_replay')
        (output/f'{arm}_STDOUT.bin').write_bytes(process.stdout)
        lines = process.stdout.splitlines(keepends=True)
        replies = [json.loads(line) for line in lines]
        require([row['id'] for row in replies]==['list',request['id'],'warm','stale'],'real_stdio_correlation_changed')
        for label,line in zip(('cold','warm','stale'),lines[1:],strict=True):
            (output/f'{arm.upper()}_{label.upper()}_RX.bin').write_bytes(line)
        result[arm]={'list_bytes_sha256':digest(lines[0]),'replies':replies[1:],'audit':read(note)}
    a,b=(result[k] for k in ('baseline','candidate'))
    historical = read(RX)
    restored = a['replies'][0]
    # The archive sorts keys in its producer JSON. Preserve values and the raw PNG,
    # then compare byte order A/B from the same restored producer.
    restored_body = json.loads(restored['result']['content'][0]['text'])
    original_path = restored_body['images'][0].pop('local_image_path',None)
    require(restored['id']==historical['id'] and restored['result']['isError']==historical['result']['isError']
            and restored['result']['content'][1:]==historical['result']['content'][1:]
            and original_path==path.as_posix() and restored_body==json.loads(historical['result']['content'][0]['text'])
            and a['list_bytes_sha256']==b['list_bytes_sha256'],'old_body_or_tools_list_changed')
    profiles={}
    for idx,label in enumerate(('cold','warm','stale')):
        baseline,candidate=(result[arm]['replies'][idx]['result'] for arm in ('baseline','candidate'))
        candidate_path = json.loads(candidate['content'][0]['text'])['images'][0].get('local_image_path')
        require(candidate_path==(path.as_posix() if label!='stale' else None)
                and candidate==baseline
                and (output/f'CANDIDATE_{label.upper()}_RX.bin').read_bytes()==(output/f'BASELINE_{label.upper()}_RX.bin').read_bytes()
                and base64.b64decode(candidate['content'][1]['data'],validate=True)==png,
                'retained_producer_changed_actual_public_bytes/'+label)
        require(b['audit']['audits'][idx]['frames'][0]['PNG_bytes_read']==4015
                and b['audit']['audits'][idx]['native_blocks_constructed']==1,'actual_native_read_count_changed')
        if label!='stale':
            cid=b['replies'][idx]
            profiles[label]={'baseline_text_bytes':len(baseline['content'][0]['text'].encode()),
                        'candidate_text_bytes':len(candidate['content'][0]['text'].encode()),'same_original_PNG':True,
                        'path_from_historical_call_6':candidate_path,'fixed_stages':profile(cid)}
    require((profiles['cold']['baseline_text_bytes'],profiles['cold']['candidate_text_bytes'])==(8062,8062),'unexpected_cold_body_size')
    values={'passed':True,'product':[read(p)['preparation_git'] for p in (BASE,CANDIDATE)],
            'original_source_pins':files,'real_installed_MCP_reply_cases':3,
            'fixed_CLI_stages_passed':sum(len(row['fixed_stages']) for row in profiles.values()),
            'A_B_cold_and_hot_wires_exact':True,'stale_generation_reply_same_bytes':True,
            'live_Blender':0,'model':0,'new_rasters':0,'profiles':profiles,
            'stdio_audits':{key:row['audit'] for key,row in result.items()},'actual_wire_files':[pin(f) for f in output.iterdir()]}
    (output/'POSITIVES.json').write_bytes((json.dumps(values,indent=2)+'\n').encode())
    print(json.dumps({'passed':True,'fixed_CLI_stages':values['fixed_CLI_stages_passed'],'report':str(output/'POSITIVES.json')}))


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path)
    parser.add_argument('--worker',type=Path)
    parser.add_argument('--notes',type=Path)
    args=parser.parse_args()
    require(sys.flags.isolated and sys.dont_write_bytecode,'use_pinned_interpreter_I_B')
    if args.worker:
        worker(args.worker,args.notes)
    else:
        run(args.output)
