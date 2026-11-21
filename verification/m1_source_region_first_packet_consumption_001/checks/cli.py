"""Audit the installed A/B first packets through the frozen CLI content budgets."""

import argparse
import json
from functools import lru_cache
from math import isclose
from pathlib import Path
from runpy import run_path
import sys


V = Path(__file__).resolve().parents[2]
PRIOR = V / 'm1_source_region_diagnostic_artifact_prototype_001/checks'
REGION = 'Obj_09'
REFERENCE = 'Obj_04'
SOURCE_SHA = '65bd1ec8009f8024e85ef1cd30c1229957cceb1c1766c8e5b62f2ef2489ce48c'
FULL_SCHEMA = 'human-eye-source-region-observation-v1'
BRIEF_SCHEMA = 'source-region-brief-v3'
MEASUREMENT_SCOPE = 'complete_selected_source_triangle_union_to_reference_triangle_surface'
INDEX_DOMAIN = 'zero_based_object_local_current_evaluated_capture_triangle_rows'
GENERATION = ('instance_id', 'epoch', 'revision')
IMAGE_IDENTITY = ('view_name', 'frame_identity', 'image_ref', 'image_sha256',
                  'host_binding_sha256', 'display_identity', 'image_scope_identity')
FACT = ('task_result', 'facts', 'surface_proximity', 'value')
FACT_SPANS = (('region_ref',), ('task_result', 'reference'), ('task_result', 'measurement_scope'),
              FACT + ('distance_m',), FACT + ('nearest_witness',),
              ('task_result', 'source_mapping', 'nearest_witness'), ('binding', 'binding_sha256'),
              ('binding', 'source_binding_sha256'))


@lru_cache(maxsize=1)
def verifier():
    return run_path(str(PRIOR / 'cli.py'))


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def verify_measurement(body):
    task = body['task_result']
    require(task['reference']['name'] == REFERENCE and task['measurement_scope'] == MEASUREMENT_SCOPE,
            'measurement_reference_or_scope_changed')
    fact = task['facts']['surface_proximity']
    require((fact['status'], fact['witness_status'], fact['direction_status']) ==
            ('measured', 'measured', 'measured'), 'expected_measured_distance_and_direction')
    value = fact['value']
    nearest = value['nearest_witness']
    a, b, direction = nearest['a'], nearest['b'], nearest['direction_a_to_b']

    # Independent bounds from the frozen Q1 evaluated vertices. The nearest edge of
    # Obj_09 lies at x=-33/16 on z=1+y/3. Obj_04 is the rectangle at x=-4.
    def equal(left, right):
        return isclose(left, right, rel_tol=0, abs_tol=1e-12)

    require(len(a) == len(b) == len(direction) == 3
            and equal(value['distance_m'], 31 / 16)
            and all(equal(actual, target) for actual, target in zip(direction, (-1, 0, 0)))
            and equal(a[0], -33 / 16) and -3 / 64 <= a[1] <= 3 / 64
            and equal(a[2], 1 + a[1] / 3)
            and equal(b[0], -4) and -1 / 16 <= b[1] <= 1 / 16 and 15 / 16 <= b[2] <= 17 / 16
            and equal(a[1], b[1]) and equal(a[2], b[2]), 'incorrect_independent_nearest_surface_witness')
    memberships = task['source_mapping']['nearest_witness']
    for point in ('a', 'b'):
        member = memberships[point]
        indices = member['source_triangle_indices']
        require(member['status'] == 'measured' and member['exact_membership'] is True
                and member['index_domain'] == INDEX_DOMAIN and bool(indices) and set(indices) <= {0, 1},
                'nearest_witness_missing_current_surface_membership/' + point)
    return {'distance_m': value['distance_m'], 'direction_world': direction, 'nearest_points_world_m': [a, b]}


