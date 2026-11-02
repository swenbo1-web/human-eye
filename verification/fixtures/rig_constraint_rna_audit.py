"""Test-only outside observer executing the exact installed/source worker bytes."""
import argparse,hashlib,importlib.util,json,os,sys
from pathlib import Path
import bpy
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from verification.run_rig_evaluation_preflight import outside_observer
p=argparse.ArgumentParser()
for name in ('root','profile'):p.add_argument('--'+name,type=Path,required=True)
for name in ('profile-sha256','module-sha256','math-sha256'):p.add_argument('--'+name,required=True)
p.add_argument('--deadline-ns',type=int,required=True);args=p.parse_args(sys.argv[sys.argv.index('--')+1:])
output=Path(os.environ['HUMAN_EYE_CONSTRAINT_AUDIT_OUTPUT']).resolve();assert output.is_relative_to(ROOT/'verification/fixes')
def save(name,value):
    with (output/name).open('x',encoding='utf8') as f:json.dump(value,f,sort_keys=True,allow_nan=False)
before=outside_observer(bpy);save('INDEPENDENT_BEFORE.json',before)
path=args.root/'human_eye_plugin/rig_constraint_worker.py';blob=path.read_bytes()
spec=importlib.util.spec_from_file_location('_audited_constraint_worker',path);module=importlib.util.module_from_spec(spec)
exec(compile(blob,str(path),'exec',dont_inherit=True),module.__dict__)
try:module.run(args)
finally:
    after=outside_observer(bpy);save('INDEPENDENT_AFTER.json',after)
    save('INDEPENDENT_RESULT.json',dict(identical=before==after,test_wrapper_used=True,
        exact_product_worker_sha256=hashlib.sha256(blob).hexdigest(),shared_GUI=False))
