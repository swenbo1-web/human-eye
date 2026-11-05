"""Owned local PERF-010 API qualification, separate from model task results.

Run this copied helper from the isolated installed candidate. Each API/case has
its own Blender process and service. ID lookup is a separately timed preflight.
Cold means first measured API request after that lookup, not all-process cold.
"""
from __future__ import annotations

import argparse
import contextlib
import copy
import json
import math
from pathlib import Path
import statistics
import sys
import time
import tracemalloc
import uuid

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from verification.perf010_qualification import bind_candidate
from verification.visual004_native import NativeSession, check, load, need, save, sha
from verification import visual004_product as product


CASES = (
    ('calibration_aabb', 'calibration', ('Object_01', 'Object_02', 'Object_03', 'Object_04'), None),
    ('calibration_pair', 'calibration', ('Object_02', 'Object_03'), .25),
    ('V01', 'V01', ('Object_04', 'Object_11'), .0015),
    ('V02', 'V02', ('Object_05', 'Object_04'), .04),
    ('V03', 'V03', ('Object_02', 'Object_01'), 'geometry_resource_limit'),
)
CACHE_FIELDS = ('measurement_hits', 'measurement_misses', 'measurement_computations')


def cache_counts(service):
    cache = service._perception_cache
    stats = cache.stats() if cache is not None else {}
    return {key: stats.get(key, 0) for key in CACHE_FIELDS}


def arguments_for(api, names, identities, aabb):
    if api == 'task':
        return dict(include_image=False, query=dict(mode='task',
            objects=[dict(name=name) for name in names],
            requested_facts=['aabb'] if aabb else ['surface_clearance', 'solid_relation']),
            response_detail='brief')
    if aabb:
        return dict(include_image=False, query=dict(mode='overview'), response_detail='brief')
    return dict(include_image=False, focal_id=identities[names[0]], reference_id=identities[names[1]],
        query=dict(mode='exact_pairs', object_ids=[identities[names[1]]], max_exact_pairs=1,
                   alignment_evidence=False), response_detail='brief')


def observation(metadata):
    if type(metadata.get('observation')) is dict:
        return metadata['observation']
    route = metadata.get('routing') or {}
    context = route.get('context_text')
    return json.loads(context) if type(context) is str else {}


def resource_certificate(spec, names):
    """Independent count arithmetic from frozen authored polygons.

    The registered collision budget bounds edge directions by three per
    triangle. This reproduces its documented bound from source counts without
    invoking work_budget_status, the solver, or a product rejection result.
    """
    objects = {item['name']: item for item in spec['objects']}
    counts = []
    for name in names:
        item = objects[name]
        counts.append(dict(name=name, vertices=len(item['vertices']),
            triangles=sum(len(face)-2 for face in item['faces'])))
    left, right = counts
    triangle_sum = left['triangles']+right['triangles']
    vertex_sum = left['vertices']+right['vertices']
    edge_product = (3*left['triangles'])*(3*right['triangles'])
    projection_elements = vertex_sum*(triangle_sum+edge_product)
    return dict(objects=counts, sat_projection_elements=projection_elements,
        configured_limit_elements=2_000_000, expected_reason='sat_projection_work_limit',
        rejected_by_count=projection_elements > 2_000_000,
        basis='frozen_source_polygon_triangulation_counts_and_registered_budget_formula')


