"""Fixed, projection-only measurements for the two source-binding candidates."""

import ast
import copy
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys
import time
import tracemalloc
from types import SimpleNamespace


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OLD_SOURCE = Path('C:/Users/Administrator/.codex/worktrees/m4-view-reuse-001/hefe/human_eye_plugin/live_spatial_mcp.py')
RAW_SOURCE = Path('D:/he_occluded_transfer_001/preparation/QP/o/product_call_01/SERVICE_RESULT.json')
OLD_RESPONSE = Path('D:/he_occluded_transfer_001/preparation/QP/o/tool_01/RESPONSE.json')
GEOMETRY = Path('C:/Users/Administrator/.codex/worktrees/m4-view-reuse-001/hefe/verification/m4_occluded_scene_transfer_001/inputs/SCENE_GEOMETRY_RATIONAL.json')
OLD_REQUEST = Path('D:/he_occluded_transfer_001/formal/P1/o/tool_05/REQUEST.json')
FUNCTIONS = {'_project_active_patch_support', '_valid_region_location_vector',
             '_valid_visible_pixel_location', '_project_active_inspection',
             'project_active_observation_brief'}
ROUNDS = 31


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_bytes())


def save(path, value):
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2)
        stream.write('\n')


def public_bytes(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode('utf-8')


def projected_copy_nodes(value):
    if isinstance(value, dict):
        return 1 + sum(projected_copy_nodes(v) for v in value.values())
    if isinstance(value, list):
        return 1 + sum(projected_copy_nodes(v) for v in value)
    return 1


def load_projection(path, counters=None):
    tree = ast.parse(Path(path).read_bytes(), filename=str(path))
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in FUNCTIONS]
    assert {node.name for node in functions} == FUNCTIONS

    def deepcopy(value):
        if counters is not None:
            counters['deepcopy_calls'] += 1
            counters['deepcopy_input_nodes'] += projected_copy_nodes(value)
        return copy.deepcopy(value)

    namespace = dict(copy=SimpleNamespace(deepcopy=deepcopy), json=json, math=math, Fraction=Fraction)
    exec(compile(ast.Module(body=functions, type_ignores=[]), str(path), 'exec'), namespace)
    return namespace


class CountedSequence(list):
    def __init__(self, values, counters, prefix):
        super().__init__(values)
        self.counters, self.prefix = counters, prefix

    def __iter__(self):
        self.counters[self.prefix + '_passes'] += 1
        for value in super().__iter__():
            self.counters[self.prefix + '_elements'] += 1
            yield value


def measure_work(path, raw):
    counters = dict(source_mapping_passes=0, source_mapping_elements=0,
                    source_face_passes=0, source_face_elements=0,
                    deepcopy_calls=0, deepcopy_input_nodes=0)
    value = copy.deepcopy(raw)
    support = value['facts']['scope']['patch_support']
    for region in support['regions']:
        region['triangle_indices'] = CountedSequence(region['triangle_indices'], counters, 'source_face')
    support['regions'] = CountedSequence(support['regions'], counters, 'source_mapping')
    namespace = load_projection(path, counters)
    result = namespace['project_active_observation_brief'](value)
    assert result is not None
    return counters


def timed_projections(functions, raw):
    samples = {name: [] for name in functions}
    for function in functions.values():
        assert function(raw) is not None
    names = list(functions)
    for round_index in range(ROUNDS):
        order = names[round_index % len(names):] + names[:round_index % len(names)]
        for name in order:
            start = time.perf_counter_ns()
            projected = functions[name](raw)
            projected_closed = time.perf_counter_ns()
            encoded = public_bytes(projected)
            closed = time.perf_counter_ns()
            samples[name].append(dict(projection_ns=projected_closed-start,
                                      encoding_ns=closed-projected_closed,
                                      projection_and_encoding_ns=closed-start,
                                      public_text_bytes=len(encoded)))
    return samples


def memory_projection(function, raw):
    values = []
    for _ in range(7):
        tracemalloc.start()
        projected = function(raw)
        encoded = public_bytes(projected)
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        values.append(dict(current_python_bytes=current, peak_python_bytes=peak,
                           encoded_text_bytes=len(encoded)))
    return values


