"""Freeze pre-implementation inputs, fixed workload and actual old work receipt."""
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))
from human_eye_plugin.query_policy import validate_query

sha = lambda raw: hashlib.sha256(raw).hexdigest()
selected = {'mode': 'task', 'objects': [{'name': 'M4_Focal'}, {'name': 'M4_Near'}],
            'requested_facts': ['aabb', 'axis_gap', 'surface_proximity']}
validate_query(selected)
inputs = json.loads((HERE / 'assets_01/INPUTS.json').read_bytes())
receipt = json.loads((HERE / 'baseline_01/RESULTS.json').read_bytes())
assert receipt['passed']
assert receipt['rows'][0]['work_events'][0]['m2_work']['new_resource_arrays'] == {
    'vertices': 3474, 'faces': 6146, 'edges': 9606}
assert receipt['rows'][1]['work_events'][0]['m2_work']['new_resource_arrays'] == {
    'vertices': 0, 'faces': 0, 'edges': 0}
paths = ['CONTRACT.md', 'build_inputs.py', 'owned_native.py', 'OWNED_NATIVE.diff',
         'wire_meter.py', 'probe.py', 'freeze_baseline.py', 'assets_01/INPUTS.json',
         'baseline_01/RESULTS.json']
result = {'status': 'BASELINE_FROZEN', 'product_commit': '00b13060a3cbe709b38f6e98ce04a6e5c3dabfb4',
          'product_source_sha256': '4ebc3910652ee461d9fa7476c8df0ecf6312580d6a02e1066c0eac88bef5c76c',
          'files': {path: sha((HERE/path).read_bytes()) for path in paths},
          'assets': [{key: row[key] for key in ('name','asset','asset_sha256','object_count','vertex_count','polygon_count')}
                     for row in inputs['inputs']], 'selected_query': selected,
          'pure_sessions': 27, 'two_step_sessions': 9,
          'old_confirmation_is_excluded_from_final_matrix': True,
          'native_controller_implementation': 'pending, fixed workload and gates cannot change',
          'old_actual_work': [dict(index=row['index'], host_RPC=row['host_RPC'], wire=row['wire'],
                                  arrays=row['work_events'][0]['m2_work']['new_resource_arrays'])
                              for row in receipt['rows']]}
with (HERE/'BASELINE_FROZEN.json').open('x', encoding='utf8', newline='\n') as stream:
    json.dump(result, stream, indent=2, allow_nan=False)
    stream.write('\n')
print(json.dumps({'status': result['status'], 'sha256': sha((HERE/'BASELINE_FROZEN.json').read_bytes())}))
