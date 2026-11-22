"""Recover formal quality evidence from unchanged final text and held, closed wires."""

from functools import lru_cache
import json
from pathlib import Path
from runpy import run_path
import sys
from types import SimpleNamespace
from urllib.parse import unquote, urlsplit


HERE = Path(__file__).resolve().parent
NS, V = HERE.parent, HERE.parents[1]
ORIGINAL = V / 'm1_region_task_first_packet_consumption_holdout_001'
BINDING = V / 'm3_whole_object_rounded_witness_compat_001/install/PRODUCT_RUN_BINDING.json'
ORIGINAL_BINDING = V / 'm1_region_task_first_packet_projection_001/install/PRODUCT_RUN_BINDING.json'


@lru_cache(maxsize=None)
def module(path):
    return run_path(str(path))


E = module(ORIGINAL / 'checks/evidence.py')
D = module(V / 'perf050_dense_micro_surface_holdout_recovery_001/checks/evidence.py')
W = module(V / 'm1_region_task_witness_image_path_001/checks/evidence.py')
require, read, pin, digest = (E[key] for key in ('require', 'read', 'pin', 'digest'))
ERRORS = (ValueError, KeyError, IndexError, TypeError, OSError, ArithmeticError)


def source_captures(slot, installed, source):
    checker = module(V / 'm4_cross_scale_discovery_001/oracle/check_saved.py')
    audit = checker['Audit']()
    captures, commands = checker['decode_captures'](slot, installed, audit)
    meshes = {row['name']: row for row in source['objects']}
    require(len(meshes) == len(source['objects']), 'ambiguous_current_terminal_roster')
    for capture in captures:
        for mesh in capture['meshes']:
            evaluated = meshes[mesh['name']]
            require(mesh['object_id'] == evaluated['object_id']
                    and capture['host_identity']['object_instances'][mesh['object_id']] == evaluated['instance_id']
                    and mesh['vertices'] == evaluated['evaluated']['vertices_world_m']
                    and mesh['faces'] == evaluated['evaluated']['triangles'],
                    'installed_capture_differs_from_closed_evaluated_source/' + mesh['name'])
    return checker, audit, captures, commands


def material(slot, source, installed, tools):
    """Correlate per-call user-facing replies and original installed producer receipts."""
    product = {}
    diagnostics = []
    if not any(row.get('product') for row in tools['attempts']):
        return product, diagnostics, []
    checker, audit, captures, commands = source_captures(slot, installed, source)
    for row in tools['attempts']:
        held = (row.get('product') or {}).get('producer_delivery')
        if held is None or row['is_error'] or not row['model_visible_as_public_CLI_tool_result']:
            continue
        try:
            producer = read(held['path']['path'])
            response = read(row['RX']['path'])
            package = {'producer': producer, 'reply': response, 'packet': E['document'](response)}
            parent = producer['binding']
            capture = checker['current_capture'](captures, parent, audit)
            if producer.get('facts', {}).get('region_task') and parent['capture_scope'] == 'complete_scene_meshes':
                checker['source_binding_checks'](capture, parent, installed, audit)
            require(parent['runtime_source_sha256'] == installed['source_sha256'],
                    'packet_runtime_install_differs')
            package['capture'] = capture
            if package['packet'].get('schema') == E['BRIEF']:
                paths = {frame['image_ref']: pin(frame['image_path'], slot) for frame in producer['frames']}
                package['public_witnesses'] = W['verify_public_witnesses'](
                    response, producer, slot=slot, authoritative_paths=paths)
            product[row['attempt']] = package
        except ERRORS as error:
            diagnostics.append({'attempt': row['attempt'], 'issue': str(error)})
    return product, diagnostics, commands


def native_verify(slot, row, target, source, truth):
    native = module(V / 'perf050_dense_micro_surface_holdout_001/qualification/native.py')
    owner = SimpleNamespace(runtime=SimpleNamespace(device=SimpleNamespace(by_ref={row['ref']: row})))
    return native['prove_image'](slot, owner, row['ref'], target, source=source, geometry=truth)


