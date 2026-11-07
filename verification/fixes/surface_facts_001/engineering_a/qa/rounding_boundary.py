"""Retain the real tiny-surface rounding pair and its independent half-ULP bound."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import numpy as np

ROOT=Path(__file__).resolve().parents[5]
sys.path.insert(0,str(ROOT))
from human_eye_plugin.surface_proximity import measure_surface_proximity

parser=argparse.ArgumentParser()
parser.add_argument('--phase',choices=('before','after'),required=True)
args=parser.parse_args()
s=2.0**-1074
H=2**300
b=SimpleNamespace(vertices=np.array([[s,s*H,s*H],[2*s,s*H,s*H],[s,s*H,2*s*H]]),faces=np.array([[0,1,2]]))
cases=[]
for sign in (1,-1):
    a=SimpleNamespace(vertices=np.array([[0,sign*s,0],[0,sign*s,4*s*H],[s,2*s*H,0]]),faces=np.array([[0,1,2]]))
    result=measure_surface_proximity(a,b,lambda stage:None)
    discriminant=4*H*H-((2*H-sign)**2+1)
    cases.append(dict(sign=sign,independent_half_ulp_discriminant=discriminant,
        expected='minimum_positive_float' if discriminant>0 else 'positive_below_rounding_resolution',
        result=result))
module=ROOT/'human_eye_plugin/surface_proximity.py'
record=dict(phase=args.phase,module_sha256=hashlib.sha256(module.read_bytes()).hexdigest(),
    independent_formula='distance = s*H / sqrt((2H-sign)^2+1); compare 4H^2 with denominator',
    cases=cases)
path=Path(__file__).resolve().parents[1]/('ROUNDING_'+args.phase.upper()+'.json')
path.write_text(json.dumps(record,indent=2),encoding='utf8')
if args.phase=='after':
    assert cases[0]['result']['measurement_valid'] and cases[0]['result']['distance_m']==s
    assert not cases[1]['result']['measurement_valid']
    assert cases[1]['result']['reason']=='surface_distance_below_float_resolution'
print(json.dumps(dict(phase=args.phase,values=[dict(sign=c['sign'],valid=c['result']['measurement_valid'],
    distance_m=c['result']['distance_m'],reason=c['result'].get('reason')) for c in cases])))
