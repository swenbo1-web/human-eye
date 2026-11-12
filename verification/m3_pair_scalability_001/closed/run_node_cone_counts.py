"""One frozen node-cone candidate count capture over the frozen four pairs."""
import hashlib
import json
from pathlib import Path
import sys
import time
import traceback
import types


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SNAPSHOT = ROOT / 'verification/spatial_task_qualification_001/entry/run_01/ACTUAL_SNAPSHOT.json'


def main():
    output = HERE / 'node_cone_counts_01'
    output.mkdir(exist_ok=False)
    initial = json.loads((HERE / 'node_cone_01/SOURCE.json').read_bytes())
    package = types.ModuleType('_m3_closed_initial')
    package.__path__ = []
    sys.modules[package.__name__] = package
    identities = {}
    for name in ('surface_proximity', 'surface_geometry'):
        path = ROOT / 'human_eye_plugin' / (name + '.py')
        raw = path.read_bytes()
        identities[name] = hashlib.sha256(raw).hexdigest()
        if name == 'surface_geometry':
            assert identities[name] == initial['source_sha256']
        module = types.ModuleType(package.__name__ + '.' + name)
        module.__package__ = package.__name__
        module.__file__ = str(path)
        sys.modules[module.__name__] = module
        setattr(package, name, module)
        exec(compile(raw, str(path), 'exec', dont_inherit=True), module.__dict__)
    snapshot_raw = SNAPSHOT.read_bytes()
    snapshot = json.loads(snapshot_raw)
    meshes = {row['name']: types.SimpleNamespace(vertices=row['vertices_world'], faces=row['triangles'])
              for row in snapshot['objects']}
    rows = []
    for target, candidate in (('Target', 'Peer_000'), ('Target', 'Competing_001'),
                              ('Target', 'Near_003'), ('Control_A', 'Control_B')):
        started = time.perf_counter_ns()
        deadline = started + 30_000_000_000
        stages = {}

        def checkpoint(stage):
            stages[stage] = stages.get(stage, 0) + 1
            if time.perf_counter_ns() >= deadline:
                raise TimeoutError('original_30s_count_capture_deadline')

        work = {}
        holder = {}
        row = {'target': target, 'candidate': candidate, 'work': work}
        try:
            row['result'] = package.surface_geometry.classify_closed_solids(
                meshes[target], meshes[candidate], checkpoint,
                diagnostics=work, prepared_holder=holder)
            row['holder_trees_present'] = 'trees' in holder
            if 'trees' in holder:
                pair = holder['pair']
                row['holder_identity_valid'] = (holder['trees']['pair'] is pair
                    and all(actual is prepared for actual, prepared in zip(holder['trees']['triangles'], pair[4])))
        except BaseException as error:
            row['error'] = {'type': type(error).__name__, 'message': str(error), 'traceback': traceback.format_exc()}
        row['elapsed_ns_for_attribution_only'] = time.perf_counter_ns() - started
        row['checkpoint_counts'] = stages
        rows.append(row)
        with (output / (candidate + '.json')).open('x', encoding='utf8', newline='\n') as stream:
            json.dump(row, stream, indent=2, allow_nan=False)
            stream.write('\n')
    report = {'scope': 'one frozen node-cone optimization, one call per fixed pair, not finite timing acceptance',
              'source_sha256': identities, 'snapshot_sha256': hashlib.sha256(snapshot_raw).hexdigest(),
              'runner_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'closed_budgets': {'work': 262144, 'full_self_cross_pairs': 16384, 'ray_tests': 16384},
              'rows': rows, 'Blender_starts': 0, 'models': 0, 'actual_business_calls': 0}
    with (output / 'RESULTS.json').open('x', encoding='utf8', newline='\n') as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'output': str(output), 'rows': [
        {'candidate': row['candidate'], 'measurement_valid': row.get('result', {}).get('measurement_valid'),
         'relation': row.get('result', {}).get('relation'), 'reason': row.get('result', {}).get('reason'),
         'work': row['work'], 'error': row.get('error')} for row in rows]}))


if __name__ == '__main__':
    main()