def assess(metadata, api, names, identities, spec, expected):
    """Use authored analytic constants and source vertices, never solver output."""
    if expected is None:
        wanted = {obj['name']: obj for obj in spec['objects'] if obj['name'] in names}
        boxes = {}
        if api == 'task':
            for binding, fact in zip(metadata['binding']['objects'], metadata['facts']['aabb']):
                need(fact['status'] == 'measured', 'local_aabb_measured')
                boxes[binding['name']] = fact['value']
        else:
            by_id = {obj['object_id']: obj for obj in observation(metadata).get('objects', [])}
            for name in names:
                item = by_id[identities[name]]
                boxes[name] = dict(min=item['bbox_min'], max=item['bbox_max'])
        errors = []
        for name, source in wanted.items():
            for key, aggregate in (('min', min), ('max', max)):
                target = [aggregate(point[axis] for point in source['vertices']) for axis in range(3)]
                errors.extend(abs(a - b) for a, b in zip(boxes[name][key], target))
        need(len(boxes) == len(names) and max(errors, default=math.inf) <= 2e-6, 'local_analytic_aabb')
        return dict(passed=True, analytic_max_error_m=max(errors), expected_scope='authored_vertex_extrema')
    if api == 'task':
        clearance = metadata['facts']['surface_clearance']
        relation = metadata['facts']['solid_relation']
        known = clearance['status'] == 'measured'
        value = clearance.get('value')
    else:
        measure = observation(metadata).get('measurement', {})
        known = measure.get('measurement_valid') is True
        value = measure.get('signed_clearance_m')
        relation = measure
    if expected == 'geometry_resource_limit':
        certificate = resource_certificate(spec, names)
        need(certificate['rejected_by_count'], 'local_independent_resource_bound')
        need(not known, 'local_resource_limit_remains_unknown')
        if api == 'task':
            need(relation['status'] == 'unknown' and clearance.get('reason') == expected
                 and relation.get('reason') == expected, 'local_expected_task_resource_reason')
        else:
            route = metadata.get('routing') or {}
            need(expected in route.get('reason_codes', [])
                 and certificate['expected_reason'] in route.get('geometry_work_budget', {}).get('reason_codes', []),
                 'local_expected_legacy_resource_reason')
        return dict(passed=True, expected_scope='independent_frozen_count_resource_bound',
                    clearance_known=False, independent_certificate=certificate)
    need(known and type(value) in (int, float) and abs(value - expected) <= 2e-6, 'local_analytic_clearance')
    if api == 'task':
        need(relation['status'] == 'measured' and relation['value'] == 'not_penetrating', 'local_relation')
    else:
        need(relation.get('is_penetrating') is False, 'local_relation')
    return dict(passed=True, expected_clearance_m=expected, actual_clearance_m=value,
                absolute_error_m=abs(value - expected), expected_scope='independent_authored_analytic_constant')


def request_trace(workspace, trace_id, request_id):
    path = workspace / 'product_audit.jsonl'
    if not path.is_file():
        return None
    for line in reversed(path.read_text(encoding='utf8').splitlines()):
        row = json.loads(line)
        trace = row.get('trace') or {}
        if row.get('event') == 'request_trace' and (row.get('trace_id') == trace_id
                or trace.get('annotations', {}).get('mcp_request_id') == request_id):
            return trace
    return None


def one_request(session, arguments, api, names, identities, spec, expected, ordinal):
    context = product._context(session)
    before = cache_counts(context['service'])
    request_id = 'local-' + uuid.uuid4().hex
    started = time.perf_counter_ns()
    response = product.observe(session, arguments, request_id=request_id, operator_support_check=True)
    finished = time.perf_counter_ns()
    metadata = response['actual_product_metadata']
    need(type(metadata) is dict and not response['images'], 'local_numeric_response')
    try:
        need(metadata.get('status') != 'error', 'local_actual_MCP_error_'+str(metadata.get('error')))
        assessment = assess(metadata, api, names, identities, spec, expected)
    except (ValueError, KeyError, TypeError) as exc:
        assessment = dict(passed=False, type=type(exc).__name__, message=str(exc))
    after = cache_counts(context['service'])
    trace_id = metadata.get('request_trace', {}).get('trace_id')
    trace = request_trace(session.workspace, trace_id, request_id)
    need(type(trace) is dict, 'local_actual_service_trace')
    trace_id = trace['trace_id']
    row = dict(ordinal=ordinal, phase='cold_after_preflight' if ordinal == 0 else 'warm',
        request_id=request_id, qa_adapter_elapsed_ns=finished-started,
        text_bytes=sum(len(text.encode('utf8')) for text in response['mcp_text']),
        status=metadata.get('status'), mcp_is_error=response['mcp_is_error'], assessment=assessment,
        trace_id=trace_id, service_spans=trace['spans'], service_trace_duration_ns=trace['duration_ns'],
        cache_before=before, cache_after=after,
        cache_delta={key: after[key]-before[key] for key in CACHE_FIELDS},
        raw_product_receipts=str(session.workspace/'product_calls'/request_id),
        original_request_budget_s=context['service'].request_budget_s,
        original_session_deadline_ns=session.config['deadline_ns'])
    if expected is None:
        need(row['cache_delta']['measurement_computations'] == 0, 'local_overview_no_pair_solve')
    save(session.workspace/('MEASURED_'+str(ordinal)+'.json'), row)
    return row


