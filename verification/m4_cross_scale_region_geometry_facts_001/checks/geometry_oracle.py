"""Replay actual producer bytes and independently check the brief geometry projection."""

import argparse
import base64
import copy
from decimal import Decimal, localcontext
from fractions import Fraction
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import runpy
import sys
import zipfile


NS = Path(__file__).resolve().parents[1]
V = NS.parent
HISTORICAL = V / 'm4_cross_scale_brief_entry_001'
RUNTIME = Path('D:/he_m4_cross_scale_brief_entry_001').resolve()
OUTPUT_FIELDS = ('area_m2', 'unit_normal_world')


def check(condition, reason):
    if not condition:
        raise ValueError(reason)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


class Sources:
    def __init__(self):
        self.pins = {}
        index = self.read(HISTORICAL / 'RUNTIME_INDEX.json',
                          '7625392863637b311c5c6a1921a4eaac386845e5acbcd30c452a2c1d2e385fbb')
        self.index = {row['path']: row for row in index['files']}
        check(len(self.index) == index['count'], 'historical_archive_index_denominator')
        self.archive = RUNTIME / 'ORIGINAL_RUNTIME.zip'
        raw = self.raw(self.archive, '1fa86e8346e08c63fa4f3d98e992d239391da0bc7dcca6ed15b6b5f3ba51635e')
        check(len(raw) == index['archive']['bytes'], 'historical_archive_length_changed')

    def raw(self, path, expected=None):
        path = Path(path).resolve()
        raw = path.read_bytes()
        pin = {'path': str(path), 'bytes': len(raw), 'sha256': digest(raw)}
        check(expected is None or pin['sha256'] == expected, 'source_hash_changed/' + str(path))
        check(self.pins.get(pin['path'], pin) == pin, 'source_changed_during_replay/' + str(path))
        self.pins[pin['path']] = pin
        return raw

    def read(self, path, expected=None):
        return json.loads(self.raw(path, expected))

    def archived(self, archive, path):
        path = Path(path).resolve()
        name = path.relative_to(RUNTIME).as_posix()
        entry = self.index[name]
        raw = self.raw(path, entry['sha256'])
        check(len(raw) == entry['bytes'] and raw == archive.read(name), 'historical_archive_entry_changed/' + name)
        return raw


def import_product(root, prefix, sources):
    package = Path(root).resolve() / 'human_eye_plugin'
    sources.raw(package / 'live_spatial_mcp.py')
    entry = package / '__init__.py'
    spec = importlib.util.spec_from_file_location(prefix, entry, submodule_search_locations=[str(package)])
    module = importlib.util.module_from_spec(spec)
    sys.modules[prefix] = module
    spec.loader.exec_module(module)
    return (importlib.import_module(f'{prefix}.live_spatial_mcp'),
            importlib.import_module(f'{prefix}.active_observation'),
            importlib.import_module(f'{prefix}.active_observation_region_task'))


def rational_coordinates(obj):
    return [tuple(Fraction(component) for component in point) for point in obj['vertices_world_m']]


def triangle_area_vector(vertices, indices):
    # The cyclic coordinate determinant equals twice the oriented triangle area.
    a, b, c = (vertices[index] for index in indices)
    return tuple(sum(p[j] * q[k] - p[k] * q[j] for p, q in ((a, b), (b, c), (c, a)))
                 for j, k in ((1, 2), (2, 0), (0, 1)))


def norm_squared(vector):
    return sum(component ** 2 for component in vector)


def decimal(fraction):
    return Decimal(fraction.numerator) / Decimal(fraction.denominator)


def triangle_metrics(obj, source_indices):
    vertices = rational_coordinates(obj)
    ordered = [triangle_area_vector(vertices, obj['triangles'][row]) for row in source_indices]
    with localcontext() as context:
        context.prec = 110
        vector = ordered[0]
        length = decimal(norm_squared(vector)).sqrt()
        area = sum(decimal(norm_squared(item)).sqrt() for item in ordered) / 2
        return area, tuple(decimal(component) / length for component in vector)


