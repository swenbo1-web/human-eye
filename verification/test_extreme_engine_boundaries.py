"""Bounded independent-oracle boundary tests; no host/model/performance calls."""
from __future__ import annotations

import argparse
import copy
import hashlib
import io
import json
import math
from pathlib import Path
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image

from human_eye_module1_operators import MeshEntity3D
from human_eye_module1_operators.submodule_1_4_spatial_sniffer import SpatialAnomalySniffer
from human_eye_plugin.auto_router import HumanEyeAutoRouter, _validated_scene, _vector
from human_eye_plugin.contact_section import append_contact_section
from human_eye_plugin.geometry_safety import (
    COLLISION_TOLERANCE_M, measure_pair_geometry, solid_support_status, work_budget_status,
)
from human_eye_plugin.rigid_frame import rigid_frame_status
from human_eye_plugin.runtime_identity import runtime_identity
from human_eye_plugin.task_verification import evaluate_spatial_goal


OBSERVATIONS = []
SIGNS = np.array([[-1,-1,-1],[1,-1,-1],[1,1,-1],[-1,1,-1],
                  [-1,-1,1],[1,-1,1],[1,1,1],[-1,1,1]], dtype=float)
FACES = [[0,2,1],[0,3,2],[4,5,6],[4,6,7],[0,1,5],[0,5,4],
         [2,3,7],[2,7,6],[1,2,6],[1,6,5],[3,0,4],[3,4,7]]


def box(identity, center=(0,0,0), size=(.2,.2,.2)):
    return dict(object_id=identity, mark_label='#'+identity, name=identity,
        vertices=(SIGNS*np.array(size)/2+np.array(center)).tolist(), faces=copy.deepcopy(FACES),
        color_rgb=[70,140,210], is_focal_target=identity=='part', local_axes=np.eye(3).tolist(),
        pivot_world=list(center), axes_source='host', axes_confidence='explicit',
        axes_reason='independent_explicit_fixture_frame')


def pair(gap=.002):
    return [box('base', (0,0,-.1)), box('part', (0,0,.1+gap))]


def scene(meshes=None):
    return dict(revision='boundary-r1', unit='m', coordinate_frame='world',
                source='bounded_independent_boundary_fixture', meshes=pair() if meshes is None else meshes)


def entity(raw):
    return MeshEntity3D.from_dict(raw)


def rotation(euler):
    x,y,z=np.radians(euler); cx,sx,cy,sy,cz,sz=math.cos(x),math.sin(x),math.cos(y),math.sin(y),math.cos(z),math.sin(z)
    return np.array([[cz,-sz,0.],[sz,cz,0.],[0.,0.,1.]]) @ np.array([[cy,0.,sy],[0.,1.,0.],[-sy,0.,cy]]) @ np.array([[1.,0.,0.],[0.,cx,-sx],[0.,sx,cx]])


def transformed(raw, matrix, offset, scale):
    result=copy.deepcopy(raw)
    result['vertices']=(np.asarray(raw['vertices'])*scale @ matrix.T+offset).tolist()
    result['local_axes']=(np.asarray(raw['local_axes']) @ matrix.T).tolist()
    result['pivot_world']=(np.asarray(raw['pivot_world'])*scale @ matrix.T+offset).tolist()
    return result


def prism(identity, sides, center_z):
    vertices=[[.04*math.cos(i*math.tau/sides), .04*math.sin(i*math.tau/sides), z]
              for z in (center_z-.01,center_z+.01) for i in range(sides)]
    faces=[(0,i+1,i) for i in range(1,sides-1)]
    faces += [(sides,sides+i,sides+i+1) for i in range(1,sides-1)]
    for i in range(sides):
        j=(i+1)%sides
        faces.extend(((i,j,j+sides),(i,j+sides,i+sides)))
    raw=box(identity, (0,0,center_z));raw.update(vertices=vertices,faces=[list(f) for f in faces])
    return raw


