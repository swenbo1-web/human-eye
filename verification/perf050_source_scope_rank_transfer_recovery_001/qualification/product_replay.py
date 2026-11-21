"""Recompute four public MCP replies with the fixed install and archived Blender source."""

import argparse
import base64
from copy import deepcopy
from hashlib import sha256
from io import StringIO
import json
from pathlib import Path
from runpy import run_path
import sys


ROOT = Path(__file__).resolve().parents[3]
V = ROOT/'verification'
OLD = V/'m4_m5_source_region_001'
BINDING = V/'m1_joint_full_task_tail_scope_001/install/PRODUCT_RUN_BINDING.json'
SOURCE = Path('D:/he_m4_m5_source_region_001/sessions/state')
DISPLAY_RECEIPT = V/'perf050_source_scope_rank_transfer_001/evidence/QN_TERMINAL_SOURCE.json'
TRUTH = V/'perf050_source_scope_rank_transfer_001/checks/truth.py'
TARGET = 'Obj_07'
REFERENCES = ('Obj_05','Obj_08')


def read(path):
    return json.loads(path.read_bytes())


def pin(path):
    path = Path(path).resolve(strict=True)
    raw = path.read_bytes()
    return {'path':str(path),'sha256':sha256(raw).hexdigest(),'bytes':len(raw)}


