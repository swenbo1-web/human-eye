"""Initial four-case distance counts, separate from the frozen five-call timing."""
import hashlib
import json
from pathlib import Path
import sys
import time
import types

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
snapshot_path = ROOT/'verification/spatial_task_qualification_001/entry/run_01/ACTUAL_SNAPSHOT.json'
initial = json.loads((HERE/'INITIAL_SOURCE.json').read_bytes())
assert hashlib.sha256((ROOT/'human_eye_plugin/surface_proximity.py').read_bytes()).hexdigest()==initial['sha256']
package = types.ModuleType('_m3_initial_distance')
package.__path__ = []
sys.modules[package.__name__] = package
sources = {}
for name in ('surface_geometry','surface_proximity'):
    path = ROOT/'human_eye_plugin'/(name+'.py')
    raw = path.read_bytes()
    module = types.ModuleType(package.__name__+'.'+name)
    module.__file__ = str(path)
    sys.modules[module.__name__] = module
    setattr(package,name,module)
    exec(compile(raw,str(path),'exec',dont_inherit=True),module.__dict__)
    sources[name] = hashlib.sha256(raw).hexdigest()
snapshot = json.loads(snapshot_path.read_bytes())
meshes = {row['name']:types.SimpleNamespace(vertices=row['vertices_world'],faces=row['triangles'])
          for row in snapshot['objects']}
results = []
for target,candidate in (('Target','Peer_000'),('Target','Competing_001'),('Target','Near_003'),('Control_A','Control_B')):
    started = time.perf_counter_ns()
    deadline = started+30*10**9
    def checkpoint(stage):
        if time.perf_counter_ns()>=deadline:
            raise TimeoutError('original_30_second_reference_window:'+stage)
    value = package.surface_proximity.measure_surface_proximity(meshes[target],meshes[candidate],checkpoint,
                                                               retain_exact_rank=True)
    results.append({'target':target,'candidate':candidate,'elapsed_ns':time.perf_counter_ns()-started,'result':value})
output = {'source':sources,'snapshot_sha256':hashlib.sha256(snapshot_path.read_bytes()).hexdigest(),
          'scope':'first fixed candidate counts; not the final five-call timing or actual MCP qualification',
          'results':results}
with (HERE/'COUNTS_01.json').open('x',encoding='utf8',newline='\n') as stream:
    json.dump(output,stream,indent=2,allow_nan=False)
    stream.write('\n')
print(json.dumps([{'candidate':row['candidate'],'valid':row['result']['measurement_valid'],
                  'reason':row['result'].get('reason'),'distance':row['result']['distance_m'],
                  'narrow':row['result']['work']['intersection_tests'],
                  'work':row['result']['work']['work_units']} for row in results]))