def concave():
    outline=[(0,0),(.2,0),(.2,.08),(.08,.08),(.08,.2),(0,.2)]
    cap=[(0,1,3),(1,2,3),(0,3,5),(3,4,5)]
    faces=[(a,c,b) for a,b,c in cap]+[(a+6,b+6,c+6) for a,b,c in cap]
    for i in range(6):
        j=(i+1)%6;faces.extend(((i,j,j+6),(i,j+6,i+6)))
    raw=box('concave');raw.update(vertices=[[x,y,z] for z in (-.03,.03) for x,y in outline], faces=[list(f) for f in faces])
    # Keep this unsupported-shape boundary after world-axis concavity gains
    # exact support. The sheared closed L still cannot be snapped to that class.
    raw['vertices']=[[x+.125*z,y,z] for x,y,z in raw['vertices']]
    return raw


class CountOnly:
    """Arithmetic admission test only; never pass into geometry/NumPy."""
    def __init__(self, count): self.count=count
    def __len__(self): return self.count


def counted(identity, vertices, faces, edges=0):
    return dict(object_id=identity, vertices=CountOnly(vertices), faces=CountOnly(faces), edges=CountOnly(edges))


class ConversionReached(RuntimeError):
    pass


class AllocationGuardList(list):
    """Advertise a boundary without allocating its purported payload."""
    def __init__(self, count): super().__init__();self.count=count;self.converted=False
    def __len__(self): return self.count
    def __array__(self, dtype=None, copy=None):
        self.converted=True
        raise ConversionReached('At/below raw input-count allocation guard')


class BoundaryCase(unittest.TestCase):
    def record(self, label, result):
        OBSERVATIONS.append(dict(test=self.id(), label=label, result=copy.deepcopy(result)))

    def observe(self, raw):
        return HumanEyeAutoRouter(quad_size=64).handle_event(dict(event='before_model', session_id='boundary',
            scene=raw, task_kind='spatial_3d', task_instruction='Measure actual 3D mesh clearance.',
            focal_id='part', reference_id='base', include_image=False))


