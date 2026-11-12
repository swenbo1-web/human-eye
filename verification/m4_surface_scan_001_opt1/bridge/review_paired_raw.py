"""Independent standard-library recalculation of the ten raw paired sequences."""
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import statistics
import sys


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
RUN = HERE.parent/'engineering/run_01'
ORDER = ['AB', 'BA', 'AB', 'BA', 'AB']
STATES = ('cold', 'repeat', 'edit')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def exact(value):
    return dict(numerator=value.numerator, denominator=value.denominator, value=float(value))


def main():
    inputs = {}
    def load(path):
        inputs[path.relative_to(ROOT).as_posix()] = sha(path)
        return read(path)
    frozen = load(RUN/'INPUT_BINDINGS.json')
    assert frozen['pair_orders'] == ORDER
    assert frozen['automatic_retries'] == frozen['evaluation_consumers'] == frozen['images'] == 0
    expected_plan = [(i, v, state) for i, order in enumerate(ORDER, 1) for v in order for state in STATES]
    assert [(r['pair'], r['version'], r['state']) for r in frozen['planned_business_rows']] == expected_plan
    sequences = {}
    rows = []
    observed_intervals = []
    reuse = []
    all_pids = set()
    cache_observations = []
    version_values = {v: {state: [] for state in STATES} for v in 'AB'}
    lifecycle = {v: [] for v in 'AB'}
    for index, order in enumerate(ORDER, 1):
        for version in order:
            folder = RUN/('pair_'+str(index).zfill(2))/version
            sequence = load(folder/'RESULTS.json')
            sequences[(index,version)] = sequence
            assert not sequence['errors'] and sequence['passed'] and sequence['source_files_unchanged']
            assert sequence['automatic_retries'] == 0 and sequence['metadata_zero_host_RPC']
            assert sequence['ended_ns']-sequence['started_ns'] == sequence['session_wall_ns']
            assert [r['state'] for r in sequence['business']] == list(STATES)
            observed_intervals.append((sequence['started_ns'],sequence['ended_ns'],index,version))
            lifecycle[version].append(sequence['session_wall_ns'])
            native = sequence['native_close']
            product = sequence['product_close']
            runtime = sequence['runtime_exit']
            assert native['process_reaped'] and native['exit_code'] == 0 and native['error'] is None
            assert native['protected_files_unchanged'] and native['source_file_unchanged']
            assert product['confirmed'] and product['process_reaped'] and product['reader_stopped']
            assert product['exit_code'] == 0 and product['error'] is None
            assert runtime['confirmed'] and runtime['exited'] and runtime['exit_code'] == 0 and runtime['handle_closed']
            closed = sequence['worker_closed']
            assert not closed['poisoned'] and closed['qa_patch_applied']
            assert closed['final_geometry_fingerprint'] == closed['accepted_geometry_fingerprint']
            assert native['pid'] not in all_pids and product['launcher_pid'] not in all_pids
            all_pids.update((native['pid'],product['launcher_pid']))
            previous_end = sequence['started_ns']
            current = {}
            for business in sequence['business']:
                state = business['state']
                assert previous_end <= business['started_ns'] < business['ended_ns'] <= sequence['ended_ns']
                previous_end = business['ended_ns']
                assert business['ended_ns']-business['started_ns'] == business['complete_client_request_ns']
                assert not business['errors']
                assert business['actual_host_RPC'] == 1
                assert business['stdio']['error'] is None and business['stdio']['send_confirmed']
                assert business['full_service_and_delivery_trace_ns'] <= business['complete_client_request_ns']
                spans = {r['name'] for r in business['span_timings_ns']}
                assert {'mcp.wire_encode','mcp.stdio_write'} <= spans
                work = business['diagnostics']
                expected_kernel = 112 if state == 'cold' else 0 if state == 'repeat' else 114 if version == 'A' else 10
                assert work['kernel_calls'] == expected_kernel
                assert work['candidate_pairs'] == (114 if state == 'edit' else 112)
                assert work['bound_pairs'] == len(work['dispositions']) == 276
                assert work['result_cache_hit'] == (state == 'repeat')
                pairs = work.get('pairs', {})
                assert len(pairs) == (0 if state == 'repeat' else work['candidate_pairs'])
                assert sum(p['surface_pair_count'] for p in pairs.values()) == expected_kernel
                acquisition = work['acquisition_work']['residency_delta']
                assert acquisition['world_vertices_transformed'] == (530 if state == 'cold' else 0 if state == 'repeat' else 8)
                assert acquisition['resource_vertices_read'] == (530 if state == 'cold' else 0)
                assert acquisition['resource_faces_read'] == (978 if state == 'cold' else 0)
                if version == 'B':
                    assert work['measurement_cache_max_measurements'] == 256
                    before, after = work['measurement_cache_before'], work['measurement_cache_after']
                    for sample in (before, after):
                        assert sample['max_bytes'] == 2097152
                        assert 0 <= sample['accounted_bytes'] <= sample['max_bytes']
                        assert 0 <= sample['measurement_entries'] <= 256
                    assert after['measurement_computations']-before['measurement_computations'] == expected_kernel
                    assert after['measurement_hits']-before['measurement_hits'] == (104 if state == 'edit' else 0)
                    if state == 'cold':
                        assert before['measurement_entries'] == before['measurement_computations'] == 0
                    cache_observations.append(dict(pair=index,state=state,before=before,after=after))
                else:
                    assert 'measurement_cache_before' not in work and 'measurement_cache_max_measurements' not in work
                rows.append(dict(pair=index,version=version,state=state,actual_RPC=1,
                    kernel_calls=expected_kernel,client_ns=business['complete_client_request_ns']))
                version_values[version][state].append(business['complete_client_request_ns'])
                current[state] = business
            if version == 'B':
                cold, edit = current['cold']['diagnostics']['pairs'], current['edit']['diagnostics']['pairs']
                moving = {obj['id'] for match in current['edit']['body']['matches'] for obj in match['objects']
                          if obj['name'] == 'Obj_008'}
                assert len(moving) == 1
                moved_id = next(iter(moving))
                hits, misses = [], []
                for pair_key, pair in edit.items():
                    ids = json.loads(pair_key)
                    assert pair['surface_dependency_used']
                    if moved_id in ids:
                        assert not pair['surface_dependency_cache_hit'] and not pair['surface_pair_cache_hit']
                        assert pair['surface_pair_count'] == 1
                        assert pair_key not in cold or pair['surface_dependency_key'] != cold[pair_key]['surface_dependency_key']
                        misses.append(dict(object_ids=ids,key=pair['surface_dependency_key'],cold_present=pair_key in cold))
                    else:
                        assert pair_key in cold and pair['surface_dependency_cache_hit'] and pair['surface_pair_cache_hit']
                        assert pair['surface_pair_count'] == 0 and pair['surface_work'] == {}
                        assert pair['surface_dependency_key'] == cold[pair_key]['surface_dependency_key']
                        assert pair['surface_dependency_objects'] == cold[pair_key]['surface_dependency_objects']
                        hits.append(dict(object_ids=ids,key=pair['surface_dependency_key']))
                assert len(hits) == 104 and len(misses) == 10
                assert current['edit']['diagnostics']['cache_hits'] == 104
                reuse.append(dict(pair=index,moving_object_id=moved_id,hits=hits,misses=misses))
    assert len(rows) == len(set((r['pair'],r['version'],r['state']) for r in rows)) == 30
    actual_order = [(i,v) for start,end,i,v in sorted(observed_intervals)]
    assert actual_order == [(i,v) for i,order in enumerate(ORDER,1) for v in order]
    for previous,next_interval in zip(observed_intervals,observed_intervals[1:]):
        assert previous[1] <= next_interval[0]
    ratios = {state:[Fraction(n,o) for o,n in zip(version_values['A'][state],version_values['B'][state])]
              for state in STATES}
    differences = {state:[n-o for o,n in zip(version_values['A'][state],version_values['B'][state])]
                   for state in STATES}
    edit_ratio = statistics.median(ratios['edit'])
    cold_allowance = max(Fraction(statistics.median(version_values['A']['cold']),20),2000000)
    repeat_allowance = max(Fraction(statistics.median(version_values['A']['repeat']),20),2000000)
    sums = {v:[sum(version_values[v][s][i] for s in STATES) for i in range(5)] for v in 'AB'}
    sum_ratios = [Fraction(n,o) for o,n in zip(sums['A'],sums['B'])]
    life_ratios = [Fraction(n,o) for o,n in zip(lifecycle['A'],lifecycle['B'])]
    gates = dict(edit=edit_ratio <= Fraction(7,10),
        cold=statistics.median(differences['cold']) <= cold_allowance,
        repeat=statistics.median(differences['repeat']) <= repeat_allowance,
        business_sum=statistics.median(sum_ratios) < 1,
        lifecycle=statistics.median(life_ratios) <= Fraction(21,20))
    assert all(gates.values()), gates
    assert not any(name.startswith('human_eye') for name in sys.modules)
    result = dict(review='independent_standard_library_raw_pair_review',inputs=inputs,
        planned=30,actual=30,missing=0,duplicates=0,failures=0,observed_order=actual_order,
        rows=rows,client_values_ns=version_values,lifecycle_values_ns=lifecycle,
        ratios={s:[exact(x) for x in ratios[s]] for s in STATES},differences_ns=differences,
        business_sum_ratios=[exact(x) for x in sum_ratios],lifecycle_ratios=[exact(x) for x in life_ratios],
        edit_ratio_median=exact(edit_ratio),cold_allowance_ns=exact(cold_allowance),
        repeat_allowance_ns=exact(repeat_allowance),gates=gates,
        business_sum_ratio_median=exact(statistics.median(sum_ratios)),
        lifecycle_ratio_median=exact(statistics.median(life_ratios)),
        mechanism=dict(cold_new_kernels=112,repeat_new_kernels=0,baseline_edit_new_kernels=114,
            candidate_edit_new_kernels=10,candidate_edit_reused_unaffected_pairs=104,
            resource_vertices_read_on_edit=0,world_vertices_transformed_on_edit=8),
        reuse_mappings=reuse,candidate_cache_observations=cache_observations,
        baseline_cache_actual_counters_available=False,
        baseline_cache_note='Frozen initial product omits cache telemetry. Actual 2MiB/256 checks above cover B. A policy remains source-bound in the fixed initial installation.',
        all_ten_native_product_and_retained_runtime_exits_confirmed=True,
        unique_native_and_launcher_pids=len(all_pids),
        lifecycle_prefix_net_improvement=statistics.median(life_ratios)<1,
        lifecycle_scope='Recorded sequence prefix ends before final RESULTS serialization/write/close. The exact complete median is unmeasured.',
        lifecycle_full_gate_evidence='ROOT_LIFECYCLE_BOUND.json',
        lifecycle_full_median_upper_bound=read(HERE.parent/'ROOT_LIFECYCLE_BOUND.json')['median_ratio_upper_bound'],
        exact_full_lifecycle_median_measured=False,
        product_imports=0,Blender_runs=0,model_consumers=0)
    output = HERE/'PAIRED_RAW_REVIEW.json'
    with output.open('x',encoding='utf8',newline='\n') as stream:
        json.dump(result,stream,ensure_ascii=False,indent=2)
        stream.write('\n')
    print(json.dumps(dict(gates=gates,edit_ratio=float(edit_ratio),
        business_sum_ratio=float(statistics.median(sum_ratios)),lifecycle_ratio=float(statistics.median(life_ratios)),
        cold_difference_median_ms=statistics.median(differences['cold'])/1e6,
        repeat_difference_median_ms=statistics.median(differences['repeat'])/1e6,
        rows=len(rows),input_files=len(inputs))))


if __name__ == '__main__':
    main()