def rounded_error(actual, exact):
    expected = float(exact)
    check(type(actual) in (int, float) and math.isfinite(actual), 'non_finite_or_non_numeric_projection')
    with localcontext() as context:
        context.prec = 110
        return abs(Decimal.from_float(float(actual)) - exact) / Decimal.from_float(math.ulp(expected))


def check_facts(row, area, normal, name):
    got_normal = row['unit_normal_world']
    check(type(got_normal) is list and len(got_normal) == 3, 'unit_normal_shape/' + name)
    unit_errors = [rounded_error(actual, exact) for actual, exact in zip(got_normal, normal, strict=True)]
    check(max(unit_errors) <= 3 and abs(math.hypot(*got_normal) - 1) <= 4 * math.ulp(1.0),
          'oriented_unit_normal_inaccurate/' + name)
    expected = float(area)
    result = {'expected_area_m2_decimal': str(area), 'expected_unit_normal_decimal': [str(x) for x in normal],
              'actual_area_m2': row.get('area_m2'), 'actual_unit_normal_world': got_normal,
              'normal_errors_in_ULPs': [str(x) for x in unit_errors]}
    if math.isfinite(expected) and expected > 0:
        check(type(row['area_m2']) in (int, float) and row['area_m2'] > 0, 'measured_area_missing/' + name)
        error = rounded_error(row['area_m2'], area)
        check(error <= 2, 'area_m2_inaccurate/' + name)
        result['area_error_in_ULPs'] = str(error)
    else:
        check(row.get('area_m2') is None, 'unrepresentable_area_not_omitted/' + name)
        reasons = row.get('geometry_fact_unknowns')
        check(reasons == {'area_m2': 'outside_positive_binary64_range'},
              'unrepresentable_area_missing_reason/' + name)
        result['area_omission_reason'] = reasons['area_m2']
    return result


def check_cli(result, sources):
    helpers = V / 'm1_source_region_facts_first_001/checks'
    helper = helpers / 'client_budget_replay.py'
    sources.raw(helper, '8a59abf2ccdaba3013c7ef3e8180265a3311ca3d5039f8af86b679252be08f4a')
    codec = runpy.run_path(str(helper))
    policy = sources.read(helpers / 'CLIENT_BUDGET_REVIEW.json',
                          '0e90ad3df1f74a1977d96b212bd7592e11cdbc4e285a80213a25745fedc57ae8')['policy']
    replay = []
    for duration in ('0.0000', '10.0000', '100.0000'):
        before = codec['model_items'](result, duration)
        mcp = codec['truncate_items'](before, policy['MCP_bytes'])
        history = codec['truncate_items'](mcp, policy['history_approximate_tokens'], token_mode=True)
        check(before == mcp == history and len(history) == 5, 'brief_text_or_original_PNG_clipped')
        replay.append({'duration_header': duration, 'header_UTF8_bytes': len(before[0]['text'].encode()),
                       'complete_text_and_ordered_images': True})
    return {'policy': policy, 'cases': replay, 'provider_input_measured': False}


