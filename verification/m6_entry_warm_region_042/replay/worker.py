"""One fresh installed-runtime process for a paired fixed-capture stage replay."""
from __future__ import annotations
import argparse
from contextlib import contextmanager
import json
from pathlib import Path
import sys
import time
import traceback

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from replay_common import dump, installation, need, pin, read, verify
from qualification import check_public


@contextmanager
def observe(module, enabled, samples):
    originals = {}
    if enabled:
        for name in ('measure_surface_proximity', '_witness_sources'):
            original = getattr(module, name)
            originals[name] = original
            def wrapped(*args, _function=original, _name=name, **kwargs):
                started = time.perf_counter_ns()
                try:
                    return _function(*args, **kwargs)
                finally:
                    closed = time.perf_counter_ns()
                    samples.append({'name': _name, 'started_ns': started, 'closed_ns': closed,
                                    'elapsed_ns': closed-started})
            setattr(module, name, wrapped)
    try:
        yield
    finally:
        for name, original in originals.items():
            setattr(module, name, original)


def main(plan_path, arm, group, output):
    output = Path(output)
    plan = read(plan_path)
    receipt = {'status': 'failed', 'arm': arm, 'group': group, 'plan': pin(plan_path),
               'rows': [], 'native_calls': 0, 'scope': plan['scope']}
    try:
        for ref in plan['sources'].values():
            verify(ref)
        verify(plan['capture'])
        installed = installation(arm)
        need(installed == plan['arms'][arm], 'installed_identity_changed')
        receipt['installation'] = installed
        sys.path.insert(0, installed['site_packages'])
        from human_eye_plugin import source_region as sr
        from human_eye_plugin.live_service import LiveSpatialService
        from human_eye_plugin import mcp_transport as wire
        # Imports and full installation verification occur outside request clocks.
        raw = Path(plan['capture']['path']).read_bytes()
        materialized = json.loads(raw)
        class FrozenHost:
            _readonly_host_source_sha256 = materialized['binding']['host_source_sha256']
            def __init__(self):self.calls = 0
            def capture_source_region_pair(self, target, reference, box, deadline_ns, max_response_bytes):
                need(time.perf_counter_ns() < deadline_ns, 'frozen_host_original_deadline')
                need(target == materialized['binding']['target_selector'] and reference == materialized['binding']['reference_selector']
                     and box == materialized['binding']['world_box_m'], 'frozen_host_request_drift')
                self.calls += 1
                return json.loads(raw)
        host = FrozenHost()
        config = {'schema_version': '1.0', 'enabled': True, 'observe_on_prompt': False,
                  'project_root': installed['site_packages'], 'state_file': str(output/'STATE.json'),
                  'audit_file': str(output/'AUDIT.jsonl'), 'request_budget_s': plan['request_budget_s'],
                  'expected_identity': {'source_sha256': installed['identity']['source_sha256']}}
        dump(output/'CONFIG.json', config)
        service = LiveSpatialService(output/'CONFIG.json', host=host)
        query = sr.validate_scoped_measurement_arguments({'include_image': False, 'query': plan['query']})
        receipt['normalized_query'] = query
        for phase in plan['phase_orders'][group-1]:
            for label in plan['reads_per_phase']:
                samples = []
                with observe(sr, phase == 'substages', samples), service._request_budget():
                    started = time.perf_counter_ns()
                    value = service._measure_selective_source_region('m6-042-offline-replay', query, include_image=False)
                    measured = time.perf_counter_ns()
                    public = sr.project_scoped_measurement(value, query)
                    projected = time.perf_counter_ns()
                    text = json.dumps(public, ensure_ascii=False, allow_nan=False, separators=(',', ':'))
                    content_encoded = time.perf_counter_ns()
                    response = {'jsonrpc': '2.0', 'id': 'replay', 'result': {'content': [{'type': 'text', 'text': text}], 'isError': False}}
                    encoded = wire.encode_response(response)
                    closed = time.perf_counter_ns()
                    service._check_request_budget('before_replay_publication', publication=True)
                check_public(public, plan['expected_public'])
                stages = value['stages']
                stages_current = {name: stages[name] for name in ('host_read','capture_validation','region_array_preparation','task_measurement','service_total')}
                intervals = [(s['started_ns'],s['closed_ns']) for name,s in stages_current.items() if name != 'service_total']
                need(all(started <= a <= b <= measured for a,b in intervals), 'stage_clock_scope')
                ordered = sorted(intervals)
                need(all(a[1] <= b[0] for a,b in zip(ordered,ordered[1:])), 'nonoverlapping_top_level_stages')
                elapsed = {k: s['elapsed_ns'] for k,s in stages_current.items()}
                elapsed.update(measure_service_call_ns=measured-started, projection_ns=projected-measured,
                    content_encode_ns=content_encoded-projected, wire_encode_ns=closed-content_encoded,
                    replay_pipeline_ns=closed-started,
                    service_unassigned_ns=(measured-started)-sum(elapsed[k] for k in ('host_read','capture_validation','region_array_preparation','task_measurement')))
                if samples:
                    need(sum(s['name']=='measure_surface_proximity' for s in samples)==1 and sum(s['name']=='_witness_sources' for s in samples)==2, 'observer_call_count')
                    elapsed['solver_ns'] = sum(s['elapsed_ns'] for s in samples if s['name']=='measure_surface_proximity')
                    elapsed['witness_membership_ns'] = sum(s['elapsed_ns'] for s in samples if s['name']=='_witness_sources')
                    elapsed['measurement_unassigned_ns'] = elapsed['task_measurement']-elapsed['solver_ns']-elapsed['witness_membership_ns']
                    need(elapsed['measurement_unassigned_ns'] >= 0, 'nested_measurement_accounting')
                row = {'phase': phase, 'read': label, 'timing_ns': elapsed, 'stage_intervals': stages_current,
                       'observer_intervals': samples, 'public': public, 'work': value['work'],
                       'witness_provenance': value.get('witness_provenance'),
                       'nearest_witness_source': value['source_mapping']['nearest_witness'],
                       'wire_bytes': len(encoded), 'host_capture_stages_historical_not_added': stages['host_capture'],
                       'current_original_budget_passed': True}
                dump(output/(phase+'_'+label+'.json'), row)
                receipt['rows'].append(row)
        receipt.update(status='pass', frozen_packet_reads=host.calls, checks={'same_fixed_public_fields_all_four':True,
                'original_measurement_options_unchanged':True, 'original_30s_service_budget':True,
                'original_kernel_work_limits':True, 'no_product_result_cache':True})
    except BaseException:
        receipt['error'] = traceback.format_exc()
    dump(output/'RESULT.json', receipt)
    print(json.dumps({'status':receipt['status'],'result':pin(output/'RESULT.json')}), flush=True)
    return 0 if receipt['status']=='pass' else 1


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--plan',required=True)
    parser.add_argument('--arm',choices=('032','r3'),required=True)
    parser.add_argument('--group',type=int,required=True)
    parser.add_argument('--output',required=True)
    args=parser.parse_args()
    raise SystemExit(main(args.plan,args.arm,args.group,args.output))
