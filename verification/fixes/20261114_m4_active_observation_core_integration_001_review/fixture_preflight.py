"""Offline exact arithmetic for a future QA fixture; creates no scene/raster."""
from fractions import Fraction
from pathlib import Path
from math import lcm
import hashlib
import json
import struct

p=Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_active_observation_core_integration_001/inputs/scene_grid16_permuted_alternating.json')
raw=p.read_bytes();scene=json.loads(raw)
coordinates=[Fraction(x) for o in scene['objects'] for pt in o['vertices'] for x in pt]
scale=Fraction(375,256)
exact=all(Fraction(struct.unpack('f',struct.pack('f',float(x*scale)))[0])==x*scale for x in coordinates)
result={'purpose':'Predeclare a separate binary32-exact host QA fixture, before candidate execution. Not runtime normalization.',
 'input':str(p),'input_sha256':hashlib.sha256(raw).hexdigest(),'coordinate_count':len(coordinates),
 'unique_coordinates':len(set(coordinates)),'non_dyadic_unique_coordinates':sum(x.denominator&(x.denominator-1)!=0 for x in set(coordinates)),
 'denominator_lcm':lcm(*(x.denominator for x in coordinates)), 'uniform_exact_scale':str(scale),
 'float32_roundtrip_all_exact':exact,'maximum_scaled_numerator_bits':max(abs((x*scale).numerator).bit_length() for x in coordinates),
 'passed':exact,'product_or_Blender_calls':0,
 'plan_review_correction':'Initial draft incorrectly described old rational fixture as binary-exact. Two static reviewers identified the issue before plan freeze. The final plan predeclares this separate uniformly scaled fixture and compares the direct core to the same actual capture.'}
with Path(__file__).with_name('FIXTURE_PREFLIGHT.json').open('x',encoding='utf8') as f:json.dump(result,f,ensure_ascii=False,indent=2)
print(json.dumps(result,ensure_ascii=False))
