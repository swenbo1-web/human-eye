"""New analytical assets and output contracts; no model/host performance claim.

All fixture builders are self-contained so this test file can run from an
isolated installed wheel. Engine geometry is never used as the oracle.
"""
from __future__ import annotations

import base64
import copy
import io
import json
import math
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image

from human_eye_module1_operators import MeshEntity3D
from human_eye_plugin.auto_router import HumanEyeAutoRouter
from human_eye_plugin.geometry_safety import measure_pair_geometry, solid_support_status
from human_eye_plugin.host_runtime import GuardedHostRuntime


SIGNS = np.array([[-1,-1,-1],[1,-1,-1],[1,1,-1],[-1,1,-1],
                  [-1,-1,1],[1,-1,1],[1,1,1],[-1,1,1]], dtype=float)
TRIANGLES = np.array([[0,2,1],[0,3,2],[4,5,6],[4,6,7],[0,1,5],[0,5,4],
                     [2,3,7],[2,7,6],[1,2,6],[1,6,5],[3,0,4],[3,4,7]])


def mesh(identity, vertices, faces, *, focal=False, color=(120,145,180), pivot=None):
    points = np.asarray(vertices, dtype=float)
    return MeshEntity3D(identity, '#'+identity, identity, points, np.asarray(faces), None,
        color, focal, local_axes=np.eye(3),
        pivot_world=np.asarray(pivot if pivot is not None else points.mean(axis=0)),
        axes_source='host', axes_confidence='explicit', axes_reason='analytic_fixture_frame').to_dict()


def box(identity, center, size, **kwargs):
    return mesh(identity, SIGNS * np.asarray(size)/2 + np.asarray(center), TRIANGLES,
                pivot=center, **kwargs)


def component_union(identity, boxes):
    vertices, faces = [], []
    for center, size in boxes:
        offset = len(vertices)
        vertices.extend((SIGNS*np.asarray(size)/2+np.asarray(center)).tolist())
        faces.extend((TRIANGLES+offset).tolist())
    return mesh(identity, vertices, faces, color=(125,130,140))


def square_ring(identity='ring'):
    """Closed genus-one square tube with an actual empty through-hole."""
    outer = [(-.06,-.06),(.06,-.06),(.06,.06),(-.06,.06)]
    inner = [(-.025,-.025),(.025,-.025),(.025,.025),(-.025,.025)]
    vertices = [(x,y,z) for z in (-.015,.015) for x,y in outer+inner]
    quads = []
    for i in range(4):
        j = (i+1)%4
        quads.extend([(8+i,8+j,12+j,12+i), (i,4+i,4+j,j),
                      (i,j,8+j,8+i), (4+j,4+i,12+i,12+j)])
    faces = [triangle for a,b,c,d in quads for triangle in ((a,b,c),(a,c,d))]
    return mesh(identity, vertices, faces, color=(150,145,135))


def l_prism(identity='L-slot'):
    polygon = [(-.06,-.06),(.06,-.06),(.06,-.025),(-.025,-.025),(-.025,.06),(-.06,.06)]
    vertices = [(x,y,z) for z in (-.02,.02) for x,y in polygon]
    top = [(0,1,2),(0,2,3),(0,3,5),(3,4,5)]
    faces = [(c,b,a) for a,b,c in top] + [(a+6,b+6,c+6) for a,b,c in top]
    for i in range(6):
        j=(i+1)%6
        faces.extend(((i,j,j+6),(i,j+6,i+6)))
    return mesh(identity, vertices, faces, color=(160,145,125))


def scene(name, meshes, *, host_execution=None):
    result = dict(revision='complex-'+name, unit='m', coordinate_frame='world',
                  source='independent_analytic_complex_fixture', meshes=meshes)
    if host_execution is not None:
        result['host_execution'] = copy.deepcopy(host_execution)
    return result


