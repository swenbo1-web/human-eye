"""Freeze one future mixed input using geometry only; no product or Blender."""
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import struct

SOURCE = Path('D:/he_m4_target_001/qualification/A_peripheral_02/CAPTURE_01.json')
SOURCE_SHA = '6bf15a59a63a9704d13485e55bf72a915baaf97099ef8717a8f15398c14c029a'
OUT = Path(__file__).parent
raw = SOURCE.read_bytes()
assert hashlib.sha256(raw).hexdigest() == SOURCE_SHA
capture = json.loads(raw)
objects = []
for mesh in capture['meshes']:
    vertices = [[F(v) for v in p] for p in mesh['vertices']]
    assert all(p[2] <= 1 for p in vertices)
    # Every frozen world coordinate can be directly represented by Blender's
    # local binary32 mesh storage with an identity object matrix.
    assert all(F(struct.unpack('<f', struct.pack('<f', float(v)))[0]) == v
               for p in vertices for v in p)
    objects.append({'name':mesh['name'], 'world_vertices_m':vertices,
                    'triangles':mesh['faces'], 'reference_object_id':mesh['object_id']})
target = next(o for o in objects if o['name'] == 'M4_Far_00')
assert len(objects) == 14 and len(target['world_vertices_m']) == 289
assert len(target['triangles']) == 512
assert all(p[0] == 1 and 0 <= p[1] <= 1 and 0 <= p[2] <= 1 for p in target['world_vertices_m'])
target['world_vertices_m'].extend([[F(v) for v in p] for p in [(1,0,2),(2,0,2),(2,1,2),(1,1,2)]])
target['triangles'] = target['triangles'] + [[289,290,291],[289,291,292]]
center = [F(3,2),F(1,2),F(1)]

def dot(a,b): return sum(x*y for x,y in zip(a,b))
def cross(a,b): return [a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]]
def relative(points): return [[v-c for v,c in zip(p,center)] for p in points]

far = next(o for o in objects if o['name'] == 'M4_Far_11')
near = next(o for o in objects if o['name'] == 'M4_Near')
d = near['world_vertices_m'][0][0]
assert d == F(8589935,2147483648)
proofs=[]
for name,direction in [('SCENE',(4,-4,3)),('TOP',(0,0,1)),('LEFT',(-1,0,1)),
                       ('RIGHT',(1,0,1)),('FRONT',(0,-1,1)),('BACK',(0,1,1))]:
    neg=[-v for v in direction]; seed=[0,1,0] if name=='TOP' else [0,0,1]
    right=cross(neg,seed); up=cross(right,neg)
    spans=[]; separations=[]
    for axis in (right,up):
        norm2=dot(axis,axis)
        projected=[dot(axis,p) for p in relative(target['world_vertices_m'])]
        spans.append(max(abs(x) for x in projected)**2/norm2)
        fproj=[dot(axis,p) for p in relative(far['world_vertices_m'])]
        lo,hi=min(fproj),max(fproj)
        nearest=lo if lo>0 else (-hi if hi<0 else F(0))
        separations.append({'axis_raw':axis,'axis_norm_squared':norm2,'far_raw_range':[lo,hi],
                            'nearest_axis_distance_squared':nearest**2/norm2})
    half_span_squared=F(121,100)*max(spans)
    valid=[r for r in separations if r['nearest_axis_distance_squared']>half_span_squared]
    assert valid,name
    proofs.append({'view':name,'target_half_span_squared':half_span_squared,'strict_separating_axis':valid[0]})

geometry={'schema':'m4-target-acquisition-002-world-geometry-v1','source_capture':str(SOURCE),
          'source_capture_sha256':SOURCE_SHA,'target_name':'M4_Far_00','objects':objects,
          'construction':'Use these exact world coordinates as local vertices, identity object matrices, scale_length=1; preserve names and face order. Do not add old object translations again.',
          'control':'Target-only uses the exact M4_Far_00 record, with all other objects omitted.',
          'old_case':'Original 001 unchanged; this is a new synthetic mixed case, not a recovered 001 success.'}
data=(json.dumps(geometry,indent=2,default=str)+'\n').encode('utf8')
(OUT/'FROZEN_GEOMETRY.json').write_bytes(data)
proof={'schema':'independent-analytic-qualification-v1','geometry_sha256':hashlib.sha256(data).hexdigest(),
       'counts':{'objects':14,'vertices':sum(len(o['world_vertices_m']) for o in objects),
                 'triangles':sum(len(o['triangles']) for o in objects),'target_vertices':293,'target_triangles':514},
       'top':{'normal':[0,0,1],'area':1,'z':2,'all_old_z_max':1,'center':center,
              'half_span':F(11,20),'minimum_screen_margin_m':F(1,20),
              'visibility_argument':'All old geometry is below z=2; along +Z no positive-distance intersection.'},
       'vertical_left':{'near_x':d,'strict_occlusion_area_m2':d*d/2,
                        'new_top_does_not_remove_old_blocker':'Any positive LEFT ray distance from x=1 has x<1, outside added top x>=1.'},
       'far11_six_view_xy_exclusion':proofs,'actual_matrix_host_pixel_qualification':'not_run',
       'new_product_Blender_raster_model_calls':0}
(OUT/'ANALYTICAL_QUALIFICATION.json').write_text(json.dumps(proof,indent=2,default=str)+'\n',encoding='utf8')
print(json.dumps({'geometry_sha256':proof['geometry_sha256'],'counts':proof['counts'],'six_exact_exclusion_checks':len(proofs)}))
