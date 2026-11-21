"""Replay the held-out noncoplanar selection through the two installed MCP servers."""

import argparse
from copy import deepcopy
from io import BytesIO
from math import isclose, sqrt
from pathlib import Path
from runpy import run_path
import sys
from time import perf_counter_ns


HERE = Path(__file__).resolve().parent
NS = HERE.parent
V = NS.parent
sys.path.insert(0, str(HERE))
from capture import pinned_capture, require


PRIOR = V/'m1_source_region_task_entry_001/qualification/product_replay.py'
TARGET = 'Obj_08'
REFERENCE = 'Obj_04'
FACES = [0, 1, 8, 9]
SELECTED_WITNESS = ([3, -3, 0], [-4, -1/16, 15/16])
WHOLE_WITNESS = ([3, -3, 15/16], [-4, -1/16, 15/16])


def replay_tools():
    return run_path(str(PRIOR))


def worker(arm, state):
    shared = replay_tools()
    binding = shared['binding_for'](arm)
    sys.path[:0] = [binding['install_root'], binding['dependency_root']]
    from human_eye_plugin import live_spatial_mcp as mcp
    from human_eye_plugin.active_observation import fingerprint
    from human_eye_plugin.live_service import LiveSpatialService
    from human_eye_plugin.runtime_identity import runtime_identity

    require(runtime_identity()['source_sha256'] == binding['source_sha256']
            and Path(mcp.__file__).resolve().is_relative_to(Path(binding['install_root']).resolve()),
            'held_out_worker_used_wrong_install')
    capture, evidence = pinned_capture()
    save = shared['save']
    state.mkdir()
    save(state/'CAPTURE.json', evidence)
    cfg = state/'PRODUCT_CONFIG.json'
    save(cfg, {'schema_version': '1.0', 'enabled': True, 'observe_on_prompt': False,
               'project_root': binding['install_root'], 'state_file': str(state/'product_state.json'),
               'audit_file': str(state/'product_audit.jsonl'), 'request_budget_s': 60,
               'expected_identity': {'source_sha256': binding['source_sha256']}})

    class ArchivedHost:
        def capture_scene(self):
            return deepcopy(capture)

        def capture_task_scene(self, selectors):
            scene = self.capture_scene()
            by_name = {mesh['name']: mesh for mesh in scene['meshes']}
            selected = [by_name[row['name']] for row in selectors]
            scene['capture_scope'] = 'selected_objects'
            scene.pop('host_execution', None)
            scene.pop('display_snapshot', None)
            identity = scene['host_identity']
            identity['capture_scope'] = 'selected_objects'
            identity['object_instances'] = {m['object_id']: identity['object_instances'][m['object_id']] for m in selected}
            scene['capture_state']['selection_key'] = fingerprint(selectors)
            scene['task_selection'] = {'selectors': deepcopy(selectors),
                'bindings': [{'object_id': mesh['object_id'], 'name': mesh['name']} for mesh in selected],
                'pair_reason': None, 'candidate_count': len(scene['meshes'])}
            scene['meshes'] = selected
            return scene

    class RecordedService(LiveSpatialService):
        calls = 0

        def observe(self, *args, **kwargs):
            result = super().observe(*args, **kwargs)
            self.calls += 1
            save(state/f'PRODUCER_{self.calls:02d}.json', result)
            return result

        def close(self):
            save(state/'EOF.json', {'closed': True, 'observations': self.calls})

    mcp._configure_utf8_stdio()
    mcp.run_stdio_mcp_server(RecordedService(cfg, host=ArchivedHost()))