def product_verify(slot, row, target, source, truth, package):
    producer = package['producer']
    frame, = [f for f in producer['frames'] if f['image_ref'] == row['ref']]
    scope = next((item['binding'] for item in producer.get('scopes', [])
                  if item['scope_id'] == row['scope_id']), producer['binding'])
    parent = producer['binding'] if scope.get('capture_scope') == 'same_capture_region_view' else None
    return module(V / 'perf050_dense_micro_surface_holdout_recovery_001/qualification/frame.py')['prove_frame'](
        slot, row, frame, scope, package['capture'], source, target, geometry=truth, parent=parent)


def normalize_link(spelling):
    lowered = spelling.casefold()
    if lowered.startswith('file://'):
        url = urlsplit(spelling)
        if url.netloc or url.query or url.fragment:
            return None
        spelling = url.path.lstrip('/')
    p = Path(unquote(spelling))
    return p.resolve() if p.is_absolute() else None


def frames_for_answer(slot, answer, tools, products, source, truth):
    manifest = read(slot / 'DEVICE_EVIDENCE.json')
    require(manifest['label'] == slot.name and manifest['asset_sha256'] == truth['asset']['sha256'],
            'frame_inventory_outside_current_asset_and_slot')
    frames = manifest['frames']
    deliveries = D['frame_deliveries'](slot, frames, tools)
    for attempt, package in products.items():
        for path in (package.get('public_witnesses') or {}).get('paths', []):
            ref = path['image_ref']
            owners = [hit for hit in deliveries[ref] if hit['attempt'] == attempt]
            require(len(owners) == 1, 'witness_path_lacks_own_actual_public_image_block')
            owners[0]['witness_local_path'] = path['path']
    links = module(V / 'm1_source_region_first_packet_consumption_001/checks/score.py')['final_links']
    paths = {link: normalize_link(link) for link in dict.fromkeys(links(answer))}
    available = {}
    for row in frames:
        ref = row['ref']
        hits = deliveries[ref]
        if not hits:
            continue
        png = pin(row['PNG'], slot)
        if not any(path is not None and path == Path(png['path']) for path in paths.values()) and ref not in answer:
            continue
        scores = {}
        for role in ('R', 'Q'):
            target = truth['roles'][role]
            try:
                if row['origin'] == 'product':
                    packages = [p for p in products.values() if any(
                        frame['image_ref'] == ref and frame['scope_id'] == row['scope_id']
                        for frame in p['producer'].get('frames', []))]
                    require(packages, 'no_bound_current_producer_of_final_frame')
                    scores[role] = product_verify(slot, row, target, source, truth, packages[0])
                else:
                    require(row['origin'] == 'common_native', 'unknown_owned_original_image_route')
                    scores[role] = native_verify(slot, row, target, source, truth)
            except ERRORS as error:
                scores[role] = {'complete': False, 'issue': str(error)}
        available[ref] = {'by_role': scores, 'post_close_png': png, 'actual_deliveries': hits,
                          'frame_ref': ref, 'origin': row['origin'], 'scope_id': row['scope_id']}
    linked = {}
    for spelling, path in paths.items():
        candidates = [entry for entry in available.values() if Path(entry['post_close_png']['path']) == path]
        if len(candidates) == 1:
            linked[spelling] = candidates[0]
    return available, linked


