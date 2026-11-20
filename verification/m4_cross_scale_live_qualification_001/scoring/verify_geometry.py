"""Qualify current original frames and region evidence with sealed independent geometry."""

import argparse
import base64
import hashlib
import importlib.util
import json
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
ORACLE = ROOT / 'verification/m4_cross_scale_discovery_001/oracle'
PRIOR = ROOT / 'verification/m4_global_local_qualification_001'
ASSET = Path('D:/he_m4_global_local_001/fixture/main.blend')
ASSET_SHA = 'a2d55e9212a84d27489aa72a680092b4e91d94d9df27d29c5de40d8a4ca3d0c6'
CURRENT_BINDING = ROOT / 'verification/m4_live_assembly_relation_task_001/PRODUCT_RUN_BINDING.json'
CURRENT_BINDING_SHA = 'eb0ecece262ce0fbbe2b01f041b9e6eab77f0c4810030094c2f590850f51b2e0'
CURRENT_SOURCE = '0d75c8f7f3522c4c7f2a5807f51f86fc4f2bec49efa9a215bf090775787ab91b'
PINS = {
    ORACLE / 'check_saved.py': '79862eb4b47e15aa2053292e218842b1c34bbe71122e1b94938d07be2ec530de',
    ORACLE / 'expected.py': 'cdbd6263f3b1e2346679c6bfff00f62c0fae8e2a08f67ca8ad26de8d5215bf22',
    ORACLE / 'geometry_witness.py': '29138a145c6a04bccce7ae950f43e3546efc2d71a533b73105bb4a05277558a0',
    ORACLE / 'EXPECTATIONS.json': '5c9213e34d33c59c5abe7bf4139e81c067e6041fa1957312c8533fad064d7d49',
    PRIOR / 'fixture/private/ROLE_MAP.json': 'd04d55335e0ce7135a3f07905b25f3539f7c0024d91dc30b0bbf73f9a8ce417c',
    PRIOR / 'oracle/static_oracle.py': '019242f0d881dff998daca74ec5303bda86b202233e207da966b9773673d87f2',
    PRIOR / 'oracle/STATIC_QUALIFICATION.json': '549fda4551f5b54c873e59b9c0fa83bea0599966c414e5eaea5a2368ec0cacca',
    PRIOR / 'fixture/GEOMETRY.json': '34c4ad599c6ead7548b21300315df25808fa274dad9dccafbf3b5808fee56ad8',
    PRIOR / 'checks/saved_frames_r2.py': 'a7e7fb4d42fc845e43b37e0870af10beb79da333a70f5017bcf534cb11390f34',
    ASSET: ASSET_SHA,
}
MAIN = {'mode': 'active_observation', 'region_task': {
    'area_min_m2': .0078125, 'area_max_m2': .03125, 'normal_z_min': .75}}
EXPECTED = {'Obj_02': 'covered', 'Obj_06': 'unknown', 'Obj_09': 'covered'}


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def read(path):
    return json.loads(Path(path).read_bytes())


def require_exact_request(row, repeat=None, *, historical=False):
    args = row['request']['params']['arguments']
    canonical = {'include_image': True, 'query': MAIN}
    if historical and 'session_id' in args:
        canonical['session_id'] = args['session_id']
    require(row['request']['params']['name'] == 'human_eye_scene_observe' and args == canonical,
            'same registered whole-scene query with production default brief required')
    if repeat is not None:
        require(args == repeat['request']['params']['arguments'], 'repeat parameters differ')


def helpers():
    for path, expected in PINS.items():
        require(digest(path.read_bytes()) == expected, 'frozen independent source changed: ' + str(path))
    spec = importlib.util.spec_from_file_location('_sealed_existing_geometry_checker', ORACLE / 'check_saved.py')
    checker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker)
    return checker