def cases(sources, baseline, candidate):
    candidate_mcp, active, task = candidate
    baseline_mcp = baseline[0]
    truth = sources.read(HISTORICAL / 'fixture/CURRENT_TRUTH.json',
                         '376a31b5a5cfc0e979f6b43d43756d9837dbfae9c53b96c77f46cc329b2ba922')
    geometry = sources.read(HISTORICAL / 'fixture/GEOMETRY.json', truth['geometry_sha256'])
    records = {}
    with zipfile.ZipFile(sources.archive) as archive:
        for ordinal in (1, 2):
            slot = RUNTIME / 'slots/P1'
            producer = json.loads(sources.archived(archive, slot / f'product_full/call_{ordinal:03d}/SERVICE_RESULT.json'))
            owner = slot / f'owner/tool_{ordinal:02d}'
            request = json.loads(sources.archived(archive, owner / 'PRODUCT_REQUEST.json'))
            original = json.loads(sources.archived(archive, owner / 'PRODUCT_RESPONSE.json'))['result']
            detail = request['params']['arguments']['response_detail']
            for frame in producer['frames']:
                raw = sources.archived(archive, frame['image_path'])
                check(digest(raw) == frame['image_sha256'], 'original_frame_sha_changed')
            old = baseline_mcp._tool_result(producer, response_detail=detail, is_error=False)
            new = candidate_mcp._tool_result(producer, response_detail=detail, is_error=False)
            old_text = old['content'][0]['text']
            original_text = original['content'][0]['text']
            # The producer archive sorts object keys, so replay can preserve
            # the parsed values and byte count while changing their ordering.
            check(old['isError'] == original['isError']
                  and len(old_text.encode()) == len(original_text.encode())
                  and json.loads(old_text) == json.loads(original_text)
                  and old['content'][1:] == original['content'][1:],
                  'fixed_installed_product_did_not_reproduce_original_' + detail)
            check(new['content'][1:] == old['content'][1:], 'historical_original_images_changed_' + detail)
            if detail == 'full':
                check(new == old, 'historical_full_body_changed_in_candidate')
                records['actual_historical_full'] = {'byte_exact': True, 'PNG_count': len(new['content']) - 1}
            else:
                records['actual_historical_brief'] = compare_brief(old, new, truth, geometry, sources)
                check(candidate_mcp._tool_result(producer, response_detail='full', is_error=False) ==
                      baseline_mcp._tool_result(producer, response_detail='full', is_error=False),
                      'candidate_full_changed_with_actual_image_carriers')
                records['full_with_images_replay_match'] = True
                fresh = producer
    check(fresh['work']['raster_attempts'] == 4, 'historical_fresh_raster_count_changed')
    source_objects = [{'name': obj['name'], 'vertices': obj['vertices_world_m'], 'triangles': obj['triangles']}
                      for obj in geometry['objects']]
    objects, _, _ = active.geometry({'objects': source_objects})
    regions, _ = active.partition_regions(objects)
    original_conditions = fresh['facts']['region_task']['conditions']
    picked = [region for region in regions if task.region_matches(region, original_conditions)]
    compared = sorted((region.object_name, list(region.triangle_indices)) for region in picked)
    check(compared == sorted((entry['object_name'], entry['source_triangle_indices'])
                             for entry in truth['eligible']), 'current_candidate_exact_task_filter_changed')
    records['actual_scene_filter'] = {'eligible': compared, 'total_rectangles': len(regions),
                                      'fixed_original_new_rasters': fresh['work']['raster_attempts']}
    records['synthetic_probes'] = numeric_probes(fresh, candidate)
    return records


def compare_brief(old_result, new_result, truth, geometry, sources):
    old_body = old_result['content'][0]['text']
    new_body = new_result['content'][0]['text']
    baseline, actual = json.loads(old_body), json.loads(new_body)
    remainder = copy.deepcopy(actual)
    truth_rows = {row['object_name']: row for row in truth['eligible']}
    objects = {obj['name']: obj for obj in geometry['objects']}
    exact, picture_hashes = {}, []
    for position, image in enumerate(new_result['content'][1:], start=1):
        descriptor = dict(zip(actual['images']['columns'], actual['images']['rows'][position-1], strict=True))
        raw = base64.b64decode(image['data'], validate=True)
        check(image['type'] == 'image' and image['mimeType'] == 'image/png'
              and descriptor['native_content_block_index'] == position
              and digest(raw) == descriptor['image_sha256'], 'brief_PNG_or_position_changed')
        picture_hashes.append(descriptor['image_sha256'])
    check(len(picture_hashes) == 3, 'historical_three_PNGs_required')
    for row in remainder['region_task']['rows']:
        name = row['object_name']
        bound = truth_rows[name]
        check(name not in exact and row['source_triangle_indices'] == bound['source_triangle_indices'],
              'historical_region_rows_changed/' + name)
        area, normal = triangle_metrics(objects[name], bound['source_triangle_indices'])
        exact[name] = check_facts(row, area, normal, name)
        if name == 'M06':
            check(row['complete_witness'] is None and row['status'] == 'unknown'
                  and row['reason'] == bound['expected_unknown_reason'], 'M06_unknown_regression')
        else:
            witness = row['complete_witness']
            position = witness['native_content_block_index']
            descriptor = dict(zip(actual['images']['columns'], actual['images']['rows'][position-1], strict=True))
            check(witness['view_name'] in bound['eligible_complete_views']
                  and all(descriptor[key] == witness[key] for key in ('view_name', 'image_ref', 'frame_identity', 'scope_id')),
                  'local_witness_reference_changed/' + name)
        for field in OUTPUT_FIELDS:
            del row[field]
    check(set(exact) == set(truth_rows) and remainder == baseline, 'brief_changed_beyond_two_new_numeric_facts')
    return {'historical_UTF8_bytes': len(old_body.encode()), 'candidate_UTF8_bytes': len(new_body.encode()),
            'added_UTF8_bytes': len(new_body.encode()) - len(old_body.encode()), 'original_PNGs_ordered': picture_hashes,
            'independent_triangle_metrics': exact, 'CLI_replay': check_cli(new_result, sources)}


