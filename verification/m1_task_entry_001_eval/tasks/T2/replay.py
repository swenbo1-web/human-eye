"""Replay only independent truth on the retained actual evaluated snapshot."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

HERE=Path(__file__).resolve().parent
p=argparse.ArgumentParser()
p.add_argument('--output',required=True,help='new certification JSON file in this task directory')
args=p.parse_args()
output=HERE/args.output
assert output.parent.resolve()==HERE.resolve() and not output.exists()
seal=json.loads((HERE/'FREEZE.json').read_bytes())
for name,digest in seal['source_sha256'].items():
    assert hashlib.sha256((HERE/name).read_bytes()).hexdigest()==digest
command=[sys.executable,'-I','-B','-X','utf8',str(HERE/'certify.py'),'--spec',str(HERE/'SPEC.json'),
    '--snapshot',str(HERE/'assets/evaluated_mesh.json'),'--output',str(output)]
# Isolated Python omits the script directory; use the explicit, fixed helper
# bootstrap below rather than an environment-dependent import path.
command=[sys.executable,'-I','-B','-X','utf8','-c',
    'import runpy,sys;sys.path.insert(0,sys.argv[1]);sys.argv=sys.argv[2:];runpy.run_path(sys.argv[0],run_name="__main__")',
    str(HERE),str(HERE/'certify.py'),'--spec',str(HERE/'SPEC.json'),
    '--snapshot',str(HERE/'assets/evaluated_mesh.json'),'--output',str(output)]
start=time.perf_counter_ns()
process=subprocess.run(command,capture_output=True,timeout=120)
log=output.with_suffix('.replay.json')
with log.open('x',encoding='utf8') as stream:
    json.dump({'command':command,'started_ns':start,'ended_ns':time.perf_counter_ns(),
        'timeout_s':120,'returncode':process.returncode,'stdout':process.stdout.decode('utf8','replace'),
        'stderr':process.stderr.decode('utf8','replace')},stream,indent=2)
assert process.returncode==0
original=json.loads((HERE/'TRUTH.json').read_bytes());actual=json.loads(output.read_bytes())
assert actual==original
print(json.dumps({'replay_equal':True,'output':str(output),'returncode':process.returncode}))