def inspect_packet(arm, body, png, expected_image_root, digest):
    brief = arm == 'B'
    require(arm in ('A', 'B') and body['schema'] == (BRIEF_SCHEMA if brief else FULL_SCHEMA)
            and body['result_kind'] == 'source_region'
            and body['status'] == 'complete' and body['observation_status'] == 'locally_observed'
            and body['read_only'] is True and 'diagnostic_artifact' not in body,
            'unexpected_first_packet_shape_or_scope/' + arm)
    ref, binding = body['region_ref'], body['binding']
    generation = ref['capture_generation']
    require(ref['schema'] == 'human-eye-source-region-ref-v1' and ref['source_triangle_indices'] == [0, 1]
            and all(key in generation for key in GENERATION) and binding['runtime_source_sha256'] == SOURCE_SHA,
            'source_ref_or_installation_mismatch/' + arm)
    region, visibility, scope = (
        (body['region'], body['visibility'], body['image_scope']) if brief else
        (body['facts']['region'], body['facts']['visibility'], binding['image_scope']))
    require((region['object_name'], region['host_id'], region['instance_id'], region['index_domain']) ==
            (REGION, ref['host_id'], ref['instance_id'], INDEX_DOMAIN)
            and scope['scope'] == 'active_view_layer_effective_viewport' and scope['status'] == 'captured'
            and len(scope['participating_object_indices']) == 9 and not scope['excluded_object_indices'],
            'missing_selected_region_or_full_scene_occlusion_scope/' + arm)
    if brief:
        require(region['source_triangle_count'] == visibility['visible_source_triangle_count'] == 2
                and visibility['unseen_source_triangle_count'] == 0, 'brief_does_not_cover_entire_selection')
    else:
        require(region['source_triangle_indices'] == visibility['visible_source_triangle_indices'] == [0, 1]
                and not visibility['unseen_source_triangle_indices'] and body['task_result']['region_ref'] == ref
                and binding['document_epoch'] == ref['document_epoch']
                and all(binding['capture_state'][key] == generation[key] for key in GENERATION),
                'full_does_not_cover_entire_current_selection')

    frame, = body['images' if brief else 'frames']
    raw, = png
    witness = visibility['complete_witness']
    require(all(witness[key] == frame[key] for key in ('view_name', 'frame_identity', 'image_ref'))
            and visibility['geometry_status'] == witness['geometry_status'] == 'complete'
            and witness['selected_surface_pixels'] == visibility['selected_surface_pixels'] >= 16
            and witness['contrasting_boundary_pixels'] == visibility['contrasting_boundary_pixels'] >= 4
            and frame['host_binding_sha256'] == binding['binding_sha256']
            and frame['display_identity'] == scope['identity']
            and frame['image_sha256'] == digest(raw) and body['image_delivery']['mcp_content_constructed_image_count'] == 1,
            'missing_or_wrong_bound_complete_image_witness/' + arm)
    if brief:
        require(frame['image_block_index'] == 1, 'brief_points_to_wrong_mcp_image_block')
    path_value = frame.get('local_image_path') if brief else frame['image_path']
    require(type(path_value) is str and path_value, 'missing_openable_image_path/' + arm)
    path = Path(path_value)
    require(path.is_absolute() and not path.as_posix().startswith('//') and path.suffix == '.png'
            and path.resolve(strict=True).as_posix() == path.as_posix() and path.is_file()
            and (not brief or path_value == path.as_posix()), 'noncanonical_local_image_path/' + arm)
    if expected_image_root is not None:
        slot = Path(expected_image_root).resolve(strict=True)
        root = slot if slot.name == 'product_state.json.source_region' else slot / 'product_state.json.source_region'
        require(root.resolve(strict=True).as_posix() == root.as_posix() and path.is_relative_to(root)
                and len(path.relative_to(root).parts) == 2,
                'image_does_not_belong_to_this_run/' + arm)
    require(path.read_bytes() == raw, 'image_file_bytes_differ_from_native_block/' + arm)
    return {'schema': body['schema'], 'binding_sha256': binding['binding_sha256'],
            'source_binding_sha256': binding['source_binding_sha256'], 'region_ref': ref,
            'frame': {key: frame[key] for key in IMAGE_IDENTITY},
            'complete_witness': witness, 'local_image_path': path.as_posix(),
            'image_path_in_original_body': path_value,
            'checked_image_root': None if expected_image_root is None else root.as_posix(),
            'select_to_object_measurement': verify_measurement(body)}


def truncation(body, retained, original, helpers, previous):
    marker, = previous['TRUNCATION'].finditer(retained)
    prefix, suffix = retained[:marker.start()], retained[marker.end():]
    require(original.startswith(prefix) and original.endswith(suffix), 'unexpected_CLI_body_truncation')
    left, right = len(prefix.encode()), len(original.encode()) - len(suffix.encode())
    visibility = ('facts', 'visibility') if body['schema'] == FULL_SCHEMA else ('visibility',)
    watched = FACT_SPANS + (visibility + ('complete_witness',),
                            ('frames' if body['schema'] == FULL_SCHEMA else 'images',))
    fields = {}
    for field in watched:
        span = helpers['path_byte_span'](original, field)
        fields['.'.join(field)] = {'original_byte_span': [span['start'], span['end']],
                                  'whole_field_retained': span['end'] <= left or span['start'] >= right}
    return {'original_cut_span_UTF8': [left, right], 'original_bytes_cut': right - left,
            'replacement_marker': marker.group(), 'watched_fields': fields}