def encoding_fixture(count, sparse):
    faces = list(range(0, count * 2, 2)) if sparse else list(range(count))
    rejected = list(range(1, count * 2, 2)) if sparse else []
    obj = dict(object_index=0, host_id='encoding-host', instance_id='encoding-instance', object_name='encoding-control')
    source = dict(**obj, source_triangle_count=count * 2 if sparse else count,
                  supported_triangle_count=count, supported_triangle_indices=faces,
                  unsupported_triangle_count=len(rejected), support_status='partially_supported' if sparse else 'fully_supported',
                  unsupported_components=[dict(triangle_indices=rejected, reason='encoding_control', status='unknown')] if sparse else [])
    patch = dict(schema='active-patch-support-v1', triangle_index_scope='zero_based_per_object_source_faces',
                 all_triangles_participate_in_occlusion=True, objects=[source],
                 regions=[dict(roi_id='encoding-region', object_index=0, triangle_indices=faces)])
    return patch, [obj], [dict(roi_id='encoding-region', object_index=0)], faces


def local_encoding_controls(namespace):
    results = []
    for count in (2, 128, 4096, 8192):
        for sparse in (False, True):
            patch, objects, regions, expected = encoding_fixture(count, sparse)
            times = []
            for _ in range(ROUNDS):
                start = time.perf_counter_ns()
                _, counts, ranges = namespace['_project_active_patch_support'](patch, objects, regions)
                encoded = public_bytes(ranges)
                times.append(time.perf_counter_ns()-start)
            assert counts == [count]
            actual = [face for first, last in ranges[0] for face in range(first, last+1)]
            assert actual == expected
            tracemalloc.start()
            namespace['_project_active_patch_support'](patch, objects, regions)
            _, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            results.append(dict(supported_source_faces=count, layout='sparse_even_indices' if sparse else 'continuous',
                intervals=len(ranges[0]), ranges_value_UTF8_bytes=len(encoded),
                projection_and_ranges_encoding_ns=times, median_ns=statistics.median(times),
                peak_python_allocated_bytes=peak,
                scope='Local source-index encoding and existing denominator validation only. No geometry or images were constructed.'))
    return results


def source_lookup_from_ranges(geometry, regions):
    offsets = [0]
    for obj in geometry['objects']:
        offsets.append(offsets[-1] + len(obj['triangles']))
    mapping = {}
    for region_index, region in enumerate(regions):
        for first, last in region['source_triangle_index_ranges']:
            for local in range(first, last+1):
                mapping[offsets[region['object_index']] + local] = region_index
    return mapping


def consumer_lookup(projection):
    sys.path.insert(0, 'D:/he_anchor_001/venv/Lib/site-packages')
    import numpy as np
    geometry = read(GEOMETRY)
    regions = [dict(zip(projection['regions']['columns'], row)) for row in projection['regions']['rows']]
    code = read(OLD_REQUEST)['params']['arguments']['code']
    tree = ast.parse(code)
    cutoff = next(index for index, node in enumerate(tree.body)
                  if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'image_rows' for t in node.targets))
    prefix = ast.Module(body=tree.body[:cutoff], type_ignores=[])
    representative = compile(prefix, str(OLD_REQUEST) + ':source_lookup_prefix', 'exec')
    source = ast.get_source_segment(code, tree.body[cutoff-1])
    work = dict(vertex_array_loads=0, geometric_pair_candidates=0)

    def trace(frame, event, argument):
        if frame.f_code is representative and event == 'line':
            line = code.splitlines()[frame.f_lineno-1]
            if "vertices=np.array(obj['vertices']" in line:
                work['vertex_array_loads'] += 1
            if "pair=obj['triangles']" in line:
                work['geometric_pair_candidates'] += 1
        return trace

    def old_lookup(instrument=False):
        namespace = dict(geometry=geometry, regions=copy.deepcopy(regions), Fraction=Fraction)
        if instrument:
            sys.settrace(trace)
        try:
            exec(representative, namespace)
        finally:
            if instrument:
                sys.settrace(None)
        return namespace['surface_by_face']

    expected = old_lookup(instrument=True)
    assert expected == source_lookup_from_ranges(geometry, regions)
    times = dict(saved_geometric_lookup=[], ranges_lookup=[])
    for round_index in range(ROUNDS):
        order = ('saved_geometric_lookup', 'ranges_lookup') if round_index % 2 == 0 else ('ranges_lookup', 'saved_geometric_lookup')
        for name in order:
            start = time.perf_counter_ns()
            result = old_lookup() if name == 'saved_geometric_lookup' else source_lookup_from_ranges(geometry, regions)
            times[name].append(time.perf_counter_ns()-start)
            assert result == expected
    return dict(source_request_path=str(OLD_REQUEST), source_request_sha256=sha(OLD_REQUEST),
        exact_source_lookup_loop=source, subset='Saved P1 tool5 prefix before image_rows. Pixel recomputation and image requests are excluded.',
        numpy_version=np.__version__, numpy_path=np.__file__, bindings=len(expected),
        source_work=work, new_work=dict(vertex_array_loads=0, geometric_pair_candidates=0,
            source_range_rows=len(regions), expanded_source_faces=len(expected)),
        paired_execution_ns=times,
        medians_ns={name: statistics.median(values) for name, values in times.items()},
        scope='Representative local same-input arithmetic only. Formal consumer choices and total-task benefit remain unmeasured here.')


