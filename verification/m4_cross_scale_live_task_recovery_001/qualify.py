"""Independently check the original zero-model qualification slots and delivery budget."""

import base64
from fractions import Fraction
import hashlib
import importlib.util
import io
import json
import math
from pathlib import Path
import runpy
import sys
import time


NS = Path(__file__).resolve().parent
ROOT = NS.parents[1]
RUN = Path('D:/he_m4_cross_scale_live_task_recovery_001')
BINDING = ROOT / 'verification/m4_live_assembly_relation_task_001/PRODUCT_RUN_BINDING.json'
OLD = ROOT / 'verification/m4_cross_scale_live_qualification_001/checks/delivery.py'
ORACLE = ROOT / 'verification/m4_cross_scale_discovery_001/oracle/check_saved.py'


def read(path):
    return json.loads(Path(path).read_bytes())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(value, reason):
    if not value:
        raise ValueError(reason)


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def close_vec(left, right):
    return len(left) == len(right) and all(math.isclose(float(Fraction(x)), float(Fraction(y)),
                                                        abs_tol=1e-6, rel_tol=0.0) for x, y in zip(left, right))


def match_geometry(meshes, role):
    expected = {m['name']: m for m in read(NS / 'fixture/GEOMETRY.json')['objects']}
    require(len(expected) == len(meshes) == 21 and {m['name'] for m in meshes} == set(expected),
            'current_readback_roster_differs/' + role)
    for mesh in meshes:
        spec = expected[mesh['name']]
        geom = mesh[role]
        differ = (geom['triangles'] != spec['triangles'] or
                  [list(map(Fraction, p)) for p in geom['vertices_world_m']] !=
                  [list(map(Fraction, p)) for p in spec['vertices_world_m']])
        require(not differ, 'current_readback_ordered_geometry_changed/' + role + '/' + mesh['name'])


def readbacks(slot, slot_result):
    paths = [Path(slot_result[name]['path']) for name in ('initial_source', 'terminal_source')]
    for path, key in zip(paths, ('initial_source', 'terminal_source'), strict=True):
        require(path.resolve().is_relative_to(slot.resolve()) and sha(path) == slot_result[key]['sha256'],
                'current_owned_readback_pin_differs/' + key)
    first, last = [read(path) for path in paths]
    asset = read(NS / 'fixture/ASSET_BINDING.json')
    protected = ('source', 'objects', 'scene_cameras', 'layer_collections', 'display_object_mask', 'source_face_offsets')
    require(all(first.get(field) == last.get(field) for field in protected), 'current_native_or_display_state_differs')
    source = first['source']
    copy = (slot / 'native/input.blend').resolve()
    require(Path(source['asset_copy']).resolve() == copy and source['asset_sha256'] == asset['asset_sha256'] == sha(copy)
            and source['scale_length'] == 1 and source['frame'] == 1 and source['subframe'] == 0,
            'current_owned_asset_or_frame_differs')
    for role in ('native', 'evaluated'):
        match_geometry(first['objects'], role)
    return {'exact_independent_initial_terminal_world_geometry_and_display': True,
            'initial_sha256': sha(paths[0]), 'terminal_sha256': sha(paths[1]), 'scope': source['view_layer']}


def pixel_counts(arrays, mask):
    import numpy as np
    rgb = arrays['color'][:, :, :3].astype(np.int32)
    boundary = np.zeros(mask.shape, dtype=bool)
    for a, b in ((np.s_[:-1, :], np.s_[1:, :]), (np.s_[1:, :], np.s_[:-1, :]),
                 (np.s_[:, :-1], np.s_[:, 1:]), (np.s_[:, 1:], np.s_[:, :-1])):
        boundary[a] |= mask[a] & ~mask[b] & (np.linalg.norm(rgb[a] - rgb[b], axis=2) >= 24)
    return int(np.count_nonzero(mask)), int(np.count_nonzero(boundary))