def fixture(name):
    if name == 'slotted_components':
        walls = [((-.045,0,.015),(.01,.10,.03)),((.045,0,.015),(.01,.10,.03)),
                 ((0,.07,.015),(.10,.01,.03))]
        return dict(name=name, scene=scene(name, [component_union('bracket', walls),
            box('insert',(0,0,.015),(.0785,.04,.03),focal=True,color=(25,100,215))]),
            focal='insert',reference='bracket',oracle=dict(kind='exact_positive',clearance_m=.00075,
            explanation='Inner wall x=+/-0.04; insert x=+/-0.03925; disconnected back rail is farther.'))
    if name == 'thin_25um':
        return dict(name=name,scene=scene(name,[box('thin-base',(0,0,0),(.21,.13,.0001)),
            box('foil',(0,0,.0001),(.07,.045,.00005),focal=True,color=(25,110,215))]),
            focal='foil',reference='thin-base',oracle=dict(kind='exact_positive',clearance_m=.000025,
            explanation='Reference top z=0.00005; foil bottom z=0.000075.'))
    if name in ('square_hole','L_slot'):
        is_ring=name=='square_hole'
        ref=square_ring() if is_ring else l_prism()
        center=(0,0,0) if is_ring else (.02,.02,0)
        size=(.012,.012,.02) if is_ring else (.01,.01,.02)
        return dict(name=name,scene=scene(name,[ref,box('probe',center,size,focal=True)]),
            focal='probe',reference=ref['object_id'],oracle=dict(kind='exact_positive',
            physical_nonpenetrating=True,clearance_m=.019 if is_ring else .04,
            analytic_clearance_m=.019 if is_ring else .04,
            explanation='The probe lies wholly inside the empty opening; a convex hull would falsely fill it.'))
    if name == 'nested':
        return dict(name=name,scene=scene(name,[box('enclosure',(0,0,0),(.2,.18,.16)),
            box('nested-insert',(.015,.012,.01),(.02,.03,.04),focal=True,color=(25,110,215))]),
            focal='nested-insert',reference='enclosure',oracle=dict(kind='contained_penetrating',
            explanation='All six insert bounds lie strictly inside the closed solid enclosure.'))
    if name == 'occluded_change':
        return dict(name=name,scene=scene(name,[box('chamber',(0,0,0),(.44,.38,.32),color=(115,120,130)),
            box('target',(-.03,-.02,.01),(.025,.035,.03),focal=True,color=(25,110,215)),
            box('hidden-marker',(.07,.06,-.03),(.012,.016,.014),color=(220,80,40))]),
            focal='target',reference='chamber',oracle=dict(kind='contained_penetrating',
            explanation='The opaque closed enclosure fully occludes both internal meshes in natural surface views.'))
    if name == 'many_obstacles':
        meshes=[box('work-base',(0,0,-.0125),(.16,.14,.025)),
                box('work-insert',(0,0,.0125),(.04,.03,.02),focal=True,color=(25,110,215)),
                box('closer-side',(.0254,0,.0125),(.01,.025,.02),color=(215,80,40))]
        for i in range(20):
            angle=i*math.tau/20
            meshes.append(box('obstacle-%02d'%i,(.22*math.cos(angle),.22*math.sin(angle),.02),
                (.014,.017,.025),color=(90+(i*13)%130,90+(i*19)%130,90+(i*23)%130)))
        return dict(name=name,scene=scene(name,meshes),focal='work-insert',reference='work-base',
            oracle=dict(kind='exact_positive',clearance_m=.0025,nearest_id='closer-side',nearest_m=.0004,
            explanation='Base top z=0, insert bottom z=.0025; side inner x=.0204, insert max x=.02.'))
    raise ValueError('Unknown independent fixture '+name)


FIXTURE_NAMES = ('slotted_components','thin_25um','square_hole','L_slot','nested','occluded_change','many_obstacles')


def observe(value, *, include_image=False, query=None, router=None):
    event=dict(event='before_model',session_id='complex-quality',scene=value['scene'],
        task_kind='spatial_3d',focal_id=value['focal'],reference_id=value['reference'],
        task_instruction='Inspect represented mesh clearance and contact; observation only.',
        include_image=include_image)
    if query is not None:
        event['query']=query
    # A fixed optional-attention clock isolates quality from machine scheduling.
    # No latency or throughput claims are based on this deterministic mode.
    with patch('human_eye_plugin.attention_rendering.time.perf_counter', return_value=0.):
        return (router or HumanEyeAutoRouter(quad_size=128)).handle_event(event)


def decode(result):
    raw=base64.b64decode(result['image']['data'],validate=True)
    with Image.open(io.BytesIO(raw)) as im:
        im.load()
        return im.convert('RGB')