@contextlib.contextmanager
def call_instrumentation():
    """Count only one real MCP invocation, including recursive deepcopy calls."""
    from human_eye_plugin import agent_adapters
    functions = dict(dumps=json.dumps, loads=json.loads, deepcopy=copy.deepcopy,
                     build_agent_observation=agent_adapters.build_agent_observation)
    codes = {function.__code__: name for name, function in functions.items()}
    counts = {key: 0 for key in functions}
    counts['deepcopy_top_level'] = 0
    depth = 0
    previous_profile = sys.getprofile()

    def profile(frame, event, argument):
        nonlocal depth
        name = codes.get(frame.f_code)
        if name is None:
            return
        if event == 'call':
            counts[name] += 1
            if name == 'deepcopy':
                if depth == 0:
                    counts['deepcopy_top_level'] += 1
                depth += 1
        elif event == 'return' and name == 'deepcopy':
            depth -= 1

    tracemalloc.start()
    sys.setprofile(profile)
    try:
        yield counts
    finally:
        sys.setprofile(previous_profile)
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        counts.update(python_traced_current_bytes=current, python_traced_peak_bytes=peak)


def instrument(session, arguments):
    context = product._context(session)
    request = dict(jsonrpc='2.0', id='instrument-'+uuid.uuid4().hex, method='tools/call',
                   params=dict(name='human_eye_scene_observe', arguments=arguments))
    with call_instrumentation() as counts:
        with context['service']._request_budget() as budget:
            remaining = (session.config['deadline_ns']-time.perf_counter_ns())/1e9
            need(remaining > 0 and budget is not None, 'local_instrument_original_deadline')
            budget['deadline'] = min(budget['deadline'], time.monotonic()+remaining)
            response = context['server'].handle_jsonrpc_message(request)
    result = dict(counts=counts, excluded_from_timing_statistics=True,
        scope='single_warmed_actual_MCP_invocation_in_coordinator_Python_process',
        peak_scope='tracemalloc_Python_allocations_only_not_Blender_or_process_RSS',
        deepcopy_scope='all_function_entries_including_recursive_calls_plus_top_level_count')
    save(session.workspace/'INSTRUMENT_REQUEST.json', request)
    save(session.workspace/'INSTRUMENT_RESPONSE.json', response)
    save(session.workspace/'INSTRUMENT_COUNTS.json', result)
    return result