def independently_expected(checker):
    oracle = checker.expected.EXACT
    objects = checker.expected.fixture()
    components, eligible = checker.expected.task_components(objects, MAIN['region_task'])
    counts = {'objects': len(objects), 'vertices': sum(len(m['vertices']) for m in objects),
              'triangles': sum(len(m['triangles']) for m in objects), 'components': len(components),
              'rectangles': sum(c['rectangle_supported'] for c in components),
              'rectangle_triangles': sum(len(c['source_triangle_indices']) for c in components if c['rectangle_supported'])}
    require(counts == {'objects': 9, 'vertices': 54, 'triangles': 56, 'components': 24,
                       'rectangles': 22, 'rectangle_triangles': 44}, 'independent fixture counts differ')
    require({row['object_name'] for row in eligible} == set(EXPECTED)
            and all(row['source_triangle_indices'] == [0, 1] for row in eligible), 'independent task set differs')
    roles = read(PRIOR / 'fixture/private/ROLE_MAP.json')['objects']
    occlusion = oracle.occlusion_proofs(objects, roles)['covered_six_directions']
    require({row['view'] for row in occlusion} == set(oracle.VIEWS)
            and all(row['blocker_object_name'] == 'Obj_03' and row['whole_rectangle_strictly_occluded']
                    for row in occlusion), 'independent occlusion proof differs')
    return {'fixture_counts': counts, 'eligible': oracle.rational_json(eligible),
            'occlusion': oracle.rational_json(occlusion), 'outside_selection_occluder': 'Obj_03'}


def repeat_from_originals(checker, session, original, repeated, *, historical=False):
    require_exact_request(repeated, repeat=original, historical=historical)
    require(original['id'] != repeated['id'] and original['closed_ns'] <= repeated['started_ns'],
            'repeat is not a fresh RPC after the first delivery')
    audit = checker.Audit()
    for row in (original, repeated):
        tx = audit.read(row['actual_TX_path'], row['actual_TX_sha256'], session)
        rx = audit.read(row['actual_RX_path'], row['actual_RX_sha256'], session)
        require(tx == audit.read(row['request_path'], row['request_sha256'], session)
                and rx == audit.read(row['response_path'], row['response_sha256'], session)
                and rx['id'] == tx['id'] and rx['result']['isError'] is False,
                'repeat receipts differ from actual installed stdio')
    first, second = [audit.read(row['producer_archive']['path'], row['producer_archive']['sha256'], session)
                     for row in (original, repeated)]
    work = second['work']
    require(first['work']['result_cache_hit'] is False and work['result_cache_hit'] is True
            and work['raster_attempts'] == work['raster_completed'] == 0,
            'repeat did not reuse original full-result raster frames')
    require(first['binding'] == second['binding'] and first['facts']['region_task'] == second['facts']['region_task'],
            'repeat source generation or original task changed')
    require(first['frames'] == second['frames'] and first['constructed_frames'] == second['constructed_frames'],
            'repeat frame archive differs from generation one')
    content = [audit.read(row['actual_RX_path'], row['actual_RX_sha256'], session)['result']['content']
               for row in (original, repeated)]
    require(all([b['type'] for b in blocks] == ['text', 'image', 'image', 'image'] for blocks in content),
            'repeat needs one original text and three images')
    require(content[0][1:] == content[1][1:], 'repeat native image bytes or ordering changed')
    left, right = (json.loads(blocks[0]['text']) for blocks in content)
    require(all(left[k] == right[k] for k in ('binding', 'objects', 'region_task', 'scopes', 'images', 'witness_pixels')),
            'repeat changed one or more consumer-visible geometry fields')
    return {'scope': 'identical full task result, separate ROI continuation untested', 'work': work,
            'same_source_generation': True, 'same_frame_refs_and_bytes': True,
            'PNG_bytes': [len(base64.b64decode(b['data'], validate=True)) for b in content[1][1:]],
            'image_sha256': [digest(base64.b64decode(b['data'], validate=True)) for b in content[1][1:]],
            'input_pins': list(audit.pins.values())}


