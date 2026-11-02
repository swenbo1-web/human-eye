"""Represented-input exact SAT oracle and full dependent action boundaries."""
import copy,math,unittest
from fractions import Fraction as Q
from unittest.mock import patch
import numpy as np
from verification.test_concave_geometry import box,changed
from verification.test_host_runtime import MutableHost
from human_eye_module1_operators import MeshEntity3D
from human_eye_module1_operators import submodule_1_4_spatial_sniffer as sat
from human_eye_plugin.geometry_safety import measure_pair_geometry
from human_eye_plugin.host_runtime import GuardedHostRuntime
from human_eye_plugin.task_verification import evaluate_spatial_goal


def fixture(shift=1e8,angle=.8265135001991609,overlap=2.015725073432108e-8):
 c,s=math.cos(angle),math.sin(angle);rotation=np.array([[c,-s,0],[s,c,0],[0,0,1.]])
 a=box(size=(1,1,1),identity='part');b=box(size=(1,1,1),identity='base')
 return changed(a,vertices=a.vertices@rotation.T+[shift,shift,0]),changed(b,vertices=b.vertices@rotation.T+[shift,shift,0]+rotation[:,0]*(1-overlap))


def exact_sat(a,b,tolerance=0):
 # Full actual-float triangle normals and all edge cross products. Production
 # axes/projections are deliberately not read or used as numerical answers.
 points=[[tuple(Q(float(x)) for x in p) for p in m.vertices] for m in (a,b)]
 def sub(a,b):return tuple(x-y for x,y in zip(a,b))
 def cross(a,b):return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])
 def dot(a,b):return sum(x*y for x,y in zip(a,b))
 normals=[];edges=[]
 for mesh,pts in zip((a,b),points):
  edge=[]
  for face in mesh.faces:
   p,q,r=[pts[i] for i in face];normals.append(cross(sub(q,p),sub(r,p)))
   edge.extend((sub(q,p),sub(r,q),sub(p,r)))
  edges.append(edge)
 axes={}
 for axis in normals+[cross(e,f) for e in edges[0] for f in edges[1]]:
  first=next((x for x in axis if x),None)
  if first is not None:axes[tuple(x/first for x in axis)]=None
 depths=[];qthreshold=Q(float(tolerance))
 for axis in axes:
  left=[dot(p,axis) for p in points[0]];right=[dot(p,axis) for p in points[1]]
  overlap=min(max(left),max(right))-max(min(left),min(right));normsq=dot(axis,axis)
  if overlap<=0 or overlap*overlap<=qthreshold*qthreshold*normsq:return False,0.
  depths.append(float(overlap)/math.sqrt(float(normsq)))
 return True,min(depths)


def scene(a,b):return dict(revision='r1',unit='m',coordinate_frame='world',source='test_host',meshes=[b.to_dict(),a.to_dict()])


def prepare(a,b):
 host=MutableHost();host.scene=scene(a,b);runtime=GuardedHostRuntime(host,quad_size=64)
 runtime.before_model(session_id='s',messages=[],task_instruction='Measure current part clearance.',focal_id='part',reference_id='base')
 return host,runtime