def pair(value):
    by_id={m['object_id']:MeshEntity3D.from_dict(m) for m in value['scene']['meshes']}
    return by_id[value['focal']],by_id[value['reference']]


class ComplexSceneQualityTests(unittest.TestCase):
    def test_new_concave_assets_are_closed_two_manifolds(self):
        for build in (square_ring,l_prism):
            with self.subTest(asset=build.__name__):
                value=build(); counts={}
                for tri in value['faces']:
                    for a,b in zip(tri,tri[1:]+tri[:1]):
                        edge=tuple(sorted((a,b)));counts[edge]=counts.get(edge,0)+1
                self.assertTrue(counts)
                self.assertEqual(set(counts.values()),{2})
                # Connected surface, not disconnected convex-component stand-in.
                neighbours={i:set() for i in range(len(value['vertices']))}
                for a,b in counts:
                    neighbours[a].add(b);neighbours[b].add(a)
                seen={0};todo=[0]
                while todo:
                    for n in neighbours[todo.pop()]-seen:
                        seen.add(n);todo.append(n)
                self.assertEqual(len(seen),len(value['vertices']))

    def test_empty_hole_and_L_cavity_have_exact_clearance_without_filling(self):
        for name in ('square_hole','L_slot'):
            with self.subTest(name=name):
                value=fixture(name);focal,reference=pair(value)
                self.assertIs(solid_support_status(reference)['supported'],True)
                measured=measure_pair_geometry(focal,reference,need_clearance=True)
                self.assertIs(measured['measurement_valid'],True)
                self.assertIs(measured['is_penetrating'],False)
                self.assertAlmostEqual(measured['signed_clearance_m'],value['oracle']['clearance_m'],places=12)
                result=observe(value)
                self.assertIsNot(result['allow_action'],True)
                self.assertEqual(result['observation_status'],'complete')
                facts=json.loads(result['context_text'])
                self.assertEqual(facts['measurement']['clearance_state'],'positive_clearance')
                self.assertAlmostEqual(facts['measurement']['signed_clearance_m'],value['oracle']['clearance_m'],places=12)

    def test_concave_construction_volume_and_topology_preserve_empty_openings(self):
        for build,expected_volume,expected_euler in ((square_ring,(.12*.12-.05*.05)*.03,0),
                                                    (l_prism,(.12*.12-.085*.085)*.04,2)):
            with self.subTest(asset=build.__name__):
                value=build();vertices=value['vertices'];directed={};edges=set();volume=0.
                for a,b,c in value['faces']:
                    x,y,z=[vertices[i] for i in (a,b,c)]
                    volume+=(x[0]*(y[1]*z[2]-y[2]*z[1])-x[1]*(y[0]*z[2]-y[2]*z[0])
                             +x[2]*(y[0]*z[1]-y[1]*z[0]))/6
                    for u,v in ((a,b),(b,c),(c,a)):
                        directed[(u,v)]=directed.get((u,v),0)+1;edges.add(tuple(sorted((u,v))))
                self.assertAlmostEqual(volume,expected_volume,places=12)
                self.assertEqual(len(vertices)-len(edges)+len(value['faces']),expected_euler)
                self.assertTrue(all(directed.get((a,b))==directed.get((b,a))==1 for a,b in edges))

    def test_disconnected_slot_has_certified_three_components_and_075mm_gap(self):
        value=fixture('slotted_components');focal,reference=pair(value)
        support=solid_support_status(reference)
        self.assertTrue(support['supported']);self.assertEqual(support['component_count'],3)
        measured=measure_pair_geometry(focal,reference,need_clearance=True)
        self.assertTrue(measured['measurement_valid']);self.assertFalse(measured['is_penetrating'])
        self.assertAlmostEqual(measured['signed_clearance_m'],value['oracle']['clearance_m'],places=12)

    def test_slot_side_collision_rejected_by_full_geometry(self):
        value=fixture('slotted_components');router=HumanEyeAutoRouter(quad_size=128)
        result=observe(value,router=router)
        blocked=router.handle_event(dict(event='before_action',session_id='complex-quality',
            observation_id=result['observation_id'],focal_id=value['focal'],reference_id=value['reference'],
            action=dict(translation=[.001,0,0])))
        self.assertIs(blocked['allow_action'],False)
        self.assertEqual(blocked['reason_codes'],['candidate_collision'])

    def test_25um_clearance_preserves_unrounded_mesh_distance(self):
        value=fixture('thin_25um');focal,reference=pair(value)
        measured=measure_pair_geometry(focal,reference,need_clearance=True)
        self.assertTrue(measured['measurement_valid']);self.assertFalse(measured['is_penetrating'])
        self.assertAlmostEqual(measured['signed_clearance_m'],25e-6,places=13)
        facts=json.loads(observe(value)['context_text'])
        self.assertAlmostEqual(facts['measurement']['signed_clearance_m'],25e-6,places=13)
        self.assertIs(facts['measurement']['clearance_exact'],True)

    def test_nested_closed_solid_is_penetrating_not_empty_free_space(self):
        value=fixture('nested');focal,reference=pair(value)
        measured=measure_pair_geometry(focal,reference,need_clearance=True)
        self.assertTrue(measured['measurement_valid']);self.assertTrue(measured['is_penetrating'])
        self.assertLess(measured['signed_clearance_m'],0)
        facts=json.loads(observe(value)['context_text'])
        self.assertEqual(facts['measurement']['measurement_kind'],'certified_penetration')
        self.assertFalse(facts['measurement']['clearance_exact'])

    def test_many_obstacles_exact_nearest_is_side_not_display_reference(self):
        value=fixture('many_obstacles')
        facts=json.loads(observe(value,query={'mode':'nearest'})['context_text'])
        query=facts['query_result']
        self.assertEqual(query['status'],'complete')
        self.assertEqual(query['ranked_object_ids'][0],value['oracle']['nearest_id'])
        side=next(row for row in facts['scene_contacts'] if row['object_id']=='closer-side')
        self.assertAlmostEqual(side['signed_clearance_m'],.0004,places=12)
        self.assertAlmostEqual(facts['measurement']['signed_clearance_m'],.0025,places=12)
        self.assertEqual(len(facts['objects']),23)

    def test_many_obstacle_budget_does_not_invent_complete_ranking(self):
        facts=json.loads(observe(fixture('many_obstacles'),query={'mode':'nearest','max_exact_pairs':1})['context_text'])
        self.assertIsNone(facts['query_result']['ranked_object_ids'])
        self.assertTrue(facts['query_result']['unresolved_object_ids'])
        self.assertEqual(facts['query_result']['status'],'unknown')

    def test_unsupported_extra_asset_preserves_main_pair_but_blocks_execution(self):
        value=fixture('thin_25um');extra=square_ring('extra-hole')
        # An oblique closed ring remains unknown; world-axis rings are tested
        # separately as a newly supported class, not used to weaken this gate.
        extra['vertices']=[[x+.125*z,y,z] for x,y,z in extra['vertices']]
        value['scene']['meshes'].append(extra)
        router=HumanEyeAutoRouter(quad_size=128);result=observe(value,router=router)
        facts=json.loads(result['context_text'])
        self.assertTrue(facts['measurement']['measurement_valid'])
        self.assertEqual(facts['observation_status'],'partial')
        self.assertIn('extra-hole',facts['scene_assessment']['unknown_object_ids'])
        blocked=router.handle_event(dict(event='before_action',session_id='complex-quality',
            observation_id=result['observation_id'],focal_id=value['focal'],reference_id=value['reference'],
            action=dict(translation=[0,0,.001])))
        self.assertIs(blocked['allow_action'],False)

    def test_open_or_nonmanifold_asset_cannot_claim_clearance(self):
        value=fixture('thin_25um');focal,reference=pair(value)
        for faces in (reference.faces[:-1],np.concatenate((reference.faces,reference.faces[:1]))):
            with self.subTest(face_count=len(faces)):
                broken=copy.deepcopy(reference);broken.faces=faces
                self.assertIs(solid_support_status(broken)['supported'],False)
                measured=measure_pair_geometry(focal,broken,need_clearance=True)
                self.assertIs(measured['measurement_valid'],False)
                self.assertIsNone(measured['signed_clearance_m'])

    def test_png_has_four_complete_views_and_stable_visible_label_contract(self):
        result=observe(fixture('many_obstacles'),include_image=True)
        picture=decode(result);facts=json.loads(result['context_text']);canvas=facts['canvas']
        self.assertEqual(picture.size,(256,256));self.assertEqual(len(canvas['views']),4)
        self.assertTrue(canvas['raster_schedule']['canvas_complete'])
        labels=canvas['object_labels']
        self.assertEqual(len(labels),23)
        self.assertEqual(len({row['stable_label'] for row in labels}),23)
        for view in canvas['views']:
            self.assertIs(view.get('labels_certify_visibility',False),False)
            for label in view.get('projected_labels',[]):
                self.assertGreater(label['surface_visible_pixels'],0)
                x0,y0,x1,y1=label['label_box_px']
                self.assertTrue(0<=x0<x1<=128 and 0<=y0<y1<=128)

    def test_thin_analytical_section_preserves_all_natural_pixels(self):
        value=fixture('thin_25um')
        normal=observe(value,include_image=True)
        diagnostic=observe(value,include_image=True,query={'visual_diagnostic':'contact_section'})
        left,right=decode(normal),decode(diagnostic)
        self.assertEqual(left.tobytes(),right.crop((0,0,left.width,left.height)).tobytes())
        facts=json.loads(diagnostic['context_text']);evidence=facts['visual_diagnostics']
        self.assertEqual(evidence['status'],'available')
        self.assertAlmostEqual(evidence['m_per_pixel']*12,25e-6,places=13)
        for key in ('natural_visibility_certified','free_path_certified','execution_authority'):
            self.assertIs(evidence[key],False)
        rows={row['object_id']:row for row in evidence['objects']}
        lower=max(p[1] for s in rows['thin-base']['viewport_segments_plane_m'] for p in s)
        upper=min(p[1] for s in rows['foil']['viewport_segments_plane_m'] for p in s)
        self.assertAlmostEqual((upper-lower)/evidence['m_per_pixel'],12,places=8)

    def test_hidden_mesh_change_detected_without_fabricating_natural_visibility(self):
        value=fixture('occluded_change');router=HumanEyeAutoRouter(quad_size=128)
        before=observe(value,include_image=True,router=router)
        changed=copy.deepcopy(value);marker=changed['scene']['meshes'][-1]
        marker['vertices']=(np.asarray(marker['vertices'])+[.003,.002,0]).tolist()
        marker['pivot_world']=(np.asarray(marker['pivot_world'])+[.003,.002,0]).tolist()
        after=observe(changed,include_image=True,router=router)
        self.assertEqual(decode(before).tobytes(),decode(after).tobytes())
        self.assertNotEqual(before['scene_fingerprint'],after['scene_fingerprint'])
        facts=json.loads(after['context_text'])
        self.assertEqual(facts['scene_memory']['changes']['transform'],['hidden-marker'])
        for view in facts['canvas']['views']:
            self.assertNotIn('hidden-marker',[label['object_id'] for label in view.get('projected_labels',[])])

    def test_readable_modified_host_geometry_never_becomes_write_permission(self):
        value=fixture('thin_25um')
        value['scene']['host_execution']=dict(schema_version='1.0',operation='rigid_transform',
            supported=False,scope='independent_static_rigid_meshes',
            reasons=[dict(object_id='foil',object_name='foil',reason='modifiers_present')])
        class Host:
            calls=0
            def capture_scene(self):
                return copy.deepcopy(value['scene'])
            def apply_transform(self,*args,**kwargs):
                self.calls+=1
                raise RuntimeError('An unsupported host must never be written')
        host=Host();runtime=GuardedHostRuntime(host,quad_size=128,require_execution_capability=True)
        observed=runtime.before_model(session_id='modified',task_instruction='Read thin gap.',
            focal_id='foil',reference_id='thin-base',messages=[],include_image=False)
        self.assertEqual(observed['routing']['route'],'engine')
        result=runtime.execute_action(session_id='modified',action={'translation':[0,0,.001]})
        self.assertFalse(result['executed']);self.assertEqual(host.calls,0)
        self.assertIn('modifiers_present',result['reason_codes'])
        self.assertFalse(runtime.status['quarantined'])


if __name__=='__main__':
    unittest.main()