def compare_independent_scene(checker, session, captured):
    audit = checker.Audit()
    path = session / 'INDEPENDENT_SCENE.json'
    ordinary = audit.read(path, within=session)
    require(ordinary['source']['asset_sha256'] == ASSET_SHA
            and ordinary['source']['scale_length'] == 1
            and ordinary['source']['frame'] == 1 and ordinary['source']['subframe'] == 0,
            'independent owned scan did not bind fixed asset, units and frame')
    meshes = {mesh['name']: mesh for mesh in captured['meshes']}
    require(len(ordinary['objects']) == len(meshes) == 9
            and {row['name'] for row in ordinary['objects']} == set(meshes), 'owner scan object set differs')
    identities = captured['host_identity']['object_instances']
    for row in ordinary['objects']:
        mesh = meshes[row['name']]
        require(row['vertices'] == mesh['vertices'] and row['triangles'] == mesh['faces']
                and row['object_id'] == mesh['object_id'] and row['instance_id'] == identities[mesh['object_id']],
                'independent live scan geometry or instance differs: ' + row['name'])
    return {'exact_geometry_and_object_instance_match': True, 'source': ordinary['source'],
            'input_pins': list(audit.pins.values())}


def run_validate(session, binding, first_index=1, repeat_index=2, *, historical=False):
    checker = helpers()
    truth = independently_expected(checker)
    calls = [json.loads(line) for line in (session / 'PUBLIC_REQUESTS.jsonl').read_bytes().splitlines() if line.strip()]
    require(historical or (len(calls) in (1, 2) and first_index == 1 and repeat_index == 2), 'original business denominator exceeds fixed plan')
    if not historical:
        require(digest(binding.read_bytes()) == CURRENT_BINDING_SHA, 'current installed source binding changed')
        attestation = read(binding)
        require(attestation['source_sha256'] == CURRENT_SOURCE and len(attestation['source_manifest']) == 143,
                'expected isolated 143-source installed product required')
        require(digest((session / 'native/input.blend').read_bytes()) == ASSET_SHA,
                'owned copy does not match fixed fixture')
    original = calls[first_index - 1]
    require_exact_request(original, historical=historical)
    evidence = checker.check_session(session, binding, 'optimized', first_index)
    captured = evidence.pop('current_capture')
    require(sum(len(mesh['vertices']) for mesh in captured['meshes']) == 54, 'actual source did not contain 54 vertices')
    require({row['object_name']: row['status'] for row in evidence['outcomes']} == EXPECTED,
            'current regional evidence set differs from independently expected')
    require(len({row['scope_id'] for row in evidence['selected_frames']}) == 3
            and len({row['frame_identity'] for row in evidence['selected_frames']}) == 3
            and len({row['camera_identity'] for row in evidence['selected_frames']}) == 3,
            'scope, frame, or camera identifier silently collides')
    if not historical:
        evidence['independent_current_scene'] = compare_independent_scene(checker, session, captured)
    repeated = 'unrun' if repeat_index == 0 or len(calls) < repeat_index else repeat_from_originals(
        checker, session, original, calls[repeat_index - 1], historical=historical)
    return {'passed': repeated != 'unrun' or historical, 'first_passed': True, 'historical_control_only': historical,
            'truth': truth, 'first': evidence, 'repeat': repeated, 'source_pins': {str(p): sha for p, sha in PINS.items()},
            'new_operations': {'Blender': 0, 'model': 0, 'raster': 0, 'MCP': 0}}


if __name__ == '__main__':
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--session', type=Path)
    cli.add_argument('--binding', type=Path, default=CURRENT_BINDING)
    cli.add_argument('--output', type=Path, required=True)
    cli.add_argument('--first-index', type=int, default=1)
    cli.add_argument('--repeat-index', type=int, default=2)
    cli.add_argument('--historical-control', action='store_true')
    args = cli.parse_args()
    try:
        if args.session is None:
            result = {'passed': True, 'scope': 'static pre-run truth only', 'truth': independently_expected(helpers()),
                      'source_pins': {str(p): sha for p, sha in PINS.items()}}
        else:
            result = run_validate(args.session.resolve(), args.binding.resolve(), args.first_index, args.repeat_index,
                                  historical=args.historical_control)
    except Exception as error:
        result = {'passed': False, 'error': {'type': type(error).__name__, 'reason': str(error)}}
    with args.output.open('x', encoding='utf8', newline='\n') as stream:
        json.dump(result, stream, indent=2, allow_nan=False, ensure_ascii=False)
        stream.write('\n')
    print(json.dumps({'passed': result['passed'], 'checks': result.get('first', {}).get('check_count'),
                      'error': result.get('error')}))
    raise SystemExit(0 if result['passed'] else 1)
