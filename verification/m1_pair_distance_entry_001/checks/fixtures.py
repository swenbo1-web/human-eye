"""Read the owned original current captures and prove source, ordering and surface truth."""

from fractions import Fraction
from hashlib import sha256
import json
from math import isclose, sqrt
from pathlib import Path
from runpy import run_path


P2 = 'perf050_target_observation_first_image_p2'
P3 = 'perf050_source_region_final_image_p3'
OLD_M09 = 'm4_cross_scale_live_task_formal_001'
WINDOWS = 'm1_target_observation_first_image_path_windows_001'
REPLAY_P3 = 'm1_source_region_final_image_001'
AREAS = {
    'N15': {'run': P3, 'label': 'P3', 'pair': ['N15', 'N23'], 'legal_attempt': 5, 'producer': 3,
            'wire': '2363439f0bb573fdd160a424f5307c8198f3b7912935be2720fcbb5126eb7cab', 'files': 268,
            'source_install': REPLAY_P3 + '/install/PRODUCT_RUN_BINDING.json', 'counts': [28, 416, 744]},
    'M09': {'run': P2, 'label': 'P2', 'pair': ['M09', 'M03'], 'legal_attempt': 3, 'producer': 2,
            'wire': 'f675d00775e16397d1802339f9b994a44d39a5e34048dd678e3a952872e439ce', 'files': 210,
            'source_install': WINDOWS + '/install/PRODUCT_RUN_BINDING.json', 'counts': [21, 148, 184]},
}


def require(value, reason):
    if not value:
        raise ValueError(reason)


def read(path):
    return json.loads(Path(path).read_bytes())


def pin(path):
    p = Path(path).resolve()
    raw = p.read_bytes()
    return {'path': str(p), 'sha256': sha256(raw).hexdigest(), 'bytes': len(raw)}


def exact_geometry(rows):
    return {row['name']: (
        row['vertices'], row['faces']
    ) for row in rows}


def bind_terminal(terminal):
    return {row['name']: (
        row['evaluated']['vertices_world_m'], row['evaluated']['triangles']
    ) for row in terminal['objects']}


class Adapter:
    def __init__(self, sealed):
        self.sealed = sealed

    def read(self, path, digest=None, within=None):
        path = Path(path).resolve()
        require(within is None or path.is_relative_to(within.resolve()), 'native_packet_outside_archived_slot')
        raw = self.sealed.member(path)
        require(digest is None or sha256(raw).hexdigest() == digest, 'native_packet_digest_changed')
        return json.loads(raw)

    check = staticmethod(require)


def capture_current(terms, selected, parent):
    rows = {row['name']: row for row in terms['objects']}
    require(exact_geometry(parent['meshes']) == bind_terminal(terms)
            and all(selected['capture_state'][key] == parent['capture_state'][key]
                    for key in ('instance_id', 'epoch', 'revision'))
            and selected['host_identity']['document_epoch'] == parent['host_identity']['document_epoch'],
            'current_full_or_selected_generation_does_not_match_its_terminal_capture')
    terminal_mesh = bind_terminal(terms)
    for mesh in selected['meshes']:
        row = rows[mesh['name']]
        require((mesh['vertices'], mesh['faces']) == terminal_mesh[mesh['name']]
                and selected['host_identity']['object_instances'][mesh['object_id']] == row['instance_id']
                and row['object_id'] == mesh['object_id'], 'selected_current_geometry_or_instance_changed')


def m09_parent(v, captured, decoder, archive_module):
    old = v / OLD_M09 / 'RUNTIME_INDEX.json'
    root = Path('D:/he_' + OLD_M09)
    slot = root / 'slots/P1'
    identity = v / 'm4_live_assembly_relation_task_001/PRODUCT_RUN_BINDING.json'
    pointer = read(old)
    with archive_module['Archive'](root, old, '38be66d67b301524de5594acab12158342da7c31e2aa75629109e2fe4ff8a89d',
                                   pointer['count']) as arc:
        owner = arc.json(slot / 'product_full/call_001/SERVICE_RESULT.json')
        adapter = Adapter(arc)
        sources, _ = decoder['decode_captures'](slot, read(identity), adapter)
        complete = decoder['current_capture'](sources, owner['binding'], adapter)
        terminal = arc.json(slot / 'TERMINAL_SOURCE.json')
        require(exact_geometry(complete['meshes']) == bind_terminal(terminal) == bind_terminal(captured),
                'older_full_M09_archive_differs_from_current_P2_meshes')
        return complete, list(arc.pins.values()) + [pin(identity)]