def model_facts(tools, products, source, truth):
    matches, aliases, facts = [], {}, []
    for row in tools['attempts']:
        ordinal = row['attempt']
        package = products.get(ordinal)
        if package is None:
            continue
        producer, packet = package['producer'], package['packet']
        args = read(row['TX']['path'])['params']['arguments']
        query = args.get('query') or {}
        region_task = producer.get('facts', {}).get('region_task') or {}
        if (query.get('mode') == 'active_observation' and query.get('region_task') == E['CONDITIONS']
                and args.get('include_image', True) and not query.get('objects')
                and producer['binding']['capture_scope'] == 'complete_scene_meshes'):
            matching_roi = []
            for region in region_task.get('rows', []):
                name = region['object_name']
                truth_region = truth['regions'].get(name)
                if truth_region and region['source_triangle_indices'] == truth_region['source_triangle_indices']:
                    aliases.setdefault(name, {})[region['roi_id']] = region['source_triangle_indices']
                    matching_roi.append(name)
            brief = packet.get('schema') == E['BRIEF']
            require(not brief or package.get('public_witnesses'), 'brief_task_missing_public_scope_verification')
            if not brief:
                require(packet.get('frames') == producer['frames'] and
                        packet.get('facts', {}).get('region_task') == region_task,
                        'full_discovery_public_facts_or_frames_differ_from_producer')
            matches.append({'attempt': ordinal, 'projection': 'brief' if brief else 'full',
                            'original_arguments': args, 'published_body_sha256': digest(
                                package['reply']['result']['content'][0]['text'].encode()),
                            'original_text_bytes': row['text_UTF8_bytes'], 'actual_images': row['image_blocks'],
                            'original_packet': row['RX'], 'fixed_history_whole': row.get('fixed_history_whole'),
                            'matching_source_objects': matching_roi,
                            'public_witnesses': package.get('public_witnesses')})
            if set(matching_roi) == set(truth['regions']):
                facts.append({'kind': 'discovery', 'attempt': ordinal, 'objects': matching_roi})
            blockers = region_task.get('blocker_evidence', [])
            if blockers:
                proof = E['verify_blockers'](packet, region_task, producer['binding'], source, truth)
                facts.append({'kind': 'occlusion', 'attempt': ordinal, 'objects': [truth['roles']['P']], 'proof': proof})
        if query.get('mode') == 'source_region':
            task = packet.get('task_result', packet)
            ref = packet.get('region_ref', task.get('region_ref'))
            target = truth['roles']['P']
            fact = task.get('facts', {}).get('surface_proximity', {})
            requested = task.get('reference') or {}
            if (fact.get('status') == 'measured' and ref
                    and requested.get('name') == truth['measurement']['reference']
                    and ref['source_triangle_indices'] == truth['regions'][target]['source_triangle_indices']):
                objects = {obj['name']: obj for obj in source['objects']}
                own, destination = objects[target], objects[requested['name']]
                binding, original = producer['binding'], producer['task_result']
                require(ref == producer['region_ref'] == original['region_ref']
                        and fact == original['facts']['surface_proximity']
                        and requested == original['reference']
                        and task['measurement_scope'] == original['measurement_scope']
                        == 'complete_selected_source_triangle_union_to_reference_triangle_surface'
                        and ref['host_id'] == own['object_id'] and ref['instance_id'] == own['instance_id']
                        and requested['object_id'] == destination['object_id']
                        and requested['instance_id'] == destination['instance_id']
                        and ref['document_epoch'] == binding['document_epoch']
                        and all(ref['capture_generation'][key] == binding['capture_state'][key]
                                for key in ('instance_id', 'epoch', 'revision')),
                        'source_region_public_scope_instance_or_generation_does_not_match_producer')
                witness = fact['value']['nearest_witness']
                m = {'object_name': target, 'reference': requested['name'], 'distance_m': fact['value']['distance_m'],
                     'a': witness['a'], 'b': witness['b'], 'direction_world': witness['direction_a_to_b']}
                facts.append({'kind': 'measurement', 'attempt': ordinal, 'objects': [target],
                              'proof': E['measured'](m, source, truth), 'requested_measurement': m})
    return matches, aliases, facts


def load_slot(slot, truth_file=None, *, binding_path=BINDING):
    slot = Path(slot).resolve(strict=True)
    truth = E['normalize_truth'](truth_file or ORIGINAL / 'fixture/TRUTH.json')
    installed = read(binding_path)
    shared = read(V / 'm5_harness_recovery_001/SHARED_DEPENDENCY.json')
    for path in (installed['dependency_root'], shared['dependency_root']):
        if path not in sys.path:
            sys.path.insert(0, path)
    raw, pub = D['publication'](slot)
    require(raw['status'] == pub['status'] == 'completed' and raw['model_consumers'] == 1,
            'no_completed_formal_consumer_to_score')
    source, closure = E['verify_closed'](slot, raw, truth)
    answer = D['closed_answer'](slot, raw)
    tools = E['public_tools'](slot, pub)
    product, packet_issues, commands = material(slot, source, installed, tools)
    frames, linked = frames_for_answer(slot, answer['text'], tools, product, source, truth)
    matches, aliases, facts = model_facts(tools, product, source, truth)
    return {'slot': slot.name, 'answer': answer, 'closed_source': closure, 'available_frames': frames,
            'link_frames': linked, 'truth': truth, 'source': source, 'actual_attempts': tools['attempts'],
            'first_matching_task': matches[0] if matches else None, 'matching_task_requests': matches,
            'budget': raw['budget'], 'roi_aliases': aliases, 'verified_product_facts': facts,
            'packet_issues': packet_issues, 'decoded_product_host_commands': commands}
