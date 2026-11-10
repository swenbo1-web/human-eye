"""Compare root-replayed raw results with narrowly named evidence projection."""
import copy
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OLD = '7a3d108bc5658508d76d98fe24b8f3dee4feac2d50856202b2ea7395c3dc9cc1'
NEW = '53db41976085ce5f361d026196f4da5faf80d639af33dfced35ba58e328ef732'
data = [json.loads((ROOT/name/'EVIDENCE.json').read_bytes())
        for name in ('root_baseline', 'root_candidate')]
key = next(k for k in data[0] if k.endswith(':LocalRelationEvidenceTests'))
checks, differences = [], []

def without_new_fact(value):
    result = copy.deepcopy(value)
    result.pop('trace_id', None)
    result.pop('local_evidence', None)
    if 'facts' in result:
        result['facts'].get('closed_solid_relation', {}).pop('local_evidence', None)
    for pair in result.get('pairs', []):
        pair.get('facts', {}).get('closed_solid_relation', {}).pop('local_evidence', None)
    for pair in result.get('candidates', []):
        pair.get('closed_solid_relation', {}).pop('local_evidence', None)
    return result

def compare(a, b, path):
    if type(a) != type(b):
        differences.append(dict(path=path, old=a, new=b))
    elif isinstance(a, dict):
        for k in sorted(a.keys() | b.keys()):
            if k not in a or k not in b:
                differences.append(dict(path=path+'/'+k, kind='key'))
            else:
                compare(a[k], b[k], path+'/'+k)
    elif isinstance(a, list):
        if len(a) != len(b):
            differences.append(dict(path=path, kind='length'))
        else:
            for i, (x, y) in enumerate(zip(a, b)):
                compare(x, y, path+'/'+str(i))
    elif a != b:
        differences.append(dict(path=path, old=a, new=b))

raw_core_checks = 0
for case, old in data[0][key].items():
    new = data[1][key][case]
    for row in (old, new):
        assert without_new_fact(row['result']) == row['core'], case
        raw_core_checks += 1
    for field in ('input', 'diagnostics', 'calls', 'loop_counts', 'loop_work_amounts',
                  'capture_calls', 'host_rpc_calls', 'host_write_calls', 'checkpoint_counts'):
        if field in old or field in new:
            checks.append(dict(case=case, field=field, equal=old.get(field)==new.get(field)))
    compare(without_new_fact(old['result']), without_new_fact(new['result']), case+'/core')

source_paths = {case+'/core/binding/runtime_source_sha256' for case in
               ('service_cold','service_warm','service_same_geometry_new_generation',
                'service_geometry_changed','public_ordinary')}
source_paths.add('public_compact/core/context/runtime_source_sha256')
meaning_path = 'public_compact/core/context/certificate_scope'
assert {d['path'] for d in differences} == source_paths | {meaning_path}
for d in differences:
    if d['path'] in source_paths:
        assert (d['old'], d['new']) == (OLD, NEW)
    else:
        assert d['old'] == 'Proof category only; surface witnesses are not shared-interior proofs.'
        assert d['new'] == ('Certificate category with local evidence when available. '
            'Transverse evidence identifies current captured triangles and approximates their boundary crossing; '
            'the exact midpoint is on both boundaries, not in their shared volume interior. '
            'Neither a boundary location nor surface distance is penetration depth.')
assert all(c['equal'] for c in checks)
result = dict(cases=len(data[0][key]), raw_core_checks=raw_core_checks,
              comparisons=len(checks), all_equal=True, allowed_core_differences=differences,
              checks=checks, product_runs='existing root replay only; no product execution by this script')
(ROOT/'ROOT_COMPARISON.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf8')
print(json.dumps({k:v for k,v in result.items() if k not in ('checks','allowed_core_differences')}))
