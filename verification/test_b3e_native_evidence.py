"""Public numerical/coherence doubles for the shared-capture native pilot arm.

These are not independent production source-admission records. Actual frozen
CLI captures are prepared separately after the common acquisition is verified.
"""
import copy,hashlib,json,math,unittest
from unittest.mock import patch
import numpy as np
from verification.model_trial import b3e_native as n
from verification import deformation_anchor_oracle as a
from verification.test_small_skin_source import packet as authored

I=np.eye(4).tolist()
def rehash(packet):
 packet['audit']['before_sha256']=packet['audit']['after_sha256']=a.digest(packet['inputs'])
 packet['source_sha256']=a.digest({k:v for k,v in packet.items() if k not in ('source_sha256','capture_id')})
 return packet

def directory(packet):
 g=a.expected_geometry(packet);i=packet['identity'];raw=packet['inputs'];anchors=[dict(row,state='available' if row['reason'] is None else 'unavailable') for row in g['anchors']]
 c=dict(schema='surface-deformation-anchor-catalog-v1',source_ref=dict(scene_sha256=i['scene_sha256'],rig_object_id=a.stable_object(raw['rig']['name']),mesh_object_id=a.stable_object(raw['mesh']['name']),frame=copy.deepcopy(raw['frame'])),
  operator_pins={key:i[key] for key in a.PIN_KEYS},coordinate_model=dict(coordinate_space='current_world_m',position_model='nearest_binary64_from_exact_binary_affine',interval_model='outward_binary64_interval_for_published_numeric_inputs_not_physical_error'),graph=g['graph'],anchors=anchors,
  bounds=dict(kind='referenced_current_triangle_hull_aabb',bounds_world_m=g['bounds_world_m'],vertices_total=g['vertices_total'],surface_vertices_total=g['surface_vertices_total'],loose_vertices_excluded=g['loose_vertices_excluded'],triangles_total=g['triangles_total']),
  completeness=dict(bones_total=len(raw['rig']['bones']),anchors_total=len(anchors),anchors_available=sum(row['reason'] is None for row in anchors),anchors_unavailable=sum(row['reason'] is not None for row in anchors),anchors_omitted=0,graph_complete=True,anchors_complete=True),
  scope=dict(anchor_semantics='native_evaluated_bone_endpoints_only',bounds_semantics='referenced_current_triangle_hulls_not_volume',not_inferred=['anatomical_semantics','surface_location','damage','visibility','repair','editing_authority']),
  source_sha256=packet['source_sha256'],live_capture=dict(source_sha256=packet['source_sha256'],document_epoch=i['document_epoch'],process_id=i['process_id']),execution_authority=False,geometry_setters=0,original_file_saved=False)
 c['catalog_sha256']=a.digest({key:c[key] for key in a.STABLE_KEYS});return c

def fixture(change=None,half=(2.,2.,2.)):
 p=authored()
 if change:change(p)
 rehash(p);c=directory(p)
 policy=dict(schema='surface-deformation-context-policy-v1',source_ref=copy.deepcopy(c['source_ref']),catalog_sha256=c['catalog_sha256'],anchor_id=c['anchors'][0]['anchor_id'],
  required_core_half_extents_m=list(half),primary_half_extents_m=[3.,3.,3.],candidate_half_extents_m=[list(half)],max_surplus_members=0,min_saved_bytes=256,planning_budget_ms=250)
 return p,c,policy