def probe(arm, output, shared, transport, deadline):
    output.mkdir()
    state = output/'product'
    command = [sys.executable, '-IB', '-X', 'utf8', str(Path(__file__).resolve()),
               '--worker', arm, str(state)]
    wire = output/'stdio'
    client = transport(command, output, wire, deadline)
    rpc, old, new = shared['rpc'], shared['OLD'], shared['NEW']
    read = shared['read']
    replies = {}
    selectors = {'region': {'object': {'name': TARGET}, 'source_triangle_indices': FACES},
                 'reference': {'name': REFERENCE}, **shared['DEFAULT_CONTEXT']}

    def call(label, tool, arguments, expected_error=None):
        response = client.call(rpc(label, 'tools/call', name=tool, arguments=arguments))
        slot = wire/f'rpc_{client.records[-1]["index"]:02d}'
        require(response == read(slot/'RX.bin'), 'held_out_stdout_reply_did_not_match_raw')
        body = read(slot/'RX.bin')['result']
        require(body['isError'] is (expected_error is not None)
                and (expected_error is None or expected_error in body['content'][0]['text']),
                'unexpected_installed_reply/' + arm + '/' + label + '/' + body['content'][0]['text'][:500])
        replies[label] = slot

    try:
        started = client.call(rpc('initialize', 'initialize', protocolVersion='2025-03-26',
                                  capabilities={}, clientInfo={'name': 'held-out-source-region', 'version': '1'}))
        require('result' in started, 'held_out_stdio_initialize_failed')
        client.call({'jsonrpc': '2.0', 'method': 'notifications/initialized'})
        catalogue = client.call(rpc('catalogue', 'tools/list'))['result']['tools']
        if arm == 'B':
            call('narrow-invalid', new, dict(selectors, response_detail='full'), 'Unexpected tool arguments')
            call('narrow', new, selectors)
        call('brief', old, shared['old_arguments'](selectors))
        call('full', old, shared['old_arguments'](selectors, 'full'))
        call('no-image', new if arm == 'B' else old, dict(selectors, include_image=False) if arm == 'B' else
             shared['old_arguments'](dict(selectors, include_image=False)))
        call('whole', old, {'query': {'mode': 'task', 'requested_facts': ['surface_proximity'],
                                     'objects': [{'name': TARGET}, {'name': REFERENCE}]},
                            'include_image': False, **shared['DEFAULT_CONTEXT']})
    finally:
        closure = client.finish()
        require(closure['confirmed'] and closure['exit_code'] == 0 and read(state/'EOF.json')['closed'],
                'held_out_installed_stdio_did_not_close')
    return {'catalogue': catalogue, 'state': state, 'replies': replies}


def metric(body, whole):
    task = body if whole else body['task_result']
    expected = sqrt(14753 if whole else 14978) / 16
    measured = task['facts']['surface_proximity']['value']
    witness = measured['nearest_witness']
    points = witness['a'], witness['b']
    wanted = WHOLE_WITNESS if whole else SELECTED_WITNESS
    direction = [(b-a)/expected for a,b in zip(*wanted, strict=True)]
    require(task['facts']['surface_proximity']['status'] == 'measured'
            and isclose(measured['distance_m'], expected, rel_tol=0, abs_tol=1e-12)
            and points == wanted and all(isclose(a,b,rel_tol=0,abs_tol=1e-12)
                                        for a,b in zip(witness['direction_a_to_b'], direction, strict=True)),
            'held_out_distance_or_nearest_pair_changed/' + ('whole' if whole else 'selected'))
    if not whole:
        require(body['region_ref']['source_triangle_indices'] == FACES and task['reference']['name'] == REFERENCE
                and task['measurement_scope'] == 'complete_selected_source_triangle_union_to_reference_triangle_surface',
                'held_out_source_region_measurement_scope_changed')
    return {'distance_m': measured['distance_m'], 'witness': witness}


