"""Run the fixed product's public entry on immutable Q1 host captures without Blender."""

import argparse
import base64
from copy import deepcopy
from hashlib import sha256
from io import StringIO
import json
from pathlib import Path
from runpy import run_path
import sys
from zipfile import ZipFile


NS = Path(__file__).resolve().parents[1]
V = NS.parent
OLD = V/'m4_cross_scale_live_qualification_001'
OLD_BINDING = V/'m4_live_assembly_relation_task_001/PRODUCT_RUN_BINDING.json'
BINDING = V/'m1_source_region_default_measurement_entry_001/install/PRODUCT_RUN_BINDING.json'
SOURCE = Path('D:/he_m4_cross_scale_live_qualification_001/slots/Q1')


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
    loader = run_path(str(V/'m4_cross_scale_discovery_001/oracle/check_saved.py'))
    historical = read(OLD_BINDING)
    archive_index = read(OLD/'RUNTIME_INDEX.json')
    archive = Path(archive_index['archive']['path'])
    require(pin(archive)['sha256']==archive_index['archive']['sha256'], 'archived_Q1_zip_changed')
    old_producer = SOURCE/'product_full/call_001/SERVICE_RESULT.json'
    compact_path = SOURCE/'INDEPENDENT_SCENE.json'
    files = sorted((SOURCE/'native/WIRE').glob('*/*.bin')) + [old_producer,compact_path,SOURCE/'native/input.blend']
    with ZipFile(archive) as z:
        require(all(path.read_bytes()==z.read(path.relative_to(SOURCE.parents[1]).as_posix()) for path in files),
                'archived_Q1_host_inputs_changed')
    audit = loader['Audit']()
    captures, commands = loader['decode_captures'](SOURCE,historical,audit)
    wanted = read(old_producer)['binding']
    same = [capture for capture in captures if capture['capture_state']==wanted['capture_state']
            and capture['revision']==wanted['scene_revision']]
    require(same and all(item==same[0] for item in same), 'ambiguous_archived_full_scene_source')
    capture = same[0]
    independent = {row['name']:row for row in read(compact_path)['objects']}
    for mesh in capture['meshes']:
        row = independent[mesh['name']]
        require((mesh['object_id'],mesh['vertices'],mesh['faces'])==(row['object_id'],row['vertices'],row['triangles'])
                and capture['host_identity']['object_instances'][row['object_id']]==row['instance_id'],
                'archived_source_differs_from_independent_Q1_geometry')
    require(len(capture['meshes'])==len(independent)==9 and capture['display_snapshot']['status']=='captured'
            and all(row['visible_get'] is True for row in capture['display_snapshot']['objects']), 'archived_display_not_complete')
    return capture, [pin(path) for path in [OLD_BINDING,OLD/'RUNTIME_INDEX.json',archive,*files]], commands


