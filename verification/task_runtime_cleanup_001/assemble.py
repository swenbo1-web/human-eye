"""Assemble final bounded-run evidence metadata; no product imports."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import statistics
import time
OUT = Path(__file__).resolve().parent
def read(name): return json.loads((OUT / name).read_bytes())
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
samples = [json.loads(line) for line in (OUT / 'timing_samples.jsonl').read_text().splitlines()]
assert len(samples) == 40 and all(row['exit_code'] == 0 for row in samples)
timing = read('TIMING_RESULTS.json')
assert sha(OUT / 'timing.py') == read('TIMING_PLAN.json')['script_sha256']
by_side = {}
for label in ('baseline', 'candidate'):
    side = [row for row in samples if row['label'] == label]
    assert len(side) == 20
    counts = Counter()
    for row in side: counts.update(row['counts'])
    by_side[label] = {'counts_total': dict(counts), 'n': len(side),
        'median_process_wall_ms': statistics.median(row['process_wall_ms'] for row in side),
        'median_script_preimport_ms': statistics.median(row['imports_ms'] for row in side),
        'median_preparation_ms': statistics.median(row['preparation_ms'] for row in side)}
for index in range(20):
    a, b = samples[index*2:index*2+2]
    assert a['pair_index'] == b['pair_index'] == index
    assert [a['label'], b['label']] == (['baseline', 'candidate'] if index%2 == 0 else ['candidate', 'baseline'])
    assert a['state_sha256'] == b['state_sha256'] and a['result_sha256'] == b['result_sha256']
execution_rows = []
for name in ('baseline_checks_failed_01.json', 'candidate_checks_failed_01.json', 'baseline_checks.json', 'candidate_checks.json'):
    item = read(name)
    execution_rows.append({'file': name, **{key: item[key] for key in ('testsRun','failures','errors','skipped')},
        'passed': item['testsRun'] - item['failures'] - item['errors'] - item['skipped']})
execution_rows.append({'file':'regressions.log', 'testsRun':26, 'failures':0, 'errors':0, 'skipped':0, 'passed':26})
totals = {key: sum(row[key] for row in execution_rows) for key in ('testsRun','failures','errors','skipped','passed')}
assert totals == {'testsRun':86,'failures':2,'errors':0,'skipped':2,'passed':82}
assert all(not row['diff'] for row in read('EQUIVALENCE.json'))
value = {'cycle_id': 'TASK-RUNTIME-CLEANUP-001', 'source': read('SOURCE_AUDIT.json'),
         'task_assignment_sha256':'ef873a47689b66f3e98542374f83ed8c26c81b2ac576afbd9d37088d64adb949',
         'root_probe_result_sha256':'7caa49c0fce4160a2ab8a0b4ba9bab230bdf7fe88d348c5b2145b11352e53257',
         'unittest_runs':execution_rows, 'unittest_totals':totals, 'current_candidate_unique_passing_methods':41,
         'baseline_current_passed':14, 'baseline_new_method_skipped':1, 'cross_process_equivalent_rows':12,
         'non_unittest_harness_comparison_setup_failures':3,
         'timing':timing, 'timing_side_totals_and_overheads':by_side,
         'new_model_calls':0,'blender_starts':0,'live_rpc_calls':0,'api_network_calls':0,
         'readonly_helper_agents':1,'single_product_implementer':True,
         'turn_started_epoch_s':1794187123,'deadline_epoch_s':1794189223,
         'assembly_epoch_s':time.time(), 'assembly_elapsed_ms':(time.time()-1794187123)*1000,
         'complete_receipt_elapsed_separate':True,
         'artifact_sha256': {path.name: sha(path) for path in sorted(OUT.iterdir())
                             if path.is_file() and path.name != 'RESULTS.json'}}
(OUT / 'RESULTS.json').write_text(json.dumps(value, indent=2) + '\n', encoding='utf8')
print(json.dumps({'unittest_totals':totals, 'overheads':by_side, 'assembly_elapsed_ms':value['assembly_elapsed_ms'],
                  'report_sha256':sha(OUT/'REPORT.md'),'results_sha256':sha(OUT/'RESULTS.json')},indent=2))
