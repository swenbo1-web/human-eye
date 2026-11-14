"""Create the one independent fixed-case reference without product imports."""

import hashlib
import importlib.util
import json
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent


def main():
    target=HERE/'admin';target.mkdir(exist_ok=True)
    path=target/'TRUTH.json'
    if path.exists():
        raise FileExistsError('single_independent_truth_already_created')
    def guard(event,args):
        if event in ('subprocess.Popen','os.system','socket.connect','socket.bind'):
            raise RuntimeError('pure_truth_forbids_process_or_network')
        if event=='import' and str(args[0]).split('.')[0] in ('human_eye_plugin','human_eye_module1_operators','numpy','PIL','bpy'):
            raise RuntimeError('pure_truth_forbids_product_or_image_import')
    sys.addaudithook(guard)
    spec=importlib.util.spec_from_file_location('_complete_witness_independent_oracle',HERE/'oracle.py')
    oracle=importlib.util.module_from_spec(spec);spec.loader.exec_module(oracle)
    scene=HERE/'inputs/SCENE_GEOMETRY_RATIONAL.json';cameras=HERE/'inputs/CAMERAS.json';capture=HERE/'inputs/CAPTURE_REPLAY.json'
    source_scene=oracle.read(scene);source_capture=oracle.read(capture)
    if (source_capture['unit']!='m' or source_capture['coordinate_frame']!='world'
            or len(source_capture['meshes'])!=len(source_scene['objects'])):
        raise ValueError('complete_world_capture_contract')
    for obj,mesh in zip(source_scene['objects'],source_capture['meshes']):
        if (obj['name']!=mesh['name'] or obj['triangles']!=mesh['faces']
                or [[oracle.fraction(v) for v in p] for p in obj['vertices']]
                   !=[[oracle.fraction(v) for v in p] for p in mesh['vertices']]):
            raise ValueError('independent_scene_capture_geometry_mismatch')
    truth=oracle.geometry_truth(source_scene,oracle.read(cameras))
    for region,mesh in zip(truth['regions'],source_capture['meshes']):
        region['host_id']=mesh['object_id']
    truth.update(schema='complete-witness-independent-truth-v1',
        input_sha256=dict(scene=oracle.sha(scene),cameras=oracle.sha(cameras),capture=oracle.sha(capture)),
        oracle_source_sha256=oracle.sha(HERE/'oracle.py'),prepare_source_sha256=oracle.sha(__file__),
        actual_product_raster_model_calls=0,
        derivation='Exact independent plane-shadow rectangles and exact binary-float camera matrix fractions. Pixel counts remain unknown until the sole actual run.')
    with path.open('x',encoding='utf-8',newline='\n') as stream:
        json.dump(truth,stream,ensure_ascii=False,allow_nan=False,sort_keys=True,indent=2);stream.write('\n')
    print(json.dumps(dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),product_raster_model_calls=0)))


if __name__=='__main__':
    main()