def review_image(label, body, png, root, digest):
    picture, = png
    brief = label != 'full'
    row, = body['images' if brief else 'frames']
    visibility = body['visibility'] if brief else body['facts']['visibility']
    require(visibility['complete_witness'] is None and 'complete_surface_visibility' in visibility['unknown']
            and digest(picture) == row['image_sha256'] and row['view_name'] == visibility['view_name'] == 'SCENE'
            and all(row[key] == visibility[key] for key in ('frame_identity', 'image_ref'))
            and row['host_binding_sha256'] == body['binding']['binding_sha256'],
            'held_out_partial_sample_or_coverage_boundary_mismatch')
    value = row.get('local_image_path' if brief else 'image_path')
    path = None if value is None else Path(value)
    openable = (path is not None and path.is_absolute() and path.is_relative_to(root)
                and len(path.relative_to(root).parts) == 2 and path.resolve(strict=True) == path
                and path.read_bytes() == picture)
    return {'bytes': len(picture), 'sha256': digest(picture), 'frame_identity': row['frame_identity'],
            'image_ref': row['image_ref'], 'view': row['view_name'], 'path': value,
            'path_opened_exact_bytes': openable, 'visible_source_triangle_indices': visibility.get('visible_source_triangle_indices'),
            'visible_source_triangle_count': visibility.get('visible_source_triangle_count'),
            'unseen_source_triangle_indices': visibility.get('unseen_source_triangle_indices'),
            'selected_surface_pixels': visibility['selected_surface_pixels'], 'complete_witness': None,
            'observation_status': body['observation_status']}


def independently_count_groups(receipt, image, capture, shared):
    import numpy as np
    from PIL import Image

    read, identify = shared['read'], shared['ident']
    state = receipt['state']
    producer_path = state/'PRODUCER_01.json'
    producer = read(producer_path)
    frame, = producer['frames']
    require(frame['frame_identity'] == image['frame_identity'] and frame['image_sha256'] == image['sha256']
            and frame['pose']['direction_rational'][2] > 0, 'wrong_original_group_pixel_frame_or_direction')
    path = Path(frame['arrays_path'])
    array_pin = identify(path)
    require(array_pin['sha256'] == frame['arrays_sha256']
            and path.parent == Path(frame['image_path']).parent, 'same_sample_NPZ_identity_changed')
    by_name = {mesh['name']: mesh for mesh in capture['meshes']}
    roster = [row['object_name'] for row in producer['binding']['objects']]
    require(len(roster) == len(by_name) and set(roster) == set(by_name), 'incorrect_original_pixel_owner_roster')
    offsets = np.cumsum([0] + [len(by_name[name]['faces']) for name in roster])
    target = roster.index(TARGET)
    with np.load(BytesIO(path.read_bytes()), allow_pickle=False) as arrays:
        rgb, owners, faces = (arrays[key] for key in ('color', 'owners', 'triangle_ids'))
        require(arrays['face_patch_offsets'].tolist() == offsets.tolist()
                and owners.shape == faces.shape == (512, 512), 'incorrect_original_triangle_id_offsets')
    with Image.open(frame['image_path']) as picture:
        require(np.array_equal(np.asarray(picture), rgb), 'native_PNG_does_not_match_original_RGB')
    counts = {str(face): int(np.count_nonzero((owners == target) & (faces == offsets[target] + face)))
              for face in FACES}
    require(counts['0'] == counts['1'] == 0 and counts['8'] > 0 and counts['9'] > 0
            and sum(counts.values()) == image['selected_surface_pixels'], 'case_source_group_pixel_membership_changed')
    return {'source_triangle_owner_pixels': counts, 'NPZ': array_pin,
            'producer': identify(producer_path), 'positive_z_direction': frame['pose']['direction_rational']}