def main(output):
    install = read(BINDING)
    sys.path[:0] = [install['install_root'],install['dependency_root']]
    from human_eye_plugin import live_spatial_mcp as mcp
    from human_eye_plugin.live_service import LiveSpatialService
    from human_eye_plugin.runtime_identity import runtime_identity

    capture, sources, commands = captured_source()
    require(runtime_identity()['source_sha256']==install['source_sha256']
            and Path(mcp.__file__).resolve().is_relative_to(Path(install['install_root'])), 'wrong_candidate_runtime_source')
    request_args = run_path(str(NS/'qualification/diagnostic.py'))['product_arguments']
    output.mkdir(parents=True,exist_ok=False)
    replies = output/'public'
    replies.mkdir()
    config_path = output/'CONFIG.json'
    write(config_path,{'schema_version':'1.0','enabled':True,'observe_on_prompt':False,
        'project_root':install['install_root'],'state_file':str(output/'product_state.json'),
        'audit_file':str(output/'product_audit.jsonl'),'request_budget_s':30,
        'expected_identity':{'source_sha256':install['source_sha256']}})

    class ArchivedHost:
        reads = 0

        def capture_scene(self):
            self.reads += 1
            return deepcopy(capture)

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

    service=RecordingService()
    labels=('Obj_02','Obj_06')
    requests=[{'jsonrpc':'2.0','id':f'observe-{i}','method':'tools/call','params':
                {'name':'human_eye_scene_observe','arguments':request_args(name)}} for i,name in enumerate(labels,1)]
    stream=StringIO()
    mcp.run_stdio_mcp_server(service,input_stream=StringIO(''.join(json.dumps(req)+'\n' for req in requests)),output_stream=stream)
    lines=stream.getvalue().splitlines(keepends=True)
    require(len(lines)==len(service.producers)==service.host.reads==2 and service.closed_by_stdio,
            'candidate_actual_stdio_did_not_deliver_both_or_close')
    measured_by_target=[]
    for name,request,line,producer in zip(labels,requests,lines,service.producers,strict=True):
        result=json.loads(line)
        require(result.get('id')==request['id'] and result.get('result',{}).get('isError') is False,
                'candidate_actual_response_error/'+str(result)[:700])
        content=result['result']['content']
        body=json.loads(content[0]['text'])
        measured=body['task_result']; metric=measured['facts']['surface_proximity']
        expected=(1062**.5/16) if name=='Obj_02' else .125
        require(abs(metric['value']['distance_m']-expected)<1e-12 and measured['reference']['name']=='Obj_03'
                and body['region_ref']['source_triangle_indices']==[0,1], 'current_selection_or_measurement_wrong')
        images=[entry for entry in content if entry['type']=='image']
        frame, = producer['frames']; png=Path(frame['image_path']); arrays=Path(frame['arrays_path'])
        require(len(images)==1 and base64.b64decode(images[0]['data'],validate=True)==png.read_bytes()
                and pin(png)['sha256']==frame['image_sha256'] and pin(arrays)['sha256']==frame['arrays_sha256'],
                'current_selected_original_image_wrong')
        visibility=producer['facts']['visibility']
        if name=='Obj_02':
            require(visibility['complete_witness'] is not None and body['images'][0]['local_image_path']==png.as_posix(),
                    'positive_original_witness_or_path_missing')
        else:
            require(visibility['complete_witness'] is None and visibility['selected_surface_pixels']==0
                    and len(body['view_attempts'])==6 and all(row['status']=='positive_area_occlusion' for row in body['view_attempts']),
                    'negative_registered_views_did_not_match_occlusion')
        wire=replies/(name+'.json'); wire.write_bytes(line.encode())
        request_file=replies/(name+'_REQUEST.json'); write(request_file,request)
        producer_file=replies/(name+'_PRODUCER.json'); write(producer_file,producer)
        measured_by_target.append({'object':name,'wire':pin(wire),'producer':pin(producer_file),'request':pin(request_file),
            'image':pin(png),'arrays':pin(arrays),'text_bytes':len(content[0]['text'].encode()),'visibility':visibility,
            'distance':metric['value']['distance_m'],'nearest':metric['value']['nearest_witness']})
    receipt={'passed':True,'runtime_source_sha256':install['source_sha256'],'sources':[pin(BINDING),pin(Path(__file__)),*sources],
        'archived_host_commands':commands,'actual_stdio_closed':True,'owned_Blender':0,'models':0,
        'offline_software_rasters':sum(row['work']['raster_attempts'] for row in service.producers),
        'results':measured_by_target,'scope':'installed solver/renderer and public stdio over immutable actual Q1 host geometry and display snapshots'}
    write(output/'PRODUCT_REPLAY.json',receipt)
    print(json.dumps({'passed':True,'results':[(row['object'],row['text_bytes'],row['distance']) for row in measured_by_target]}))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True,type=Path)
    main(parser.parse_args().output.resolve())