def fixture(v, name):
    from copy import deepcopy
    case = AREAS[name]
    key, slot_name = case['run'], case['label']
    namespace = v / key
    root = Path('D:/he_' + key)
    slot = root / 'slots' / slot_name
    archive_file = v / P2 / 'harness/archives.py'
    archives = run_path(str(archive_file))
    decoder_file = v / 'm4_cross_scale_discovery_001/oracle/check_saved.py'
    decoder = run_path(str(decoder_file))
    binding_file = v / case['source_install']
    source_install = read(binding_file)
    with archives['Archive'](root, namespace / 'RUNTIME_INDEX.json', case['wire'], case['files']) as arc:
        capture_terminal = arc.json(slot / 'TERMINAL_SOURCE.json')
        capture_initial = arc.json(slot / 'initial_capture/TERMINAL_SOURCE.json')
        results = arc.json(slot / 'SLOT_RESULT.json')
        publication = arc.json(slot / 'SLOT_PUBLICATION.json')
        result_identity = pin(slot / 'SLOT_RESULT.json')
        require(capture_terminal['objects'] == capture_initial['objects']
                and capture_terminal['display_object_mask'] == capture_initial['display_object_mask']
                and results['independent_before_after']['passed'] and results['closure_verification']['passed']
                and publication['result_sha256'] == result_identity['sha256']
                and results['status'] == publication['status'] == 'completed'
                and results['product_source_sha256'] == source_install['source_sha256'], 'original_scene_or_close_changed')
        producer = arc.json(slot / f"product_full/call_{case['producer']:03}/SERVICE_RESULT.json")
        binding = producer['binding']
        legal = case['legal_attempt']
        text = arc.json(slot / f'owner/tool_{legal:02}/PRODUCT_RESPONSE.json')['result']
        require(not text['isError'] and len(text['content']) == 1 and json.loads(text['content'][0]['text']) == producer,
                'actual_legal_set_wire_not_original_producer')
        contracts = arc.json(slot / 'consumer/BUSINESS_SOURCE_BINDING.json')['result_contracts']
        events = archives['rows'](arc.member(slot / 'consumer/stdout.raw.bin'))
        request, actual_response, receipt = archives['outer_packet'](arc, 'slots/' + slot_name, legal, contracts, events)
        selectors = [{'name': n} for n in case['pair']]
        query = {'mode': 'task', 'target': selectors[0], 'candidates': selectors[1:],
                 'requested_facts': ['surface_proximity', 'spatial_relation']}
        require(request['params']['arguments']['query'] == query and actual_response['result'] == text
                and producer['schema_version'] == 'task-query-set-v2'
                and producer['binding']['capture_scope'] == 'selected_objects',
                'actual_legal_selected_query_changed')
        adapter = Adapter(arc)
        scopes, commands = decoder['decode_captures'](slot, source_install, adapter)
        ready = [cap for cap in scopes if cap['revision'] == binding['scene_revision']
                 and cap['capture_scope'] == binding['capture_scope']]
        require(ready and all(candidate == ready[0] for candidate in ready), 'selected_original_capture_ambiguous')
        selected = ready[0]
        require(selected['host_identity'] == binding['host_identity'], 'selected_host_identity_changed')
        current_commands = [row['command']['params']['selectors'] for row in commands
                            if row['command']['command'] == 'capture_task']
        require(selectors in current_commands and [mesh['name'] for mesh in selected['meshes']] == case['pair'],
                'actual_selected_task_capture_missing_or_wrong_order')
        parents = [row for row in scopes if row.get('capture_scope', 'complete_scene_meshes') == 'complete_scene_meshes']
        if parents:
            parent = parents[0]
            require(all(exact_geometry(row['meshes']) == exact_geometry(parent['meshes']) for row in parents),
                    'ambiguous_complete_current_fixture')
            capture_current(capture_terminal, selected, parent)
            extra = []
        else:
            require(name == 'M09', 'current_N15_full_native_source_missing')
            parent, extra = m09_parent(v, capture_terminal, decoder, archives)
            ids = {row['name']: row for row in capture_terminal['objects']}
            require(all((m['vertices'], m['faces']) == bind_terminal(capture_terminal)[m['name']]
                        and m['object_id'] == ids[m['name']]['object_id']
                        and selected['host_identity']['object_instances'][m['object_id']] == ids[m['name']]['instance_id']
                        for m in selected['meshes']), 'current_M09_selected_not_identical_to_full_ordered_geometry')
        meshes = parent['meshes']
        require([len(meshes), sum(len(m['vertices']) for m in meshes), sum(len(m['faces']) for m in meshes)]
                == case['counts'], 'complete_source_geometry_denominators_changed')
        return {'parent': parent, 'selected': selected, 'archive_result': producer,
                'archive_legal_attempt': receipt, 'case': case, 'terminal': capture_terminal,
                'pins': list(arc.pins.values()) + extra + [pin(path) for path in (
                            archive_file, decoder_file, binding_file)]}