def make_probe(edge_u, edge_v, reverse=False):
    a, b = tuple(map(Fraction, edge_u)), tuple(map(Fraction, edge_v))
    return {'name': 'probe', 'vertices_world_m': [(0, 0, 0), a, tuple(p + q for p, q in zip(a, b)), b],
            'triangles': [(0, 2, 1), (0, 3, 2)] if reverse else [(0, 1, 2), (0, 2, 3)]}


def numeric_probes(original, candidate):
    mcp, active, policy = candidate
    tiny, large = Fraction(1, 10 ** 150), 10 ** 150
    probes = {
        'area_lower_bound_equal': (make_probe((Fraction(1, 8), 0, 0), (0, Fraction(1, 16), 0)), (1/128, 1)),
        'area_upper_bound_equal': (make_probe((Fraction(1, 8), 0, 0), (0, Fraction(1, 4), 0)), (1/32, 1)),
        'tilt_z_equal': (make_probe((1, 0, 0), (0, 3, 4)), (5, 0.6)),
        'reverse_tilt_z_equal': (make_probe((1, 0, 0), (0, 3, 4), reverse=True), (5, -0.6)),
        'negative_z_axis_equal': (make_probe((1, 0, 0), (0, 1, 0), reverse=True), (1, -1)),
        'squared_norm_underflow': (make_probe((tiny, 0, 0), (0, tiny, tiny)), None),
        'squared_norm_overflow': (make_probe((large, 0, 0), (0, large, large)), None),
        'final_area_subnormal_after_cross_underflow':
            (make_probe((Fraction(1, 2 ** 537), 0, 0), (0, Fraction(1, 2 ** 537), 0)), None),
        'area_float_maximum': (make_probe((int(sys.float_info.max), 0, 0), (0, 1, 0)), None),
        'huge_times_tiny_rational_edges':
            (make_probe((10 ** 350, 0, 0), (0, Fraction(1, 10 ** 350), Fraction(1, 10 ** 351))), None),
        'small_unit_vector_component': (make_probe((1, 0, 0), (0, 1, Fraction(1, 10 ** 300))), None),
        'area_out_of_range_high': (make_probe((10 ** 200, 0, 0), (0, 10 ** 200, 0)), None),
        'area_out_of_range_low':
            (make_probe((Fraction(1, 10 ** 200), 0, 0), (0, Fraction(1, 10 ** 200), 0)), None),
    }
    formatted = {}
    for name, (asset, boundary) in probes.items():
        source = {'name': asset['name'], 'vertices': asset['vertices_world_m'], 'triangles': asset['triangles']}
        parsed, _, _ = active.geometry({'objects': [source]})
        (region,), _ = active.partition_regions(parsed)
        exact_area, exact_normal = triangle_metrics(asset, [0, 1])
        packet = copy.deepcopy(original)
        historical = packet['facts']['region_task']['rows'][0]
        world = active.region_world_description(region)
        historical.update(world)
        result = mcp.project_active_observation_brief(packet)['region_task']['rows'][0]
        check(all(result[key] == world[key] for key in world), 'lossless_geometry_changed/' + name)
        record = check_facts(result, exact_area, exact_normal, name)
        if boundary is not None:
            area, nz = boundary
            inclusive = {'area_min_m2': area, 'area_max_m2': area, 'normal_z_min': nz}
            min_outside = {**inclusive, 'area_min_m2': math.nextafter(area, math.inf), 'area_max_m2': area * 2}
            max_outside = {**inclusive, 'area_min_m2': 0, 'area_max_m2': math.nextafter(area, -math.inf)}
            outside = [min_outside, max_outside]
            if nz < 1:
                outside.append({**inclusive, 'normal_z_min': math.nextafter(nz, math.inf)})
            check(policy.region_matches(region, inclusive)
                  and all(not policy.region_matches(region, rule) for rule in outside),
                  'exact_boundary_regression/' + name)
            record['exact_filter_inclusive_and_just_outside'] = True
        formatted[name] = record
    return formatted