def review(output, arms, shared):
    cli = run_path(str(V/'m1_source_region_diagnostic_artifact_prototype_001/checks/cli.py'))
    helpers, _ = cli['policy']()
    capture, _ = pinned_capture()
    dependency = shared['binding_for']('A')['dependency_root']
    if dependency not in sys.path:
        sys.path.append(dependency)
    groups = {}
    rows = {}
    for arm, receipt in arms.items():
        rows[arm] = {}
        for label, slot in receipt['replies'].items():
            row = {'TX': shared['ident'](slot/'TX.bin'), 'RX': shared['ident'](slot/'RX.bin')}
            rows[arm][label] = row
            if label.endswith('invalid'):
                continue
            result, text, body, png, _ = cli['packet'](slot/'RX.bin')
            row.update(text_bytes=len(text.encode()), measurement=metric(body, label == 'whole'))
            if label in ('whole', 'no-image'):
                require(not png and (label == 'whole' or body['observation_status'] == 'image_not_requested'),
                        'held_out_no_image_call_published_image')
                continue
            image = review_image(label, body, png, receipt['state']/'product_state.json.source_region', cli['digest'])
            row.update(image=image, scope=body['region_ref'], schema=body['schema'])
            stage_root = output/'fixed_cli'/arm/label
            stage_root.mkdir(parents=True)
            row['fixed_CLI'] = cli['stages']('original_full' if label == 'full' else 'first',
                   result, text, [{'bytes': image['bytes'], 'sha256': image['sha256']}], stage_root)
            if label == 'full':
                for stage in row['fixed_CLI']:
                    left, right = stage['middle_cut']['original_cut_span_UTF8']
                    fields = stage['middle_cut']['watched_fields']
                    for key in ('visible_source_triangle_indices', 'unseen_source_triangle_indices'):
                        address = ('facts', 'visibility', key)
                        span = helpers['path_byte_span'](text, address)
                        fields['.'.join(address)] = {'original_byte_span': [span['start'], span['end']],
                                                     'whole_field_retained': span['end'] <= left or span['start'] >= right}
        groups[arm] = independently_count_groups(receipt, rows[arm]['brief']['image'], capture, shared)

    a, b = rows['A'], rows['B']
    require(arms['A']['catalogue'] == [tool for tool in arms['B']['catalogue'] if tool['name'] != shared['NEW']],
            'held_out_normal_catalogue_changed_prior_definition')
    require(all(row['measurement'] == a['brief']['measurement'] and row['scope'] == a['brief']['scope']
                and all(row['image'][key] == a['brief']['image'][key] for key in
                        ('sha256', 'frame_identity', 'image_ref', 'selected_surface_pixels', 'complete_witness'))
                for row in (a['full'], b['brief'], b['full'], b['narrow'])),
            'held_out_same_producer_changed_measurement_or_sample')
    brief_rows = (a['brief'], b['brief'], b['narrow'])
    path_both = all(row['image']['path_opened_exact_bytes'] for row in brief_rows)
    complete_cli = all(stage['all_items_exact'] and stage['native_PNG_exact']
                       for row in brief_rows for stage in row['fixed_CLI'])
    original_png_retained = all(stage['native_PNG_exact'] for row in (a['full'],b['full']) for stage in row['fixed_CLI'])
    return {'passed': path_both and complete_cli and original_png_retained,
            'brief_openable': path_both, 'brief_fixed_CLI_exact': complete_cli, 'full_native_PNG_retained': original_png_retained,
            'independent_source_groups': groups,
            'catalogues': {arm: {'count': len(items['catalogue']), 'bytes': len(shared['encoded'](items['catalogue']))}
                            for arm, items in arms.items()}, 'cases': rows,
            'offline_only': True, 'owned_Blender': 0, 'models': 0}


def main(output, retained=None):
    shared = replay_tools()
    output.mkdir(parents=True)
    output = output.resolve(strict=True)
    transport = run_path(str(V/'m4_global_local_qualification_001/harness/reused/stdio_checks.py'))['StdioClient']
    deadline = perf_counter_ns() + 150_000_000_000
    arms = {}
    for arm in ('A', 'B'):
        if retained is None:
            arms[arm] = probe(arm, output/arm, shared, transport, deadline)
        else:
            items = shared['archived_probe'](retained/arm)
            items['replies'] = {label: path.parent for label, path in items['replies'].items()}
            arms[arm] = items
    verdict = review(output, arms, shared)
    shared['save'](output/'PRODUCT_REPLAY.json', verdict)
    print({k: v for k, v in verdict.items() if k not in ('cases', 'independent_source_groups')})
    return 0 if verdict['passed'] else 1


if __name__ == '__main__':
    require(sys.flags.isolated and sys.dont_write_bytecode, 'held_out_requires_pinned_interpreter_I_B')
    if len(sys.argv) == 4 and sys.argv[1] == '--worker':
        worker(sys.argv[2], Path(sys.argv[3]))
    else:
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument('output', type=Path)
        parser.add_argument('--retained', type=Path)
        args = parser.parse_args()
        raise SystemExit(main(args.output, args.retained))
