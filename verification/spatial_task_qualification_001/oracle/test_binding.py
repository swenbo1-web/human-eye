"""Finite synthetic source-binding counterexamples; no geometry solver."""

import copy
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import socket
import subprocess
import sys
from unittest.mock import patch


HERE = Path(__file__).resolve().parent


def main():
    output = HERE/'binding_checks_01'
    output.mkdir(exist_ok=False)
    source = HERE/'verify_actual.py'
    spec = importlib.util.spec_from_file_location('_qualification_pure_source_binding',source)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    original = json.loads((HERE.parent/'assets/BUILD_SNAPSHOT.json').read_bytes())
    rows, attempts = [], []

    def blocked(*args, **kwargs):
        attempts.append('external process or socket')
        raise AssertionError(attempts[-1])

    def check(name, snapshot, expected_error=None):
        before = module.digest(snapshot)
        try:
            result = module.bind_actual(snapshot)
            passed = expected_error is None and result['passed'] is True
            record = {'case':name,'expected_error':expected_error,'actual_error':None,
                'passed':passed,'binding':result}
        except ValueError as exception:
            message = str(exception)
            passed = expected_error is not None and message == expected_error
            record = {'case':name,'expected_error':expected_error,'actual_error':message,'passed':passed}
        record['input_sha256'] = before
        record['input_unchanged'] = before == module.digest(snapshot)
        record['passed'] = record['passed'] and record['input_unchanged']
        rows.append(record)

    with patch.object(subprocess,'Popen',side_effect=blocked), patch.object(socket,'socket',side_effect=blocked):
        check('frozen_build_actual_source',copy.deepcopy(original))
        changed = copy.deepcopy(original)
        changed['objects'].pop()
        check('missing_object',changed,'actual_directory_count')
        changed = copy.deepcopy(original)
        changed['objects'][0]['vertices_world'][0][0] = math.nextafter(changed['objects'][0]['vertices_world'][0][0],math.inf)
        check('one_binary64_ulp_world_change',changed,'actual_vertex_not_in_frozen_source:Competing_001')
        changed = copy.deepcopy(original)
        changed['objects'][0]['matrix_world'][0][3] = math.nextafter(changed['objects'][0]['matrix_world'][0][3],math.inf)
        check('one_binary64_ulp_pose_change',changed,'source_field_mismatch:Competing_001:matrix_world')
        changed = copy.deepcopy(original)
        triangle = changed['objects'][0]['triangles'][0]
        triangle[1],triangle[2] = triangle[2],triangle[1]
        check('orientation_reversal',changed,'oriented_triangle_surface_changed:Competing_001')
        changed = copy.deepcopy(original)
        changed['scale_length'] = .25
        check('unit_change',changed,'snapshot_context_mismatch:scale_length')
        changed = copy.deepcopy(original)
        changed['objects'][0]['object_id'] = 'blender:' + '0'*64
        check('identity_mismatch',changed,'source_identity_mismatch:Competing_001:object_id')
        changed = copy.deepcopy(original)
        row = next(row for row in changed['objects'] if row['name']=='Target')
        count = len(row['vertices_local'])
        row['vertices_local'].reverse()
        row['vertices_world'].reverse()
        row['triangles'] = [[count-1-i for i in tri[1:]+tri[:1]] for tri in reversed(row['triangles'])]
        check('bijective_reindex_and_cyclic_face_rotation',changed)
        mapping = next(row for row in rows[-1]['binding']['source_surface_mappings'] if row['name']=='Target')
        rows[-1]['passed'] = rows[-1]['passed'] and mapping['mode']=='exact_oriented_surface_reindex'
    result = {'synthetic':True,'passed':all(row['passed'] for row in rows) and not attempts,
        'checks':len(rows),'rows':rows,'external_attempts':attempts,'product_calls':0,'model_consumers':0,
        'Blender_sessions':0,'oracle_replays':0,
        'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'verifier_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
        'scope':'finite metadata/source-contract counterexamples, separate from business task denominators'}
    with (output/'RESULTS.json').open('x',encoding='utf8',newline='\n') as stream:
        json.dump(result,stream,ensure_ascii=False,sort_keys=True,indent=2);stream.write('\n')
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
