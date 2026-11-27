"""043 untimed holdout provenance helpers; no product/host imports."""
from pathlib import Path
import hashlib
import json

HERE=Path(__file__).resolve().parent
VER=HERE.parents[1]
RAW=Path('D:/HumanEye/runs/M6-043-R3-REGION-ATTRIBUTION/holdouts')
PYTHON=Path('D:/he_m3_bvh032_private_654c1f69/venv/Scripts/python.exe')
BASE=Path('D:/HumanEye/runs/M6-041-KERNEL-HOOK')
SOURCE=Path('D:/he_m1_m2_source_region_scoped_measurement_001/slots/YB/initial_capture/TERMINAL_SOURCE.json')
FROZEN=VER/'m6_same_frame_scoped_batch_034/private/inputs/FROZEN.json'
HIGH=Path('D:/HumanEye/runs/M6-042-ENTRY-WARM-REGION/replay/capture_01/CAPTURE.json')
CANDIDATE=Path('D:/HumanEye/runs/M6-043-R3-REGION-ATTRIBUTION/candidate/PINS.json')


def need(ok,reason):
    if not ok:raise ValueError(reason)


def read(p):return json.loads(Path(p).read_bytes())


def dump(p,v):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('x',encoding='utf8',newline='\n') as f:json.dump(v,f,ensure_ascii=False,allow_nan=False,indent=2);f.write('\n')


def pin(p):
    p=Path(p).resolve(strict=True);b=p.read_bytes()
    return {'path':str(p),'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}


def verify(ref):need(pin(ref['path'])==ref,'source_identity_changed:'+ref['path'])


def installation(arm):
    if arm in ('A','B'):
        tag='032' if arm=='A' else 'r3';p=read(BASE/'install/PINS.json')
        binding=p['binding'][tag];verify(binding);b=read(binding['path'])
        site=Path(b['site_packages']);manifest=b['source_files'];identity=b['identity'];pins=pin(BASE/'install/PINS.json')
    else:
        p=read(CANDIDATE);need(pin(CANDIDATE)['sha256']=='47490e5b23b8d1317a182651b41411a5249c9e7e9f6a9addf9b3dab729b5c091','candidate_pins')
        binding=p['binding'];verify(binding);b=read(binding['path'])
        site=Path(p['site']);manifest=p['source_manifest'];identity=p['identity'];pins=pin(CANDIDATE)
    need(len(manifest)==143,'source_count')
    for row in manifest:need(pin(site/row['path'])['sha256']==row['sha256'],'installed_source')
    return {'arm':arm,'site':str(site),'identity':identity,'binding':binding,'pins':pins,'source_count':143}
