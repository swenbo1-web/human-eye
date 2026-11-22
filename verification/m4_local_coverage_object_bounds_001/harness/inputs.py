"""Verify the two fixed real captures, their original requests and raster artifacts."""

import ast
import hashlib
import json
from pathlib import Path
import re
import subprocess
from zipfile import ZipFile


HERE = Path(__file__).resolve().parent
V = HERE.parents[1]
REPO = V.parent
RUN = Path('D:/he_m4_local_coverage_object_bounds_001')
BASE = V/'m3_whole_object_rounded_witness_compat_001/install/PRODUCT_RUN_BINDING.json'
PRIOR = V/'m4_dense_sweep_integrated_native_pilot_001'
SEAL = V/'m5_harness_recovery_001'
CATALOGUE = PRIOR/'inputs/EVIDENCE_TOOLS_SCHEMA.json'
BASE_GIT = 'cee6fe78a65c1534361228641743aa83d6d72b61'
FIXTURES = {
    'main': ('5b7910c1486071abae84466cb0b51230dc111aa0','m4_dense_sweep_integrated_native_startup_001',
             'RAW_INDEX.json','runtime/','3cdb270694e6d7096dfd3554b6a19edea5a3891a1ee76d35d204e8713c916a06',
             (20,3502,6160),('global','local','local')),
    'holdout': ('39fd39cd','m4_cross_scale_assembly_transfer_001',
                'RUNTIME_INDEX.json','','d0d2294f5e5fe006d2f3f23deaf34290dba696b39424585b7cd5e4494d8ffa90',
                (28,416,744),('global','global','local')),
}


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def read(path):
    return json.loads(Path(path).read_bytes())


def write(path, value):
    with Path(path).open('xb') as out:
        out.write((json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2)+'\n').encode())


def digest(raw):
    return {'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}


def pin(path):
    p = Path(path).resolve(strict=True)
    return {'path':str(p), **digest(p.read_bytes())}


def sealed_inputs(name):
    commit,namespace,index_name,prefix,source_sha,sizes,scope_roster = FIXTURES[name]
    original = Path('D:/')/('he_'+namespace)
    slot = original/'slots/P1'
    index_path = V/namespace/index_name
    reference = commit+':'+index_path.relative_to(REPO).as_posix()
    require(index_path.read_bytes()==subprocess.check_output(['git','show',reference],cwd=REPO),
            'fixed_original_index_differs_from_committed_Git/'+name)
    index = read(index_path)
    info = index['archive']
    archive = V/namespace/info['name'] if prefix else Path(info['path'])
    require(digest(archive.read_bytes())=={k:info[k] for k in ('bytes','sha256')},'archive_sha_changed/'+name)
    roster = index['members'] if prefix else {item['path']:{k:item[k] for k in ('bytes','sha256')}
                                                 for item in index['files']}
    pins = [pin(index_path),pin(archive)]

    def member(path):
        path = Path(path).resolve(strict=True)
        require(path.is_relative_to(slot.resolve()),'fixed_original_member_outside_slot')
        name_in_zip = prefix+path.relative_to(original.resolve()).as_posix()
        raw = path.read_bytes()
        identity = digest(raw)
        require(roster[name_in_zip]==identity and zipped.read(name_in_zip)==raw,
                'archived_original_member_changed/'+name_in_zip)
        pins.append({'path':str(path), **identity})
        return raw

    with ZipFile(archive) as zipped:
        terminal_path = slot/'TERMINAL_SOURCE.json'
        terminal_raw = member(terminal_path)
        terminal = json.loads(terminal_raw)
        rows = terminal['objects']
        dimensions = (len(rows),sum(len(row['evaluated']['vertices']) for row in rows),
                      sum(len(row['evaluated']['triangles']) for row in rows))
        require(digest(terminal_raw)['sha256']==source_sha and dimensions==sizes,
                'fixed_terminal_source_or_roster_changed/'+name)
        closing = json.loads(member(slot/'SLOT_RESULT.json'))
        publication = json.loads(member(slot/'SLOT_PUBLICATION.json'))
        require(closing['closure_verification']['passed'] and closing['independent_before_after']['passed']
                and publication['result_sha256']==next(row['sha256'] for row in pins
                                                         if row['path']==str((slot/'SLOT_RESULT.json').resolve())),
                'fixed_original_source_not_independently_closed/'+name)
        deltas, transport = [], []
        for index_key, resources in (('002',sizes[0]),('003',0)):
            folder = slot/'native/WIRE'/index_key
            tx,rx = [member(folder/key) for key in ('REQUEST.bin','RESPONSE.bin')]
            request, reply = json.loads(tx), json.loads(rx)
            encoded = re.search(r'_request = _json.loads\((.+)\)\n', request['params']['code'])
            require(encoded is not None,'original_transport_request_not_decodable')
            native = json.loads(ast.literal_eval(encoded.group(1)))
            lines = [line for line in reply['result']['result'].splitlines()
                     if line.startswith('HUMAN_EYE_BLENDER_MCP:')]
            require(reply['status']=='success' and len(lines)==1,'fixed_original_transport_response_changed')
            packet = json.loads(lines[0].split(':',1)[1])
            current = packet['result']
            require(packet['id']==native['id'] and native['command']=='capture' and not native['params']
                    and current['schema']=='human-eye-scene-delta-v1' and len(current['resources'])==resources,
                    'fixed_original_full_or_incremental_capture_changed')
            deltas.append(current)
            transport.append({'wire':index_key,'TX':digest(tx),'RX':digest(rx),'resource_count':resources})
        require(deltas[0]['capture']==deltas[1]['capture']
                and deltas[0]['live_resources']==deltas[1]['live_resources'],'same_generation_source_delta_changed')
        calls = [json.loads(member(slot/'product_calls'/f'call_{i:03d}'/'REQUEST.json'))
                 for i in (1,2)]
        for i in (1,2):
            member(slot/'product_calls'/f'call_{i:03d}'/'RESPONSE.json')
        producer = json.loads(member(slot/'product_full/call_001/SERVICE_RESULT.json'))
        member(slot/'product_full/call_002/SERVICE_RESULT.json')
        require(calls[0]['params']['arguments']['query']['mode']=='active_observation'
                and calls[0]['params']['arguments']['include_image'] is True
                and calls[1]['params']['arguments']['include_image'] is False
                and [f['scope_id'].split('_',1)[0] for f in producer['constructed_frames']]==list(scope_roster),
                'fixed_discovery_and_no_image_request_or_original_raster_roster_changed')
        frames = []
        for frame in producer['constructed_frames']:
            png = digest(member(Path(frame['image_path'])))
            arrays = digest(member(Path(frame['arrays_path'])))
            require(png['sha256']==frame['image_sha256'] and arrays['sha256']==frame['arrays_sha256'],
                    'sealed_original_frame_hash_changed')
            frames.append({'scope_id':frame['scope_id'], 'view_name':frame['view_name'],'png':png,'arrays':arrays})
    binding = producer['binding']
    require(all(value['capture']['capture_state']==binding['capture_state']
                and value['capture']['revision']==binding['scene_revision'] for value in deltas),
            'frozen_original_producer_detached_from_native_capture')
    return {'name':name,'source_dimensions':list(sizes),'original_slot':str(slot),'terminal':terminal,
            'frames':frames,'deltas':deltas,'transport':transport,'calls':calls,
            'source_pins':sorted(pins,key=lambda value:value['path'])}