def write(path, value):
    path.write_bytes((json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode())


def require(value, reason):
    if not value:
        raise ValueError(reason)


def captured_source():
    loader = run_path(str(OLD/'oracle/check_saved.py'))
    archived_binding = read(OLD/'R1_RUN_BINDING.json')
    archive_index = {row['relative']:row for row in read(OLD/'RUNTIME_ARCHIVE.json')['files']}
    original_files = list((SOURCE/'native/WIRE').glob('*/*.bin'))
    producer_path = SOURCE/'product_full/call_003/SERVICE_RESULT.json'
    original_files.append(producer_path)
    for path in original_files:
        name = 'sessions/state/'+path.relative_to(SOURCE).as_posix()
        row = archive_index[name]
        require(pin(path)['sha256'] == row['sha256'] == pin(OLD/row['copy'])['sha256'], 'archived_capture_pin/'+name)
    audit = loader['Audit']()
    captures, _ = loader['decode_captures'](SOURCE,archived_binding,audit)
    producer = read(producer_path)
    capture = loader['current_capture'](captures,producer['binding'],audit)
    loader['compare_geometry'](capture,False,audit)
    return capture, producer, original_files


def main(output):
    install = read(BINDING)
    sys.path[:0] = [install['install_root'],install['dependency_root']]
    from human_eye_plugin import live_spatial_mcp as mcp
    from human_eye_plugin.live_service import LiveSpatialService
    from human_eye_plugin.active_observation import fingerprint

    capture, historic, inputs = captured_source()
    require(Path(mcp.__file__).resolve().is_relative_to(Path(install['install_root'])), 'wrong_runtime_source')
    oracle = run_path(str(TRUTH))
    meshes, truth_pins = oracle['frozen_meshes']()
    independent_membership = run_path(str(oracle['MEMBERSHIP']))
    truth = oracle['analytical_truth'](meshes,truth_pins,independent_membership)
    display = read(DISPLAY_RECEIPT)
    oracle['verifies_geometry'](display,meshes)
    oracle['verifies_capture'](capture,display)
    snapshot = {'schema':'blender-viewport-display-v1','scope':'active_view_layer','status':'captured',
        'view_layer':{'name':display['source']['view_layer'],'instance_id':display['source']['view_layer_id']},
        'objects':sorted([{'host_id':row['object_id'],'instance_id':row['instance_id'],'visible_get':row['visible_get'],
                           **{name:row['display'][name] for name in ('hide_get','hide_viewport','hide_render')}}
                          for row in display['objects']],key=lambda row:row['host_id'])}
    snapshot['sha256'] = fingerprint(snapshot)
    capture['display_snapshot'] = snapshot
    inputs.append(DISPLAY_RECEIPT)
    output.mkdir(parents=True,exist_ok=True)
    replies = output/'public'
    replies.mkdir()
    config_path = output/'CONFIG.json'
    write(config_path,{'schema_version':'1.0','enabled':True,'observe_on_prompt':False,
        'project_root':install['install_root'],'state_file':str(output/'product_state.json'),
        'audit_file':str(output/'product_audit.jsonl'),'request_budget_s':30,
        'expected_identity':{'source_sha256':install['source_sha256']}})

    class ArchivedHost:
        def capture_scene(self):
            return deepcopy(capture)

        def capture_task_scene(self, selectors):
            scene = deepcopy(capture)
            by_name = {mesh['name']:mesh for mesh in scene['meshes']}
            selected = [by_name[row['name']] for row in selectors]
            ids = {item['object_id'] for item in selected}
            scene['capture_scope'] = 'selected_objects'
            scene.pop('host_execution',None)
            scene.pop('display_snapshot',None)
            identity = scene['host_identity']
            identity['capture_scope'] = 'selected_objects'
            identity['object_instances'] = {k:v for k,v in identity['object_instances'].items() if k in ids}
            scene['capture_state']['selection_key'] = fingerprint(selectors)
            scene['task_selection'] = {'selectors':deepcopy(selectors),
                'bindings':[{'object_id':item['object_id'],'name':item['name']} for item in selected],
                'pair_reason':None,'candidate_count':len(scene['meshes'])}
            scene['meshes'] = selected
            return scene

    class RecordingService(LiveSpatialService):
        def __init__(self):
            super().__init__(config_path,host=ArchivedHost())
            self.producers = []
            self.closed_by_stdio = False

        def observe(self, *args, **kwargs):
            result = super().observe(*args,**kwargs)
            self.producers.append(deepcopy(result))
            return result

        def close(self):
            self.closed_by_stdio = True

    service = RecordingService()
    requests, labels = [], []
    for scope in ('selected','whole'):
        for reference in REFERENCES:
            if scope == 'selected':
                query = {'mode':'source_region','reference':{'name':reference},'requested_facts':['surface_proximity'],
                         'region':{'object':{'name':TARGET},'source_triangle_indices':[0,1,2,3]}}
            else:
                query = {'mode':'task','objects':[{'name':TARGET},{'name':reference}],'requested_facts':['surface_proximity']}
            label = f'{scope}_{reference}'
            requests.append({'jsonrpc':'2.0','id':'observe-'+str(len(requests)+1),'method':'tools/call',
                 'params':{'name':'human_eye_scene_observe','arguments':{'include_image':label == 'selected_Obj_05',
                     'query':query,'response_detail':'brief'}}})
            labels.append((scope,reference,label))
    stream = StringIO()
    mcp.run_stdio_mcp_server(service,input_stream=StringIO(''.join(json.dumps(req)+'\n' for req in requests)),output_stream=stream)
    response_lines = stream.getvalue().splitlines(keepends=True)
    require(len(response_lines) == len(service.producers) == 4 and service.closed_by_stdio, 'candidate_actual_stdio_did_not_deliver_four_and_close')
    items = []
    for request,line,payload,(scope,reference,label) in zip(requests,response_lines,service.producers,labels,strict=True):
        response = json.loads(line)
        require(response.get('id') == request['id'] and response.get('result',{}).get('isError') is False,
                'candidate_actual_response_error/'+str(response)[:600])
        content = response['result']['content']
        value = json.loads(content[0]['text'])
        task = value['task_result'] if scope == 'selected' else value
        if scope == 'selected':
            require(value['region_ref']['source_triangle_indices'] == [0,1,2,3] and task['reference']['name'] == reference,
                    'incorrect_selected_source_scope')
        else:
            require(task['pair_order'] == 'A_to_B' and [row['name'] for row in task['binding']['objects']] == [TARGET,reference]
                    and task['binding']['capture_scope'] == 'selected_objects', 'incorrect_whole_source_scope')
        measured = task['facts']['surface_proximity']['value']
        answer = {'scope':scope,'reference':reference,'distance_m':measured['distance_m'],
                  'witness_a':measured['nearest_witness']['a'],'witness_b':measured['nearest_witness']['b']}
        truth_row, = (row for row in truth['measurements'] if (row['scope'],row['reference']) == (scope,reference))
        score = oracle['check_measurement'](answer,truth_row,meshes,independent_membership)
        require(score['passed'],'independent_four_pair_truth_mismatch/'+label)
        wire = replies/(label+'.json')
        wire.write_bytes(line.encode())
        producer = replies/(label+'_PRODUCER.json')
        write(producer,payload)
        stored_request = replies/(label+'_REQUEST.json')
        write(stored_request,request)
        jpg_or_png = [block for block in content if block['type']=='image']
        files = []
        if label == 'selected_Obj_05':
            frame, = payload['frames']
            png, arrays = (Path(frame[key]) for key in ('image_path','arrays_path'))
            fresh = png.read_bytes()
            original_png = Path(historic['frames'][0]['image_path'])
            require(len(jpg_or_png)==1 and base64.b64decode(jpg_or_png[0]['data'],validate=True)==fresh
                    and pin(png)['sha256'] == frame['image_sha256'] and pin(arrays)['sha256'] == frame['arrays_sha256'],
                    'product_image_array_or_wire_mismatch')
            files = [pin(png),pin(arrays),pin(original_png)]
        else:
            require(not jpg_or_png, 'unexpected_product_raster/'+label)
        items.append({'label':label,'wire':pin(wire),'request':pin(stored_request),'producer':pin(producer),
                      'score':score,'media_files':files,'body_bytes':len(content[0]['text'].encode())})
    receipt = {'passed':True,'basis':'current installed public entry over archived geometry, synthesized display wrapper over verified prior QN display rows and derived whole-pair selection; no Blender',
               'product':install['preparation_git'],'runtime_source_sha256':install['source_sha256'],
               'software_raster_offline':1,'owned_Blender':0,'model':0,'fixtures':items,
               'source_pins':[pin(path) for path in [BINDING,OLD/'R1_RUN_BINDING.json',OLD/'RUNTIME_ARCHIVE.json',Path(__file__),*inputs]],
               'actual_stdio_closed':True}
    write(output/'PRODUCT_REPLAY.json',receipt)
    print(json.dumps({'passed':True,'fixtures':[(row['label'],row['body_bytes']) for row in items]}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True,type=Path)
    main(parser.parse_args().output.resolve())