class StrictNumericBoundaryTests(BoundaryCase):
    def test_collision_tolerance_both_sides_and_exact_represented_boundary(self):
        self.assertEqual(COLLISION_TOLERANCE_M,1e-9)
        self.assertGreater(SpatialAnomalySniffer.FLUSH_TOLERANCE_M,50e-6)
        for requested in (-50e-6,-2e-9,-1e-9,-.5e-9,0.,.5e-9,2e-9,50e-6):
            with self.subTest(gap=requested):
                a,b=map(entity,pair(requested)); lo_a,hi_a=a.vertices.min(0),a.vertices.max(0);lo_b,hi_b=b.vertices.min(0),b.vertices.max(0)
                overlap=np.minimum(hi_a,hi_b)-np.maximum(lo_a,lo_b)
                actual=float(lo_b[2]-hi_a[2]); expected=bool(np.all(overlap>1e-9))
                result=measure_pair_geometry(a,b,need_clearance=True);self.record(str(requested),dict(actual_gap_m=actual,expected_penetrating=expected,measurement=result))
                self.assertTrue(result['measurement_valid'],result)
                self.assertEqual(result['is_penetrating'],expected)
                self.assertAlmostEqual(result['signed_clearance_m'],actual,delta=2e-12)

    def test_pair_swap_does_not_change_single_box_clearance(self):
        for gap in (.002,-50e-6,0.):
            with self.subTest(gap=gap):
                a,b=map(entity,pair(gap));left=measure_pair_geometry(a,b,need_clearance=True);right=measure_pair_geometry(b,a,need_clearance=True)
                self.record(str(gap),dict(left=left,right=right))
                self.assertTrue(left['measurement_valid'] and right['measurement_valid'])
                self.assertEqual(left['is_penetrating'],right['is_penetrating'])
                self.assertAlmostEqual(left['signed_clearance_m'],right['signed_clearance_m'],delta=2e-12)

    def test_supported_translation_rotation_and_scale_metamorphic_oracle(self):
        for scale in (.001,1.,1000.):
            for angles,offset in (((0,0,0),(0,0,0)),((17,-23,41),(12,-7,3)),((17,-23,41),(12000,-7000,3))):
                with self.subTest(scale=scale,angles=angles,offset=offset):
                    values=[entity(transformed(raw,rotation(angles),np.array(offset),scale)) for raw in pair()]
                    maximum=max(float(np.max(np.abs(v.vertices))) for v in values); tolerance=8*float(np.spacing(max(1.,maximum)))+1e-11*scale
                    result=measure_pair_geometry(*values,need_clearance=True);self.record(str((scale,angles,offset)),dict(expected_gap_m=.002*scale,tolerance_m=tolerance,measurement=result))
                    self.assertTrue(result['measurement_valid'],result)
                    self.assertFalse(result['is_penetrating'])
                    self.assertAlmostEqual(result['signed_clearance_m'],.002*scale,delta=tolerance)

    def test_collision_options_reject_bool_string_nonfinite_and_out_of_contract(self):
        a,b=map(entity,pair())
        for value in (True,'1e-9',-1e-12,1.00001e-8,float('nan'),float('inf')):
            with self.subTest(value=value),self.assertRaises(ValueError): measure_pair_geometry(a,b,collision_tolerance_m=value)
        for value in (0.,1e-8):
            result=measure_pair_geometry(a,b,collision_tolerance_m=value);self.assertTrue(result['measurement_valid'])

    def test_action_vectors_reject_python_and_numpy_bools_without_coercion(self):
        for value in (True,False,np.bool_(True),np.bool_(False),'1'):
            with self.subTest(value=str(value),type=type(value).__name__):
                with self.assertRaises(ValueError):_vector([value,0,0])
                self.record(type(value).__name__+':'+str(value),{'raw_action_scalar_refused':True})
        np.testing.assert_array_equal(_vector([np.int64(1),np.float64(2),0]),[1.,2.,0.])

    def test_subresolution_section_refuses_without_mutating_natural_canvas(self):
        canvas=Image.new('RGB',(128,128),(11,23,41));before=canvas.tobytes();gap=1e-14
        measured=dict(measurement_kind='exact',clearance_exact=True,measurement_valid=True,
            signed_clearance_m=gap,point_a_world=[0,0,gap],point_b_world=[0,0,0])
        with self.assertRaisesRegex(ValueError,'numeric resolution'):
            append_contact_section(canvas,list(map(entity,pair(gap))),measured,focal_id='part',reference_id='base',quad_size=64)
        self.assertEqual(before,canvas.tobytes())

    def test_nanogap_lost_in_input_float_does_not_satisfy_strict_goal(self):
        values=pair(1e-9)
        for item in values:
            item['vertices']=(np.array(item['vertices'])+[0,0,1e12]).tolist();item['pivot_world'][2]+=1e12
        actual=min(v[2] for v in values[1]['vertices'])-max(v[2] for v in values[0]['vertices'])
        self.assertEqual(actual,0.)
        result=evaluate_spatial_goal(scene(values),dict(focal_id='part',reference_id='base',target_clearance_m=1e-9,clearance_tolerance_m=1e-12))
        self.record('captured_zero_is_not_requested_nanogap',result)
        self.assertFalse(result['task_succeeded'])
        self.assertFalse(result['checks']['clearance']['passed'])