def compatibility(sources, low, high):
    products = {
        'active_observation_without_region_task': (
            'D:/he_m4_global_local_001/sessions/global/product_full/call_001/SERVICE_RESULT.json',
            '7e1c4331d7582254e985d256595dad0fdef4d98a21974b969f3cff9e97f6a112'),
        'source_region': ('D:/he_m4_live_source_region_task_003/slots/P1/product_full/call_001/SERVICE_RESULT.json',
                          '32d1dded3fe137e611087e1e8487b732d3cede1d47a6cbe259a466eb6be5b9c9'),
    }
    result = {}
    for mode, (path, sha) in products.items():
        producer = sources.read(path, sha)
        check('region_task' not in producer.get('facts', {}), 'legacy_probe_contains_region_task')
        for frame in producer.get('frames', []):
            sources.raw(frame['image_path'], frame['image_sha256'])
        result[mode] = {}
        for detail in ('brief', 'full'):
            old = low._tool_result(producer, response_detail=detail, is_error=False)
            new = high._tool_result(producer, response_detail=detail, is_error=False)
            check(old == new, 'legacy_mode_or_photo_output_changed/' + mode + '/' + detail)
            result[mode][detail] = {'exact': True, 'original_PNG_count': len(new['content']) - 1}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    sources = Sources()
    baseline = sources.read(V / 'm4_live_assembly_relation_task_001/PRODUCT_RUN_BINDING.json',
                            'eb0ecece262ce0fbbe2b01f041b9e6eab77f0c4810030094c2f590850f51b2e0')
    shared = sources.read(V / 'm5_harness_recovery_001/SHARED_DEPENDENCY.json',
                          '0c1d25be82eb494c6e7fddff39ff380af307fe8d1a1f1ff37a3414e819e55a2b')
    sys.path[:0] = [str(args.candidate.resolve()), baseline['dependency_root'], shared['dependency_root']]
    older = import_product(baseline['install_root'], '_geometry_oracle_baseline', sources)
    newer = import_product(args.candidate, '_geometry_oracle_candidate', sources)
    result = cases(sources, older, newer)
    legacy = compatibility(sources, older[0], newer[0])
    sources.raw(Path(__file__))
    result.update(passed=True, schema='m4-cross-scale-region-geometry-facts-oracle-v1',
                  candidate_root=str(args.candidate.resolve()), other_modes=legacy,
                  actual_Blender_processes=0, actual_model_runs=0, actual_rasters=0,
                  source_pins=sorted(sources.pins.values(), key=lambda row: row['path']))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(result, stream, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2)
        stream.write('\n')
    summary = result['actual_historical_brief']
    print('GEOMETRY_ORACLE_PASS', len(result['synthetic_probes']), len(result['source_pins']),
          summary['historical_UTF8_bytes'], summary['candidate_UTF8_bytes'], digest(args.output.read_bytes()))


if __name__ == '__main__':
    main()