def main():
    output = HERE / 'ENGINEERING_REPORT.json'
    if output.exists():
        raise FileExistsError('engineering_measurements_are_write_once')
    started = time.perf_counter_ns()
    assert sha(OLD_SOURCE) == '54874f092b57ffc496ff16eb58ba50fb355e1b643aab67311bffd42910d5e08d'
    variants = dict(baseline=OLD_SOURCE, initial=HERE/'product_candidate_01.py', optimized=HERE/'product_candidate_02.py')
    assert sha(variants['optimized']) == sha(ROOT/'human_eye_plugin/live_spatial_mcp.py')
    input_hash = sha(RAW_SOURCE)
    saved_raw = read(RAW_SOURCE)
    saved_public = json.loads(read(OLD_RESPONSE)['result']['content'][0]['text'])
    raw = copy.deepcopy(saved_raw)
    raw['binding'].pop('camera_specification')
    raw['image_delivery'] = copy.deepcopy(saved_public['image_delivery'])
    encoded_input_hash = hashlib.sha256(public_bytes(raw)).hexdigest()
    namespaces = {name: load_projection(path) for name, path in variants.items()}
    functions = {name: namespace['project_active_observation_brief'] for name, namespace in namespaces.items()}
    projected = {name: function(raw) for name, function in functions.items()}
    assert all(value is not None for value in projected.values())
    assert projected['baseline'] == saved_public
    assert projected['initial'] == projected['optimized']
    restored = copy.deepcopy(projected['optimized'])
    restored['schema'] = projected['baseline']['schema']
    del restored['source_triangle_index_ranges_semantics']
    position = restored['regions']['columns'].index('source_triangle_index_ranges')
    restored['regions']['columns'].pop(position)
    for row in restored['regions']['rows']:
        row.pop(position)
    assert restored == projected['baseline']
    samples = timed_projections(functions, raw)
    work = {name: measure_work(path, raw) for name, path in variants.items()}
    memory = {name: memory_projection(function, raw) for name, function in functions.items()}
    controls = local_encoding_controls(namespaces['optimized'])
    lookup = consumer_lookup(projected['optimized'])
    assert sha(RAW_SOURCE) == input_hash and hashlib.sha256(public_bytes(raw)).hexdigest() == encoded_input_hash
    result = dict(schema='m1-source-face-binding-engineering-v1',
        registered_rounds=ROUNDS, order='Three projection variants rotate across rounds, lookups alternate.',
        input_path=str(RAW_SOURCE), input_sha256=input_hash, original_saved_input_unchanged=True,
        actual_public_receipt_path=str(OLD_RESPONSE), actual_public_receipt_sha256=sha(OLD_RESPONSE),
        projection_input_preparation='Copied saved SERVICE_RESULT, excluded private camera_specification and restored image_delivery from its actual closed MCP receipt. Baseline projection equals that exact saved public result.',
        source_sha256={name: sha(path) for name, path in variants.items()},
        semantic_checks=dict(initial_equals_optimized=True, removing_only_new_field_semantics_and_version_restores_baseline=True),
        public_text_bytes={name: len(public_bytes(value)) for name, value in projected.items()},
        operation_counts=work, projection_measurements=samples,
        medians_ns={name: {key: statistics.median(sample[key] for sample in values)
                          for key in ('projection_ns', 'encoding_ns', 'projection_and_encoding_ns')}
                    for name, values in samples.items()},
        memory_measurements=memory, local_encoding_controls=controls, representative_consumer_lookup=lookup,
        hot_attempt_count=1, candidate_count=2,
        actual_product_observe_calls=0, actual_geometry_capture_calls=0, actual_geometry_solver_calls=0,
        actual_raster_calls=0, actual_model_consumers=0,
        scope='Pure AST-selected saved-result projection and ordinary local source-index arithmetic. Python allocation peaks are tracemalloc values, not process RSS.',
        started_ns=started, before_publication_ns=time.perf_counter_ns())
    save(output, result)
    print(json.dumps(dict(public_text_bytes=result['public_text_bytes'], work=work,
        medians_ns=result['medians_ns'], lookup_medians_ns=lookup['medians_ns'])))


if __name__ == '__main__':
    main()