class FrameAndTopologyBoundaryTests(BoundaryCase):
    def test_frame_orthonormal_tolerance_both_sides_without_repair(self):
        for requested_error,expected in ((.999e-6,True),(1.001e-6,False)):
            raw=box('part');raw['local_axes'][0][0]=math.sqrt(1+requested_error);before=copy.deepcopy(raw)
            result=rigid_frame_status(raw);self.record(str(requested_error),result)
            self.assertEqual(result['valid'],expected);self.assertEqual(raw,before)

    def test_invalid_raw_frames_do_not_gain_authority_after_normalization(self):
        mutations=[('reflection',{'local_axes':np.diag([-1,1,1]).tolist()}),
            ('shear',{'local_axes':[[1,.01,0],[0,1,0],[0,0,1]]}),
            ('bool',{'local_axes':[[True,0,0],[0,1,0],[0,0,1]]}),
            ('strings',{'local_axes':[['1','0','0'],['0','1','0'],['0','0','1']]}),
            ('source',{'axes_source':'inferred_surface'}),('confidence',{'axes_confidence':'ambiguous'}),
            ('pivot_bool',{'pivot_world':[False,0,0]}),('pivot_string',{'pivot_world':['0',0,0]})]
        for label,fields in mutations:
            with self.subTest(label=label):
                raw=scene();raw['meshes'][1].update(fields)
                try:normalized,_,_=_validated_scene(raw)
                except ValueError:self.record(label,{'refusal':'invalid_scene_before_normalization'});continue
                normalized,_,_=_validated_scene(normalized);route=self.observe(normalized)
                self.record(label,{k:route.get(k) for k in ('route','reason_codes','requires_reobserve','rigid_frame_valid','allow_action')})
                self.assertFalse(route['rigid_frame_valid']);self.assertTrue(route['requires_reobserve']);self.assertIsNot(route['allow_action'],True)

    def test_missing_frame_provenance_does_not_get_defaulted_into_authority(self):
        for field in ('local_axes','pivot_world','axes_source','axes_confidence','axes_reason'):
            with self.subTest(field=field):
                raw=scene();raw['meshes'][1].pop(field);normalized,_,_=_validated_scene(raw);route=self.observe(normalized)
                self.assertFalse(route['rigid_frame_valid']);self.assertTrue(route['requires_reobserve'])

    def test_open_duplicate_reversed_zeroarea_and_thin_solids_are_unknown(self):
        variants={};raw=box('part');raw['faces'].pop();variants['open']=raw
        raw=box('part');raw['faces'].append(raw['faces'][0][:]);variants['duplicate_face']=raw
        raw=box('part');raw['faces'][0]=raw['faces'][0][::-1];variants['inconsistent_winding']=raw
        raw=box('part');raw['faces'][0]=[0,0,1];variants['zero_area']=raw
        variants['near_zero_volume']=box('part',size=(.2,.2,1e-13))
        variants['zero_volume']=box('part',size=(.2,.2,0.))
        variants['microscopic']=box('part',size=(2e-8,2e-8,2e-8))
        variants['connected_oblique_concave']=concave()
        for label,raw in variants.items():
            with self.subTest(label=label):
                result=solid_support_status(raw);self.record(label,result);self.assertFalse(result['supported'],result)
                measured=measure_pair_geometry(entity(raw),entity(box('base',(0,0,-1))),need_clearance=True)
                self.assertFalse(measured['measurement_valid']);self.assertIsNone(measured['is_penetrating']);self.assertIsNone(measured['signed_clearance_m'])

    def test_nonfinite_and_invalid_triangle_indices_refuse_before_core_casting(self):
        for label,kind,value in (('nan','vertex',math.nan),('inf','vertex',math.inf),
                ('negative','face',-1),('out_of_range','face',8),('float','face',.5),('bool','face',True)):
            with self.subTest(label=label):
                raw=scene()
                # Replace an existing integer1 by True, preserving the closed
                # represented solid if a mixed bool/int cast launders the type.
                column=2 if label=='bool' else 0
                raw['meshes'][1]['vertices' if kind=='vertex' else 'faces'][0][column]=value
                with self.assertRaises(ValueError):_validated_scene(raw)

    def test_face_and_edge_scalar_types_are_checked_before_any_core_constructor(self):
        for field in ('faces','edges'):
            for value in (True,np.bool_(True),1.,'1',math.nan,math.inf,-1,8,1<<100):
                with self.subTest(field=field,value=str(value)):
                    raw=scene()
                    if field=='edges':raw['meshes'][1]['edges']=[[0,value]]
                    else:raw['meshes'][1]['faces'][0][2]=value
                    # The first valid mesh may be constructed; the bad mesh
                    # must never enter the coercing core constructor.
                    original=MeshEntity3D.from_dict;constructed=[]
                    def checked(item):
                        constructed.append(item['object_id'])
                        return original(item)
                    with patch('human_eye_plugin.auto_router.MeshEntity3D.from_dict',side_effect=checked):
                        with self.assertRaises(ValueError):_validated_scene(raw)
                    self.assertEqual(constructed,['base'])

    def test_valid_integer_list_tuple_and_numpy_index_arrays_remain_compatible(self):
        for dtype in (None,np.int32,np.int64,np.uint32,np.uint64):
            with self.subTest(dtype=str(dtype)):
                raw=scene()
                if dtype is None:
                    raw['meshes'][1]['faces']=tuple(tuple(np.int64(x) for x in row) for row in FACES)
                    raw['meshes'][1]['edges']=((np.int64(0),np.int64(1)),)
                else:
                    raw['meshes'][1]['faces']=np.asarray(FACES,dtype=dtype)
                    raw['meshes'][1]['edges']=np.asarray([[0,1]],dtype=dtype)
                normalized,_,_=_validated_scene(raw)
                self.assertEqual(normalized['meshes'][1]['faces'],FACES)
                self.assertEqual(normalized['meshes'][1]['edges'],[[0,1]])

    def test_extreme_finite_geometry_is_unknown_not_silently_clear(self):
        raw=box('part',size=(1e308,1e308,1e308))
        result=solid_support_status(raw);self.record('finite_overflow_geometry',result)
        self.assertFalse(result['supported'])
        measured=measure_pair_geometry(entity(raw),entity(box('base')),need_clearance=True)
        self.record('finite_overflow_pair',measured)
        self.assertFalse(measured['measurement_valid']);self.assertIsNone(measured['is_penetrating'])
        json.dumps(measured,allow_nan=False)