class LocalSatSafetyTests(unittest.TestCase):
 def test_reported_adversary_is_independently_overlapping_above_original_tolerance(self):
  a,b=fixture();truth,depth=exact_sat(a,b,1e-9);self.assertTrue(truth);self.assertGreater(depth,1e-9)
  self.assertAlmostEqual(depth,1.09609058278678e-8,delta=1e-20)
  for clearance in (False,True):
   result=measure_pair_geometry(a,b,need_clearance=clearance)
   self.assertFalse(result['measurement_valid'] and result['is_penetrating'] is False,result)
   if result['measurement_valid']:self.assertTrue(result['is_penetrating'])
 def test_ordinary_and_dual_share_positive_classification(self):
  a,b=fixture();ordinary=sat._certified_solid_collision(a,b,1e-9);dual=sat._single_convex_collision_and_zero(a,b,1e-9)
  self.assertTrue(ordinary[0]);self.assertEqual(ordinary[:2],dual[0][:2]);self.assertTrue(dual[1][0])
 def test_shift_rotation_and_threshold_matrix_matches_actual_represented_geometry(self):
  for shift in (0.,1e6,1e8,1e12):
   for angle in (0.,.37,.8265135001991609):
    for overlap in (-1e-4,0.,5e-10,2e-9,2e-8,1e-4):
     with self.subTest(shift=shift,angle=angle,overlap=overlap):
      a,b=fixture(shift,angle,overlap);truth,_=exact_sat(a,b,1e-9);result=measure_pair_geometry(a,b)
      if result['measurement_valid']:self.assertEqual(result['is_penetrating'],truth,result)
      else:self.assertIsNone(result['is_penetrating'])
 def test_axis_box_tolerance_two_sides_and_exact_touch(self):
  a=box(size=(1,1,1),identity='part')
  for overlap in (-2e-9,0.,.5e-9,1e-9,2e-9):
   b=box(center=(1-overlap,0,0),size=(1,1,1),identity='base')
   truth,_=exact_sat(a,b,1e-9);ordinary=sat._certified_solid_collision(a,b,1e-9);dual=sat._single_convex_collision_and_zero(a,b,1e-9)
   self.assertEqual(ordinary[0],truth);self.assertEqual(dual[0][0],truth);self.assertEqual(dual[1][0],exact_sat(a,b,0)[0])
 def test_zero_goal_cannot_pass_the_actual_positive_overlap(self):
  a,b=fixture();result=evaluate_spatial_goal(scene(a,b),dict(focal_id='part',reference_id='base',target_clearance_m=0,clearance_tolerance_m=1e-9))
  self.assertFalse(result['task_succeeded'],result)
 def test_preview_and_precommit_block_without_setter(self):
  a,b=fixture();host,runtime=prepare(a.translated([0,0,1.1]),b)
  preview=runtime.preview_action(session_id='s',action=dict(translation=[0,0,-.2]));self.assertFalse(preview['allow_action'],preview)
  result=runtime.execute_action(session_id='s',action=dict(translation=[0,0,-.2]));self.assertFalse(result['verified'],result);self.assertEqual(host.calls,0)
 def test_successful_safe_endpoint_still_works(self):
  a,b=fixture();host,runtime=prepare(a.translated([0,0,1.1]),b)
  result=runtime.execute_action(session_id='s',action=dict(translation=[0,0,.2]));self.assertTrue(result['verified'],result);self.assertEqual(host.calls,1)
 def test_unexpected_readback_penetration_keeps_real_setter_and_quarantines(self):
  a,b=fixture();host,runtime=prepare(a.translated([0,0,1.1]),b);original=host.apply_transform
  def corrupt(action,**kw):
   result=original(action,**kw);host.scene['meshes'][1]=a.translated([0,0,.9]).to_dict();result['scene']=copy.deepcopy(host.scene);return result
  host.apply_transform=corrupt
  result=runtime.execute_action(session_id='s',action=dict(translation=[0,0,.2]));self.assertFalse(result['verified'],result);self.assertEqual(host.calls,1);self.assertTrue(runtime.status['quarantined']);self.assertTrue(result['host_call_completed']);self.assertIsNone(result['executed'])
 def test_exhausted_exact_numeric_resolution_is_unknown_not_orthogonal_safe(self):
  a=box(size=(1,1,1),identity='part');b=box(center=(1,0,0),size=(1,1,1),identity='base')
  for clearance in (False,True):
   with patch.object(sat,'_MAX_EXACT_SAT_DOTS',0):result=measure_pair_geometry(a,b,collision_tolerance_m=0,need_clearance=clearance)
   self.assertFalse(result['measurement_valid']);self.assertIsNone(result['is_penetrating']);self.assertEqual(result['reason'],'sat_projection_precision_unresolved')
 def test_numeric_unknown_blocks_goal_and_action(self):
  a=box(size=(1,1,1),identity='part');b=box(center=(1-1e-9,0,0),size=(1,1,1),identity='base')
  host,runtime=prepare(a.translated([0,0,1.1]),b)
  with patch.object(sat,'_MAX_EXACT_SAT_DOTS',0):
   result=evaluate_spatial_goal(scene(a,b),dict(focal_id='part',reference_id='base',target_clearance_m=0,clearance_tolerance_m=1e-9));self.assertFalse(result['task_succeeded']);self.assertFalse(result['measurement_valid'])
   preview=runtime.preview_action(session_id='s',action=dict(translation=[0,0,-.2]));self.assertFalse(preview['allow_action'])
   execute=runtime.execute_action(session_id='s',action=dict(translation=[0,0,-.2]));self.assertFalse(execute['verified']);self.assertEqual(host.calls,0)
 def test_recomputed_mtv_ranking_resolves_all_high_error_axes(self):
  import itertools
  rng=np.random.default_rng(4719);bits=np.array(list(itertools.product([-.5,.5],[-.5,.5],[-1.,1.])))
  for _ in range(29):
   axes=np.linalg.qr(rng.normal(size=(3,3)))[0].T;length=10**rng.uniform(8,13)
   va=(bits*[1,1,length])@axes
   offset=axes[0]*(.7+rng.uniform(-1e-5,1e-5))+axes[1]*(.7+rng.uniform(-1e-5,1e-5))
   vb=va+offset
  overlaps,positive,negative=sat._local_sat_projection(va,vb,axes,(0.,1e-9))
  depths=[]
  for axis in axes:
   qaxis=[Q(float(v)) for v in axis]
   aa=[sum(Q(float(point[k]))*qaxis[k] for k in range(3)) for point in va]
   bb=[sum(Q(float(point[k]))*qaxis[k] for k in range(3)) for point in vb]
   depths.append(float(min(abs(max(bb)-min(aa)),abs(min(bb)-max(aa)))))
  depth,vector=sat._sat_metric(va,vb,axes,positive,negative)
  self.assertAlmostEqual(depth,min(depths),delta=1e-9)
  self.assertAlmostEqual(depth,.30004877353742665,delta=1e-15)
 def test_unrepresentable_metre_vector_metric_is_unknown(self):
  a=box(size=(1e8,1e8,1e8),identity='part');b=box(center=(1e7,0,0),size=(1e8,1e8,1e8),identity='base')
  result=measure_pair_geometry(a,b,need_clearance=True)
  self.assertFalse(result['measurement_valid']);self.assertEqual(result['reason'],'sat_projection_precision_unresolved');self.assertIsNone(result['signed_clearance_m'])
 def test_component_path_uses_same_local_origin(self):
  a,b=fixture();shell_a=sat._convex_shells(a)[0];shell_b=sat._convex_shells(b)[0]
  self.assertTrue(sat._convex_sat_parts(shell_a,shell_b,1e-9)[0])
  with patch.object(sat,'_MAX_EXACT_SAT_DOTS',0):
   touch=box(center=(1,0,0),size=(1,1,1));base=box(size=(1,1,1))
   with self.assertRaisesRegex(ValueError,'sat_projection_precision_unresolved'):sat._convex_sat_parts(sat._convex_shells(touch)[0],sat._convex_shells(base)[0],0)

if __name__=='__main__':unittest.main()