def image_bytes(contents):
    from PIL import Image
    images = []
    for block in contents:
        if block['type'] == 'image':
            raw = base64.b64decode(block['data'], validate=True)
            require(block['mimeType'] == 'image/png', 'original_image_not_PNG')
            with Image.open(io.BytesIO(raw)) as img:
                require(img.format == 'PNG' and img.size == (512, 512), 'original_PNG_shape_wrong')
                img.verify()
            images.append(raw)
    return images


def consumer_budget(result, required):
    old = load('_cross_task_pinned_cli_policy', OLD)
    helper, policy = old.budget_helpers()
    originals = [row['text'] for row in result['content'] if row['type'] == 'text']
    verdict = []
    for seconds in ('0.0000', '10.0000', '100.0000'):
        raw = helper['model_items'](result, seconds)
        emitted = helper['truncate_items'](raw, policy['MCP_bytes'])
        retained = helper['truncate_items'](emitted, policy['history_approximate_tokens'], token_mode=True)
        texts = '\n'.join(row['text'] for row in retained if row['type'] == 'input_text')
        lost = [name for name, data in required.items() if data not in texts]
        same_images = [i for i in raw if i['type'] == 'input_image'] == [i for i in retained if i['type'] == 'input_image']
        verdict.append({'header_bytes': len(raw[0]['text'].encode()), 'text_exact': raw == retained,
                        'required_facts_lost': lost, 'images_exact': same_images})
    return {'body_bytes': sum(len(text.encode()) for text in originals), 'stages': verdict,
            'passed': all(not row['required_facts_lost'] and row['images_exact'] for row in verdict),
            'live_provider_input': None}


