"""Seal only this new batch and the single product source member."""
from pathlib import Path
import hashlib,json
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
files={str(p.relative_to(HERE)).replace('\\','/'):sha(p) for p in sorted(HERE.rglob('*')) if p.is_file() and p.name!='SEAL.json'}
surface=ROOT/'human_eye_plugin/surface_proximity.py'
assert sha(surface)=='2c471262b29101439293a172820c7d9183f840492d6ca2250f72122c5548cce3'
value={'task':'SCALE-OPT-001','parent_commit':'b39a5d9f58aed2782225287738413982beac4920','file_count':len(files),
       'batch_bytes':sum((HERE/name).stat().st_size for name in files),'files':files,
       'product_source':{'human_eye_plugin/surface_proximity.py':sha(surface)},
       'scope':'new batch only; original SCALE-DIAG fixture/oracle/install sources referenced by frozen hashes, not copied; isolated candidate runtime retained locally',
       'candidate_canonical':'3fc2651e108ad7ac252394871d78e1abaee1200c92a018125984b2fc240193bd',
       'default_configuration_changed':False,'admin_acceptance_pending':True}
target=HERE/'SEAL.json';assert not target.exists()
target.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf8',newline='\n')
print(json.dumps({'file_count':len(files),'bytes':value['batch_bytes'],'seal_sha256':sha(target)}))