class NativeEvidenceTests(unittest.TestCase):
 def call(self,values):return n.prepare_native(*values)
 def refused(self,values,reason):
  with self.assertRaisesRegex(n.NativeEvidenceError,'^b3e_native_'+reason+'$'):self.call(values)

 def test_known_local_stretches_counts_and_area(self):
  def stretch(p):p['evaluated']['vertices']=[[0.,0.,0.],[2.,0.,0.],[0.,.5,0.]]
  public,truth=self.call(fixture(stretch));f=public['facts']
  self.assertEqual(f['core_status'],'observed');self.assertEqual(f['core_triangle_count'],1);self.assertEqual(f['core_states'],dict(measured=1,collapsed=0,unknown=0))
  self.assertEqual(f['core_unknown_reasons'],{});self.assertEqual(f['core_extrema'],dict(max_principal_stretch=2.,min_principal_stretch=.5,min_area_ratio=1.,max_area_ratio=1.))
  self.assertEqual(truth['core_triangle_indices'],[0]);self.assertEqual(truth['facts'],f)

 def test_empty_has_no_invented_extrema(self):
  def shift(p):
   p['inputs']['mesh']['vertices']=[[2.,0.,0.],[3.,0.,0.],[2.,1.,0.]];p['evaluated']['vertices']=copy.deepcopy(p['inputs']['mesh']['vertices'])
  public,truth=self.call(fixture(shift,half=(.1,.1,.1)));f=public['facts']
  self.assertEqual(f['core_status'],'empty');self.assertEqual(f['core_triangle_count'],0);self.assertEqual(f['core_extrema'],dict.fromkeys(n.METRICS))
  self.assertEqual(f['core_states'],dict(measured=0,collapsed=0,unknown=0));self.assertEqual(truth['core_triangle_indices'],[])

 def test_all_unknown_preserves_reason_and_null_extrema(self):
  public,truth=self.call(fixture(lambda p:p['inputs']['mesh'].update(weights=[[],[],[]])))
  f=public['facts'];self.assertEqual(f['core_status'],'partial');self.assertEqual(f['core_states'],dict(measured=0,collapsed=0,unknown=1))
  self.assertEqual(f['core_unknown_reasons'],{'unweighted_vertex_source':1});self.assertEqual(f['core_extrema'],dict.fromkeys(n.METRICS));self.assertIsNone(truth['core_facts'][0]['principal_stretches'])

 def test_collapsed_member_is_not_empty_and_zero_is_a_measured_fact(self):
  public,truth=self.call(fixture(lambda p:p['evaluated'].update(vertices=[[0.,0.,0.]]*3)))
  f=public['facts'];self.assertEqual(f['core_status'],'observed');self.assertEqual(f['core_states'],dict(measured=0,collapsed=1,unknown=0))
  self.assertEqual(f['core_extrema'],dict.fromkeys(n.METRICS,0.));self.assertEqual(truth['core_facts'][0]['reason'],'current_zero_area')

 def test_original_zero_area_stays_unknown(self):
  def zero(p):p['inputs']['mesh']['vertices']=[[0.,0.,0.],[1.,0.,0.],[2.,0.,0.]];p['evaluated']['vertices']=copy.deepcopy(p['inputs']['mesh']['vertices'])
  public,truth=self.call(fixture(zero));self.assertEqual(public['facts']['core_unknown_reasons'],{'original_zero_area':1});self.assertEqual(public['facts']['core_extrema'],dict.fromkeys(n.METRICS))

 def test_world_rigid_transform_and_units_keep_shape_metrics(self):
  def world(p):
   w=[[0.,-1.,0.,10.],[1.,0.,0.,3.],[0.,0.,1.,0.],[0.,0.,0.,1.]]
   p['evaluated']['mesh_matrix_world']=copy.deepcopy(w);p['evaluated']['rig_matrix_world']=copy.deepcopy(w);p['inputs']['unit_scale_m']=.001
  public,truth=self.call(fixture(world,half=(.01,.01,.01)))
  np.testing.assert_allclose(list(public['facts']['core_extrema'].values()),[1.,1.,1.,1.],atol=1e-15,rtol=0.)
  self.assertEqual(public['facts']['core_triangle_count'],1);self.assertEqual(public['core_region']['coordinate_space'],'current_world_m')

 def test_point_contact_retains_whole_face_without_area_claim(self):
  def touch(p):p['inputs']['mesh']['vertices']=[[.25,.25,.25],[1.,.25,.25],[.25,1.,.25]];p['evaluated']['vertices']=copy.deepcopy(p['inputs']['mesh']['vertices'])
  public,truth=self.call(fixture(touch,half=(.25,.25,.25)))
  self.assertEqual(public['facts']['core_triangle_count'],1);self.assertEqual(public['scope']['contact_extent'],'not_checked');self.assertEqual(public['scope']['metric_scope'],'whole_original_triangles_not_clipped_integrals')

 def test_source_digest_and_audit_changes_are_not_trusted(self):
  p,c,s=fixture();p['evaluated']['vertices'][0][0]=.1;self.refused((p,c,s),'source_digest')
  p,c,s=fixture();p['audit']['independent_after_sha256']='f'*64;self.refused((p,c,s),'capture_audit')
  p,c,s=fixture();p['inputs']['frame']['number']=7;self.refused((p,c,s),'capture_audit')

 def test_rehashed_wrong_scene_frame_or_profile_still_refuses_catalog_binding(self):
  for change in (lambda p:p['identity'].update(scene_sha256='f'*64),lambda p:p['identity'].update(profile_sha256='f'*64),lambda p:p['inputs']['frame'].update(number=9)):
   p,c,s=fixture();change(p);rehash(p);self.refused((p,c,s),'catalog_binding')

 def test_policy_target_catalog_and_half_mutations_refused(self):
  p,c,s=fixture();s['source_ref']['frame']['number']=7;self.refused((p,c,s),'policy_source')
  p,c,s=fixture();s['catalog_sha256']='f'*64;self.refused((p,c,s),'policy_source')
  p,c,s=fixture();s['required_core_half_extents_m'][0]=True;self.refused((p,c,s),'policy_halves')
  p,c,s=fixture();s['candidate_half_extents_m'][0]=[4.]*3;self.refused((p,c,s),'policy_candidates')
  p,c,s=fixture();s['anchor_id']='bone-anchor:'+'f'*64;self.refused((p,c,s),'anchor_unavailable')

 def test_bound_shapes_and_tails_are_checked_before_independent_math(self):
  for change,reason in ((lambda p:p['evaluated']['vertices'].append([0,0,0]),'vertices'),(lambda p:p['inputs']['mesh']['triangles'][0].__setitem__(2,True),'triangles'),
      (lambda p:p['evaluated'].update(original_links_verified=False),'evaluated_shape'),(lambda p:p['inputs']['mesh']['weights'][2].__setitem__(0,[0,float('nan')]),'weights'),
      (lambda p:p.update(qualified=True),'packet_schema')):
   p,c,s=fixture();change(p);self.refused((p,c,s),reason)

 def test_only_readonly_capture_metadata_is_accepted(self):
  for change in (dict(execution_authority=True),dict(geometry_setters=1),dict(geometry_setters=False),dict(original_file_saved=True)):
   p,c,s=fixture();c.update(change);self.refused((p,c,s),'readonly_capture_provenance')

 def test_stable_catalog_is_explicitly_revalidated_not_a_borrowed_live_epoch(self):
  p,c,s=fixture();original=copy.deepcopy(c['live_capture']);p['identity']['document_epoch']='c'*32;p['identity']['process_id']=5678;p['capture_id']='d'*32;rehash(p)
  public,truth=self.call((p,c,s))
  self.assertEqual(public['source_observation_sha256'],p['source_sha256']);self.assertNotEqual(public['source_observation_sha256'],c['source_sha256'])
  self.assertEqual(truth['provenance']['catalog_original_capture'],original);self.assertTrue(truth['provenance']['live_observation_window_not_granted'])

 def test_private_complete_truth_is_not_added_to_public_packet(self):
  inputs=fixture();original=copy.deepcopy(inputs);public,truth=self.call(inputs)
  self.assertEqual(inputs,original);self.assertNotIn('core_triangle_indices',public);self.assertNotIn('core_facts',public);self.assertNotIn('vertices',json.dumps(public))
  self.assertEqual(set(truth['facts']),{'core_status','core_triangle_count','core_states','core_unknown_reasons','core_extrema'})
  self.assertFalse(public['execution_authority']);self.assertTrue(truth['provenance']['external_acquisition_receipt_required'])
  self.assertTrue(truth['provenance']['raw_operator_policy_file_sha256_required_from_caller']);self.assertEqual(public['policy_digest_model'],'canonical_utf8_json_not_operator_file_bytes')

 def test_runtime_and_bytes_measure_whole_helper_not_capture_or_task(self):
  public,truth=self.call(fixture());m=truth['measurement'];raw=n.encode(public)
  self.assertEqual(m['public_report_canonical_utf8_bytes'],len(raw));self.assertEqual(m['public_report_canonical_utf8_sha256'],hashlib.sha256(raw).hexdigest())
  self.assertGreater(m['full_prepare_elapsed_ns'],0);self.assertIsNone(m['common_capture_elapsed_ns']);self.assertIn('excludes',m['basis'])

 def test_no_production_geometry_selector_or_metric_is_used(self):
  with patch('human_eye_plugin.surface_deformation._geometry_rows',side_effect=AssertionError('production B2 called')),patch('human_eye_plugin.deformation_region.select',side_effect=AssertionError('production clipping called')),patch('human_eye_plugin.deformation_anchors.catalog',side_effect=AssertionError('production catalog called')):
   public,truth=self.call(fixture());self.assertEqual(public['facts']['core_triangle_count'],1)

if __name__=='__main__':unittest.main()