def compact(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'))


def product(slot, truth, result):
    checker = load('_cross_task_exact_product_frame', ORACLE)
    audit = checker.Audit()
    capture_receipts, _ = checker.decode_captures(slot, read(BINDING), audit)
    calls = [json.loads(line) for line in (slot / 'PUBLIC_REQUESTS.jsonl').read_bytes().splitlines()]
    require(len(calls) == 1, 'QP_must_use_one_actual_product_call')
    call = calls[0]
    require(call['request']['params']['arguments'] == read(NS / 'inputs/REQUEST.json') and
            call['response']['result'] == result, 'actual_product_rpc_or_diagnostic_delivery_differs')
    archive = call['producer_archive']
    full = audit.read(archive['path'], archive['sha256'], slot)
    source = checker.current_capture(capture_receipts, full['binding'], audit)
    checker.source_binding_checks(source, full['binding'], read(BINDING), audit)
    fixture = checker.expected.EXACT.read_objects(read(NS / 'fixture/GEOMETRY.json'))
    expected_meshes = {mesh['name']: mesh for mesh in fixture}
    captured_meshes = {mesh['name']: mesh for mesh in source['meshes']}
    require(len(source['meshes']) == len(expected_meshes) == 21 and captured_meshes.keys() == expected_meshes.keys(),
            'current_product_mesh_roster_differs')
    for name, expected_mesh in expected_meshes.items():
        mesh = captured_meshes[name]
        require([tuple(Fraction(v) for v in p) for p in mesh['vertices']] == expected_mesh['vertices'] and
                [tuple(triangle) for triangle in mesh['faces']] == expected_mesh['triangles'],
                'current_ordered_product_geometry_differs/' + name)
    require(sum(len(mesh['faces']) for mesh in source['meshes']) == 184 and
            sum(len(mesh['vertices']) for mesh in source['meshes']) == 148, 'fixed_current_scene_counts_differ')
    public = json.loads(result['content'][0]['text'])
    png = image_bytes(result['content'])
    require(public['schema'] == 'active-observation-region-task-brief-v1' and public['read_only'] is True and
            public['execution_authority'] is False, 'initial_product_brief_contract_missing')
    public_rows = {row['object_name']: row for row in public['region_task']['rows']}
    rows = {row['object_name']: row for row in full['facts']['region_task']['rows']}
    require(set(public_rows) == set(rows) == set(truth) and len(rows) == len(public['region_task']['rows']),
            'product_region_roster_differs')
    require(len(png) == 3, 'product_must_deliver_actual_overview_and_two_witness_images')
    frames = {f['frame_identity']: f for f in full['constructed_frames']}
    scopes = {s['scope_id']: s for s in full['scopes']}
    components, _ = checker.expected.task_components(fixture, read(NS / 'inputs/REQUEST.json')['query']['region_task'])
    components = {row['object_name']: row for row in components if row['eligible']}
    details = {}
    for name, expected in truth.items():
        row, shown = rows[name], public_rows[name]
        component = components[name]
        checker.validate_region(row, component, {x['name']: x for x in fixture}, audit)
        require(row['source'] == checker.source_row(component, source, full['binding']), 'product_current_source_unbound/' + name)
        projected = {**shown}
        if shown['complete_witness']:
            projected['complete_witness'] = dict(shown['complete_witness'])
            projected['complete_witness'].pop('native_content_block_index')
        require(projected == row, 'public_product_region_changes_facts/' + name)
        allowed = expected['eligible_complete_views']
        result_row = details[name] = {'triangles': row['source_triangle_indices'], 'status': row['status'], 'reason': row['reason']}
        if not allowed:
            require(row['status'] == 'unknown' and row['complete_witness'] is None and
                    row['reason'] == 'positive_area_occlusion_all_front_views', 'product_covered_unknown_missing/' + name)
            continue
        require(row['status'] == 'covered' and row['complete_witness'], 'product_local_witness_missing/' + name)
        witness = row['complete_witness']; frame = frames[witness['frame_identity']]; view = frame['view_name']
        require(view in allowed and frame['scope_id'] != 'global' and frame['image_ref'] == witness['image_ref'],
                'product_local_direction_or_scope_invalid/' + name)
        scope = scopes[frame['scope_id']]
        checker.local_binding_checks(scope, full['binding'], row['source'], audit)
        regions, patch = checker.patch_maps(scope, source, audit)
        observation = next(o for o in scope['facts']['observations'] if o['frame_identity'] == frame['frame_identity'])
        pixel = observation['pixel_rows'][witness['pixel_row_index']]
        require(pixel['roi_id'] == row['roi_id'] and pixel['visible_surface_pixels'] >= 16 and
                pixel['contrasting_boundary_pixels'] >= 4, 'product_pixel_gates_not_met/' + name)
        image = Path(frame['image_path'])
        index = shown['complete_witness']['native_content_block_index']
        require(1 <= index <= 3 and image.read_bytes() == png[index - 1] and sha(image) == frame['image_sha256'],
                'product_actual_native_image_binding_missing/' + name)
        checker.geometry_witness.prove(fixture, component, tuple(frame['pose']['direction_rational']))
        checker.check_frame(frame, observation, scope, source, regions, patch, slot, audit)
        result_row.update(view=view, image_sha256=sha(image), PNG_bytes=image.stat().st_size,
                          surface_pixels=pixel['visible_surface_pixels'], boundary_pixels=pixel['contrasting_boundary_pixels'])
    raw_text = result['content'][0]['text']
    needed = {name: compact(public[name]) for name in ('binding', 'region_task', 'scopes', 'images', 'witness_pixels')}
    require(all(body in raw_text for body in needed.values()), 'product_public_text_canonical_check_failed')
    return {'regions': details, 'geometric_checks': len(audit.checks), 'work': full['work'],
            'image_bytes': list(map(len, png)), 'CLI': consumer_budget(result, needed)}


def native(slot, truth, result):
    import numpy as np
    contents = result['content']
    raw = json.loads(contents[0]['text'])
    stdout = raw['stdout'].strip()
    answer = json.loads(stdout.splitlines()[-1])
    images = image_bytes(contents)
    receipt = read(slot / 'DEVICE_EVIDENCE.json')
    frames = receipt['frames']
    if isinstance(frames, list):
        frames = {row['ref']: row for row in frames}
    rows = {row['object_name']: row for row in answer['regions']}
    require(set(rows) == set(truth) and len(images) == 2 and answer['objects'] == 21, 'native_geometric_roster_and_images')
    witness_count = 0
    for name, target in truth.items():
        row = rows[name]
        require(row['triangles'] == target['source_triangle_indices'] and
                close_vec(row['center_world_m'], target['center_world_m']) and
                close_vec(row['unit_normal'], target['unit_normal']) and
                abs(row['area_m2'] - target['area_m2']) < 1e-6, 'native_region_geometry_differs/' + name)
        allowed = target['eligible_complete_views']
        if not allowed:
            require(row['status'] == 'unknown' and len(row['directions']) == 6 and all(
                'positive_area_front_occluder/' in v for v in row['directions'].values()), 'native_unknown_unexplained/' + name)
            continue
        require(row['status'] == 'covered' and row['direction'] in allowed and row['ref'] in frames,
                'native_required_local_direction_or_frame_missing/' + name)
        frame = frames[row['ref']]
        base = slot / 'native_frames' / f'{witness_count + 1:03d}'
        image = base / 'SCENE.png'
        array = base / 'SCENE.npz'
        require(frame['source_ref'] == answer['source_ref'] and frame['view'] == row['direction'] and
                close_vec(frame['pose']['target_world_m'], target['center_world_m']) and
                frame['frame_identity'] == row['frame_identity'] and frame['PNG_sha256'] == sha(image) and
                images[witness_count] == image.read_bytes(), 'native_actual_image_binding_missing/' + name)
        index = frame['object_names'].index(name)
        required = [frame['source_face_offsets'][index] + t for t in row['triangles']]
        with np.load(array, allow_pickle=False) as evidence:
            mask = (evidence['owners'] == index) & np.isin(evidence['triangle_ids'], required)
            surface, boundary = pixel_counts(evidence, mask)
        require(surface == row['surface_pixels'] and boundary == row['contrasting_boundary_pixels'] and
                surface >= 16 and boundary >= 4, 'native_actual_pixel_gates_failed/' + name)
        witness_count += 1
    require(witness_count == 2, 'native_two_actual_local_witnesses_required')
    return {'regions': rows, 'image_bytes': list(map(len, images)),
            'CLI': consumer_budget(result, {'native_required_facts': contents[0]['text']})}


def main():
    started = time.perf_counter_ns()
    binding = read(BINDING)
    sys.path.insert(0, binding['dependency_root'])
    truth = {row['object_name']: row for row in read(NS / 'fixture/CURRENT_TRUTH.json')['eligible']}
    slots = []
    for label, score in (('QN', native), ('QP', product)):
        slot = RUN / 'slots' / label
        publication = read(slot / 'SLOT_PUBLICATION.json')
        case = {'label': label, 'passed': False, 'original_status': publication['status'],
                'result_sha256': sha(slot / 'SLOT_RESULT.json')}
        try:
            require(publication['result_sha256'] == case['result_sha256'] and publication['status'] == 'completed',
                    'original_qualification_runner_failed')
            case['source_readbacks'] = readbacks(slot, read(slot / 'SLOT_RESULT.json'))
            original = read(slot / 'client/call_01/RESPONSE.json')
            require(original['result']['isError'] is False, 'diagnostic_ordinary_or_product_response_error')
            evidence = score(slot, truth, original['result'])
            case.update(evidence=evidence, passed=evidence['CLI']['passed'])
            if not case['passed']:
                case['error'] = 'actual_CLI_presentation_replay_lost_required_facts'
        except Exception as error:
            case['error'] = {'type': type(error).__name__, 'reason': str(error)}
        slots.append(case)
    overall = {'passed': all(row['passed'] for row in slots), 'slots': slots, 'formal_denominator': ['N1', 'P1'],
               'actual_models_launched_by_qualification': 0, 'freeze_sha256': sha(NS / 'FROZEN.json'),
               'started_ns': started, 'completed_ns': time.perf_counter_ns()}
    with (NS / 'QUALIFICATION.json').open('x', encoding='utf8', newline='\n') as stream:
        json.dump(overall, stream, indent=2, sort_keys=True)
        stream.write('\n')
    print(overall['passed'], [(r['label'], r.get('error')) for r in slots])
    return 0 if overall['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