def truth(v, name, item):
    item_meshes = {row['name']: row for row in item['parent']['meshes']}
    pair = item['case']['pair']
    assembled = [{'name': label, 'vertices': [tuple(map(Fraction, point)) for point in item_meshes[label]['vertices']],
                  'triangles': item_meshes[label]['faces']} for label in pair]
    if name == 'N15':
        path = v / 'perf050_readonly_product_pilot_001/truth/oracle.py'
        data = run_path(str(path))['independent_measurement'](assembled)
        return {'distance_m': data['distance_m'], 'delta': data['displacement_exact_m'],
                'direction': data['direction_a_to_b_world'], 'pins': [pin(path)], 'independent': data}
    path = v / 'perf050_readonly_product_transfer_001/truth/oracle.py'
    data = run_path(str(path))['compute']()['measurement']
    expected = Fraction(15, 64)
    left, right = assembled
    require(max(p[2] for p in left['vertices']) == Fraction(65, 64)
            and max(p[2] for p in right['vertices']) == Fraction(5, 4)
            and Fraction(data['distance_m']) == expected, 'M09_independent_oracle_truth_changed')
    return {'distance_m': float(expected), 'delta': ['0', '0', str(expected)], 'direction': [0, 0, 1],
            'pins': [pin(path)], 'independent': data}


def check_witness(witness, facts, closure, prepared, v, *, reverse=False):
    near = lambda a, b: isclose(float(a), float(b), rel_tol=0, abs_tol=1e-12)
    coords = [tuple(map(Fraction, witness[end])) for end in ('a', 'b')]
    delta = [b-a for a, b in zip(*coords, strict=True)]
    check_path = v / 'm5_observe_measure_001/oracle.py'
    membership = run_path(str(check_path))['membership']
    terminal = {row['name']: row['evaluated'] for row in prepared['terminal']['objects']}
    labels = prepared['case']['pair'][::-1] if reverse else prepared['case']['pair']
    proof = [membership(point, terminal[label]['vertices_world_m'], terminal[label]['triangles'])
             for point, label in zip(coords, labels, strict=True)]
    sign = -1 if reverse else 1
    expected_distance = closure['distance_m']
    require(all(row['within_publication_tolerance_source_triangle_indices'] for row in proof)
            and all(near(actual, sign * Fraction(expected)) for actual, expected in zip(delta, closure['delta'], strict=True))
            and all(near(a, sign*b) for a, b in zip(witness['direction_a_to_b'], closure['direction'], strict=True))
            and near(sqrt(float(sum(x*x for x in delta))), expected_distance)
            and near(facts, expected_distance), 'pair_distance_direction_or_source_membership_wrong')
    return {'points': witness, 'proof': proof, 'ordered_delta_m': list(map(str, delta)), 'pin': pin(check_path)}