def inspect_arm(arm, packet_source, *, raw_output=None, expected_image_root=None):
    previous = verifier()
    helpers, policy = previous['policy']()
    digest, encoded = previous['digest'], previous['encoded']
    response, text, body, png, wire = previous['packet'](packet_source)
    delivery = inspect_packet(arm, body, png, expected_image_root, digest)
    image = [{'bytes': len(item), 'sha256': digest(item)} for item in png]
    output = None if raw_output is None else Path(raw_output)
    if output is not None:
        output.mkdir(parents=True, exist_ok=False)
    rows = []
    for seconds, header_bytes in previous['HEADERS']:
        source = helpers['model_items'](response, seconds)
        require(len(source[0]['text'].encode()) == header_bytes, 'pinned_CLI_tool_title_width_changed')
        first = helpers['truncate_items'](source, policy['MCP_bytes'])
        second = helpers['truncate_items'](first, policy['history_approximate_tokens'], token_mode=True)
        for stage, items in (('MCP', first), ('history', second)):
            caption, body_text = [item['text'] for item in items if item['type'] == 'input_text']
            require(caption == source[0]['text'], 'pinned_CLI_tool_title_changed')
            image_exact = previous['retained_image_identity'](items) == image
            raw = encoded(items)
            exact = items == source
            raw_body = body_text.encode()
            row = {'header_bytes': header_bytes, 'stage': stage, 'body_UTF8_bytes': len(raw_body),
                   'body_sha256': digest(raw_body),
                   'items_sha256': digest(raw), 'all_items_exact': exact, 'native_PNG_exact': image_exact,
                   'image_path_retained': json.dumps(delivery['image_path_in_original_body'], ensure_ascii=False) in body_text}
            if body_text != text:
                row['middle_cut'] = truncation(body, body_text, text, helpers, previous)
            if output is not None:
                path = output / f'{header_bytes}_{stage}.json'
                with path.open('xb') as stream:
                    stream.write(raw)
                row['raw_stage'] = {'name': path.name, 'bytes': len(raw), 'sha256': digest(raw)}
            rows.append(row)
    return {'arm': arm, 'wire_bytes': None if wire is None else len(wire),
            'wire_sha256': None if wire is None else digest(wire),
            'body_UTF8_bytes': len(text.encode()), 'body_sha256': digest(text.encode()),
            'native_PNG': image, 'delivery': delivery, 'stages': rows,
            'passed': all(row['native_PNG_exact'] and (arm == 'A' or row['all_items_exact']) for row in rows)}


def audit(full_packet, brief_packet, *, raw_output=None, expected_image_root=None):
    """Require same-generation full/brief original witness and no loss in B."""
    output = None if raw_output is None else Path(raw_output)
    a = inspect_arm('A', full_packet, raw_output=None if output is None else output / 'A',
                    expected_image_root=expected_image_root)
    b = inspect_arm('B', brief_packet, raw_output=None if output is None else output / 'B',
                    expected_image_root=expected_image_root)

    def shared(receipt):
        return {key: item for key, item in receipt['delivery'].items()
                if key not in ('schema', 'image_path_in_original_body')}

    require(shared(a) == shared(b) and a['native_PNG'] == b['native_PNG'], 'full_brief_different_producer')
    previous = verifier()
    _, _, full, _, _ = previous['packet'](full_packet)
    _, _, brief, _, _ = previous['packet'](brief_packet)
    require(all(full['task_result'][key] == brief['task_result'][key] for key in
                ('status', 'reference', 'measurement_scope', 'facts'))
            and full['task_result']['source_mapping']['nearest_witness']
            == brief['task_result']['source_mapping']['nearest_witness'], 'brief_changed_measured_fact_or_source_mapping')
    before, after = full['binding']['image_scope'], brief['image_scope']
    table = after['objects']
    require(all(set(row) == set(table['columns']) for row in before['objects'])
            and all(len(row) == len(table['columns']) for row in table['rows'])
            and [dict(zip(table['columns'], row)) for row in table['rows']] == before['objects']
            and {key: item for key, item in before.items() if key != 'objects'}
            == {key: item for key, item in after.items() if key != 'objects'},
            'brief_changed_occlusion_scope')
    return {'passed': a['passed'] and b['passed'], 'same_producer': True, 'A': a, 'B': b,
            'brief_exact_stages': sum(row['all_items_exact'] for row in b['stages']),
            'full_clipped_stages': sum('middle_cut' in row for row in a['stages']),
            'policy': previous['policy']()[1],
            'scope': 'Offline fixed CLI replay and local path byte read. No model or provider context observed.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('full', type=Path)
    parser.add_argument('brief', type=Path)
    parser.add_argument('--raw-output', type=Path)
    parser.add_argument('--expected-image-root', type=Path)
    args = parser.parse_args()
    require(sys.flags.isolated and sys.dont_write_bytecode, 'invoke_the_pinned_interpreter_with_I_B')
    receipt = audit(args.full, args.brief, raw_output=args.raw_output, expected_image_root=args.expected_image_root)
    print(json.dumps(receipt, ensure_ascii=False, allow_nan=False, indent=2))
    raise SystemExit(0 if receipt['passed'] else 1)