def run_api(args, case, api, deadline_ns):
    case_id, asset_id, names, expected = case
    asset = args.assets/asset_id/'scene.blend'
    source_hash = sha(asset)
    spec = load(args.assets/asset_id/'SCENE_SPEC.json')
    workspace = args.output/(case_id+'_'+api)
    session = None
    report = dict(case=case_id, api=api, source_asset=str(asset), original_source_sha256=source_hash,
                  prebound_ids_advantage_to_old_api=True, success=False)
    try:
        session = NativeSession.start(blender=args.blender, asset=asset, workspace=workspace,
            deadline_ns=deadline_ns, condition='P', expected_asset_sha256=source_hash)
        started = time.perf_counter_ns()
        context = product._context(session)
        captured = context['host'].capture_scene()
        identities = {obj['name']: obj['object_id'] for obj in captured['meshes']}
        need(all(name in identities for name in names), 'local_fixed_name_binding')
        preflight_ns = time.perf_counter_ns()-started
        report['preflight'] = dict(elapsed_ns=preflight_ns, object_ids={name: identities[name] for name in names},
            scope='service_construction_transport_connection_and_one_capture_excluded_from_request_stats',
            measured_requests_are_not_all_process_cold=True)
        save(workspace/'PREFLIGHT_CAPTURE.json', captured)
        save(workspace/'PREFLIGHT.json', report['preflight'])
        arguments = arguments_for(api, names, identities, expected is None)
        save(workspace/'FIXED_ARGUMENTS.json', arguments)
        rows = [one_request(session, arguments, api, names, identities, spec, expected, number)
                for number in range(6)]
        report['requests'] = rows
        report['instrumentation'] = instrument(session, arguments)
        warm = [row['qa_adapter_elapsed_ns']/1e6 for row in rows[1:]]
        report['timing'] = dict(cold_after_preflight_ms=rows[0]['qa_adapter_elapsed_ns']/1e6,
            warm_count=5, warm_median_ms=statistics.median(warm), warm_max_ms=max(warm),
            warm_mean_ms=statistics.mean(warm),
            scope='actual_product_adapter_plus_QA_receipts_no_owner_broker_or_model')
        report['success'] = all(row['assessment']['passed'] for row in rows)
    except BaseException as exc:
        report['error'] = dict(type=type(exc).__name__, message=str(exc))
    finally:
        if session is not None:
            try:
                product.close_product(session)
            except BaseException as exc:
                report['product_close_error'] = dict(type=type(exc).__name__, message=str(exc))
                report['success'] = False
            report['close'] = session.close()
            report['worker_terminal'] = session.status()['closed']
            report['success'] = bool(report['success'] and report['close']['process_reaped']
                and report['close']['exit_code'] == 0 and report['close']['error'] is None
                and report['close']['source_file_unchanged'] and report['close']['protected_files_unchanged']
                and type(report['worker_terminal']) is dict
                and report['worker_terminal']['initial_geometry_fingerprint']
                    == report['worker_terminal']['final_geometry_fingerprint'])
        report['final_source_sha256'] = sha(asset)
        need(report['final_source_sha256'] == source_hash, 'local_source_asset_unchanged')
        save(args.output/(case_id+'_'+api+'_RESULT.json'), report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--assets', type=Path, required=True)
    parser.add_argument('--blender', type=Path, required=True)
    parser.add_argument('--pin', required=True)
    args = parser.parse_args()
    args.output = args.output.resolve()
    args.assets = args.assets.resolve()
    args.blender = args.blender.resolve()
    args.output.mkdir(parents=True, exist_ok=False)
    identity = bind_candidate(args.pin)
    started = time.perf_counter_ns()
    deadline = started+240*10**9
    save(args.output/'RUNTIME.json', identity)
    save(args.output/'RUN_SPEC.json', dict(schema='perf010-local-cost-v1', runner_sha256=sha(__file__),
        installed_root=str(ROOT), python_executable=sys.executable, pin=args.pin,
        started_ns=started, original_deadline_ns=deadline, cases=CASES,
        requests_per_api_case=dict(cold_after_preflight=1, warm=5, separate_instrumented=1),
        scope='local_QA_only_no_model_answers_no_model_benefit_or_owner_broker_claim',
        old_api='actual_prebound_ID_exact_pairs_budget1_alignment_false_brief_or_unpaired_overview',
        new_api='same_needed_facts_task_query_with_exact_names',
        immutable_source_assets=True, no_product_setters_or_saves=True,
        preflight_separate=True, cold_scope='first_measured_API_request_after_service_and_capture_preflight'))
    reports = []
    for index, case in enumerate(CASES):
        for api in (('old', 'task') if index % 2 == 0 else ('task', 'old')):
            check(deadline)
            report = run_api(args, case, api, deadline)
            reports.append(report)
            print(json.dumps(dict(case=case[0], api=api, success=report['success'],
                timing=report.get('timing'), error=report.get('error')), ensure_ascii=False), flush=True)
    finished = time.perf_counter_ns()
    result = dict(schema='perf010-local-cost-result-v1', pin=args.pin,
        success=len(reports) == 2*len(CASES) and all(row['success'] for row in reports) and finished < deadline,
        started_ns=started, finished_ns=finished, elapsed_s=(finished-started)/1e9,
        cases=reports, scope='local_API_QA_only_model_quality_latency_cost_unmeasured')
    save(args.output/'SUMMARY.json', result)
    return 0 if result['success'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