class BudgetAndInputBoundaryTests(BoundaryCase):
    def test_dense_arithmetic_limit_minus_equal_plus_one(self):
        for value in (999999,1000000,1000001):
            with self.subTest(value=value):
                result=work_budget_status([counted('a',value,1)],purpose='mesh_validation');self.record(str(value),result)
                self.assertEqual(result['estimates']['largest_dense_elements'],value)
                self.assertEqual(result['within_budget'],value<=1000000)
                self.assertEqual('dense_geometry_work_limit' in result['reason_codes'],value>1000000)

    def test_sat_arithmetic_limit_minus_equal_plus_one_without_other_limit(self):
        for total_vertices,edge_product,wanted in ((17,117647,1999999),(2,1000000,2000000),(3,666667,2000001)):
            with self.subTest(value=wanted):
                values=[counted('a',1,0,1),counted('b',total_vertices-1,0,edge_product)]
                result=work_budget_status(values,query_pairs=[['a','b']]);self.record(str(wanted),result)
                self.assertEqual(result['estimates']['largest_sat_projection_elements'],wanted)
                self.assertEqual(result['within_budget'],wanted<=2000000)
                self.assertEqual(result['reason_codes'],['sat_projection_work_limit'] if wanted>2000000 else [])

    def test_scene_arithmetic_limit_minus_equal_plus_one(self):
        for value in (7999999,8000000,8000001):
            with self.subTest(value=value):
                quotient,remainder=divmod(value,1000000);values=[counted(str(i),1000000,1) for i in range(quotient)]
                if remainder:values.append(counted('tail',remainder,1))
                result=work_budget_status(values,purpose='mesh_validation');self.record(str(value),result)
                self.assertEqual(result['estimates']['scene_work_elements'],value)
                self.assertEqual(result['reason_codes'],['scene_geometry_work_limit'] if value>8000000 else [])

    def test_actual_fifteen_and_sixteen_prisms_are_distinct_from_count_sentinels(self):
        for sides,sat,expected in ((15,1700160,True),(16,2081280,False)):
            with self.subTest(sides=sides):
                a,b=[entity(prism(n,sides,z)) for n,z in (('base',-.01),('part',.012))]
                self.assertTrue(solid_support_status(a)['supported']);self.assertTrue(solid_support_status(b)['supported'])
                budget=work_budget_status([a,b]);self.record(str(sides),budget)
                self.assertEqual(budget['estimates']['largest_sat_projection_elements'],sat);self.assertEqual(budget['within_budget'],expected)
                measured=measure_pair_geometry(a,b,need_clearance=True)
                self.record(str(sides)+'_measurement',measured)
                if expected:self.assertAlmostEqual(measured['signed_clearance_m'],.002,delta=2e-12)
                else:self.assertFalse(measured['measurement_valid']);self.assertEqual(measured['reason'],'geometry_resource_limit')

    def test_256_real_sparse_objects_keep_all_255_coverage_records(self):
        values=pair()+[box('far-'+str(i),(3+i,2,0)) for i in range(254)]
        normalized,meshes,_=_validated_scene(scene(values));self.assertEqual(len(meshes),256)
        route=self.observe(normalized);facts=json.loads(route['context_text'])
        self.record('256_real_objects',{k:route.get(k) for k in ('route','reason_codes','observation_status')})
        self.assertEqual(route['route'],'engine');self.assertEqual(len(facts['objects']),256)
        self.assertEqual(len(facts['scene_contacts']),255)
        self.assertEqual({r['object_id'] for r in facts['scene_contacts']},{x['object_id'] for x in values if x['object_id']!='part'})

    def test_257_objects_refuse_before_constructing_any_mesh(self):
        values=pair()+[box('far-'+str(i),(3+i,2,0)) for i in range(255)]
        with patch('human_eye_plugin.auto_router.MeshEntity3D.from_dict') as constructor:
            with self.assertRaisesRegex(ValueError,'1..256'):_validated_scene(scene(values))
            constructor.assert_not_called()

    def test_vertex_input_allocation_guard_minus_equal_plus_one(self):
        for count in (499999,500000,500001):
            with self.subTest(count=count):
                raw=box('part');vertices=AllocationGuardList(count);raw['vertices']=vertices
                with self.assertRaises(ConversionReached if count<=500000 else ValueError):_validated_scene(scene([raw]))
                self.assertEqual(vertices.converted,count<=500000)

    def test_vertex_input_limit_is_cumulative_across_meshes(self):
        for count in (499992,499993):
            with self.subTest(count=count):
                raw=box('part');vertices=AllocationGuardList(count);raw['vertices']=vertices
                with self.assertRaises(ConversionReached if count==499992 else ValueError):_validated_scene(scene([box('base'),raw]))
                self.assertEqual(vertices.converted,count==499992)

    def test_face_input_over_limit_refuses_before_vertex_or_face_conversion(self):
        raw=box('part');vertices=AllocationGuardList(8);faces=AllocationGuardList(1000001);raw.update(vertices=vertices,faces=faces)
        with self.assertRaisesRegex(ValueError,'before allocation'):_validated_scene(scene([raw]))
        self.assertFalse(vertices.converted);self.assertFalse(faces.converted)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--report',type=Path);args=parser.parse_args(argv)
    identity=runtime_identity();root=Path(__file__).resolve().parents[1]
    before={x['path']:hashlib.sha256((root/x['path']).read_bytes()).hexdigest() for x in identity['source_files']}
    suite=unittest.defaultTestLoader.loadTestsFromModule(__import__(__name__,fromlist=['_']))
    stream=io.StringIO();result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
    after={name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in before}
    report=dict(schema_version='1.0',status='pass' if result.wasSuccessful() and before==after else 'fail',
        scope='bounded_local_geometry_boundary_suite_not_Blender_model_or_performance',runtime_identity=identity,
        criteria_sha256=hashlib.sha256((root/'verification/fixes/20261023_field_validation/extreme_01/ENGINE_BOUNDARY_CRITERIA.md').read_bytes()).hexdigest(),
        test_source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),tests_run=result.testsRun,
        failures=[dict(test=str(t),traceback=s) for t,s in result.failures],errors=[dict(test=str(t),traceback=s) for t,s in result.errors],
        skipped=[dict(test=str(t),reason=s) for t,s in result.skipped],runtime_sources_unchanged=before==after,
        source_hashes_before=before,source_hashes_after=after,observations=OBSERVATIONS,unittest_output=stream.getvalue())
    if args.report:
        args.report.parent.mkdir(parents=True,exist_ok=True)
        with args.report.open('x',encoding='utf-8',newline='\n') as handle:json.dump(report,handle,ensure_ascii=False,indent=2,allow_nan=False)
    print(stream.getvalue(),end='')
    return 0 if report['status']=='pass' else 1


if __name__=='__main__':
    raise SystemExit(main())
