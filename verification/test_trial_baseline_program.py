"""Public-data solver feasibility; no engine, private oracle or Blender imports."""
from __future__ import annotations

from copy import deepcopy
import ast
import hashlib
import json
import math
from pathlib import Path
import struct
import time
import unittest

from verification.model_trial.baseline_program import PROGRAM, READONLY_PROGRAM, build_program
from verification.model_trial.compute import RestrictedCompute


SIGNS = [(-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),
         (-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1)]
FACES = [[0,2,1],[0,3,2],[4,5,6],[4,6,7],[0,1,5],[0,5,4],
         [2,3,7],[2,7,6],[1,2,6],[1,6,5],[3,0,4],[3,4,7]]
SAMPLES=[]


def f32(value):
    return struct.unpack('<f',struct.pack('<f',value))[0]


def refresh(obj):
    obj['world_vertices']=[[f32(sum(obj['matrix'][r][k]*local[k] for k in range(3))+
                                  obj['matrix'][r][3]) for r in range(3)]
                           for local in obj['local_vertices']]


def box(name,size,center,angle=0):
    s,c=f32(math.sin(angle)),f32(math.cos(angle))
    obj={'name':name,'object_id':'public:'+name,
         'local_vertices':[[f32(sign[k]*size[k]/2) for k in range(3)] for sign in SIGNS],
         'faces':deepcopy(FACES),
         'matrix':[[c,0,s,f32(center[0])],[0,1,0,f32(center[1])],[-s,0,c,f32(center[2])],[0,0,0,1]],
         'color':[.12,.4,.85,1]}
    refresh(obj)
    return obj


def public_scene(angle_deg=0,gap=.004,origin=(0.,0.,0.),dense=False):
    angle=math.radians(angle_deg)
    n=[math.sin(angle),0.,math.cos(angle)]
    objects=[box('GreyBase',[.2,.2,.2],origin,angle),
             box('BluePart',[.06,.06,.1],[origin[k]+n[k]*(.15+gap) for k in range(3)],angle)]
    if dense:
        for i in range(24):
            objects.append(box('Distractor_%02d'%i,[.01,.01,.01],
                [origin[0]+.3+.025*(i%6),origin[1]-.05+.025*(i//6),origin[2]+.03]))
    return {'unit':'m','coordinate_frame':'world','revision':'public:r0',
            'objects':sorted(objects,key=lambda o:o['name'])}


def named(scene,name):
    return next(obj for obj in scene['objects'] if obj['name']==name)


def independent_projection_gap(scene):
    # Test expectation from the public matrix and native vertices only.
    base,part=named(scene,'GreyBase'),named(scene,'BluePart')
    n=[base['matrix'][k][2] for k in range(3)]
    length=math.sqrt(sum(value*value for value in n));n=[value/length for value in n]
    return min(sum(n[k]*v[k] for k in range(3)) for v in part['world_vertices'])-max(
        sum(n[k]*v[k] for k in range(3)) for v in base['world_vertices'])


def compute(scene,code=PROGRAM):
    start=time.perf_counter()
    result=RestrictedCompute().run(code,scene)
    SAMPLES.append({'objects':len(scene['objects']),'instructions':result['instructions'],
                    'seconds':time.perf_counter()-start,
                    'output_bytes':len(json.dumps(result,allow_nan=False).encode()),
                    'status':result['result']['status']})
    return result


def execute_witness(scene):
    initial=deepcopy(scene)
    current=deepcopy(scene)
    writes=[]
    for index in range(9):
        reply=compute(current)['result']
        if reply['status']=='satisfied':
            return initial,current,writes,reply
        if reply['status']!='candidate':
            raise AssertionError(reply)
        if len(writes)>=8:
            raise AssertionError('cannot exceed the actual eight-write budget')
        before=deepcopy(named(current,'BluePart'))
        dz=reply['delta_world_m'][2]
        part=named(current,'BluePart')
        part['matrix'][2][3]=f32(part['matrix'][2][3]+dz)
        refresh(part)
        actual=part['matrix'][2][3]-before['matrix'][2][3]
        if abs(actual)>.001:raise AssertionError('actual simulated write exceeds1mm')
        current['revision']='public:r'+str(index+1)
        writes.append(actual)
    raise AssertionError('witness failed to converge')


class BaselineProgramTests(unittest.TestCase):
    def test_plain_pair_and_public_evidence(self):
        scene=public_scene()
        before=deepcopy(scene)
        response=compute(scene)['result']
        self.assertEqual(response['status'],'candidate')
        self.assertAlmostEqual(response['gap_m'],independent_projection_gap(scene),places=14)
        self.assertEqual(response['delta_world_m'],[0,0,-.00099])
        self.assertEqual(scene,before)
        self.assertEqual(response['revision'],scene['revision'])

    def test_dense26_fits_default_vm_budget(self):
        result=compute(public_scene(14,.005,(.071,-.043,.02),dense=True))
        self.assertEqual(result['result']['status'],'candidate')
        self.assertEqual(result['result']['checked_other_objects'],25)
        self.assertLess(result['instructions'],300000)
        self.assertLess(SAMPLES[-1]['seconds'],8)
        self.assertLess(SAMPLES[-1]['output_bytes'],4096)

    def test_angle_gap_translation_variants_complete_same_cap(self):
        for angle in (-14,-10,-6,6,10,14):
            for gap in (.003,.004,.005):
                origin=(.073,-.047,.021) if angle<0 else (-.061,.089,-.017)
                with self.subTest(angle=angle,gap=gap):
                    initial,final,writes,reply=execute_witness(public_scene(angle,gap,origin,dense=True))
                    self.assertEqual(reply['status'],'satisfied')
                    self.assertLessEqual(len(writes),8)
                    self.assertLess(sum(abs(x) for x in writes),.008)
                    self.assertLess(abs(independent_projection_gap(final)-.001),1e-6)
                    a,b=named(initial,'BluePart'),named(final,'BluePart')
                    self.assertEqual(a['local_vertices'],b['local_vertices'])
                    self.assertEqual(a['faces'],b['faces'])
                    self.assertTrue(all(a['matrix'][r][c]==b['matrix'][r][c]
                        for r in range(4) for c in range(4) if not (r==2 and c==3)))
                    self.assertEqual([o for o in initial['objects'] if o['name']!='BluePart'],
                                     [o for o in final['objects'] if o['name']!='BluePart'])

    def test_readonly_reports_without_action(self):
        scene=public_scene(-14,.005,(-.07,.09,.01),dense=True)
        result=compute(scene,READONLY_PROGRAM)['result']
        self.assertEqual(result['status'],'measured')
        self.assertNotIn('delta_world_m',result)
        self.assertAlmostEqual(result['gap_m'],independent_projection_gap(scene),places=14)

    def test_open_focal_and_reference_refuse(self):
        for name in ('BluePart','GreyBase'):
            scene=public_scene();named(scene,name)['faces']=named(scene,name)['faces'][:2]+named(scene,name)['faces'][4:]
            with self.subTest(name=name):
                result=compute(scene)['result']
                self.assertEqual(result['status'],'unsupported')
                self.assertNotIn('delta_world_m',result)

    def test_invalid_closed_box_topology_refuses(self):
        mutations=[lambda o:o['faces'].__setitem__(0,o['faces'][1][:]),
                   lambda o:o['faces'].__setitem__(0,list(reversed(o['faces'][0]))),
                   lambda o:o['faces'].__setitem__(0,[0,0,1]),
                   lambda o:o['local_vertices'].__setitem__(0,o['local_vertices'][1][:])]
        for mutate in mutations:
            scene=public_scene();mutate(named(scene,'BluePart'))
            self.assertEqual(compute(scene)['result']['status'],'unsupported')

    def test_invalid_transform_or_frame_refuses(self):
        for matrix_edit in ('shear','reflect','singular','nonaffine'):
            scene=public_scene();part=named(scene,'BluePart')
            if matrix_edit=='shear':part['matrix'][0][1]=.1
            if matrix_edit=='reflect':part['matrix'][0][0]=-1
            if matrix_edit=='singular':part['matrix'][0][0]=0
            if matrix_edit=='nonaffine':part['matrix'][3][3]=2
            refresh(part)
            self.assertEqual(compute(scene)['result']['status'],'unsupported')
        for field,value in (('unit','mm'),('coordinate_frame','local')):
            scene=public_scene();scene[field]=value
            self.assertEqual(compute(scene)['result']['status'],'unsupported')

    def test_footprint_or_collision_blocks_action(self):
        scene=public_scene();part=named(scene,'BluePart')
        part['matrix'][0][3]=.3;refresh(part)
        self.assertEqual(compute(scene)['result']['status'],'unsupported')
        for gap in (.001,.004):
            scene=public_scene(gap=gap);part=named(scene,'BluePart')
            scene['objects'].append(box('Obstacle',[.02,.02,.02],[part['matrix'][k][3] for k in range(3)]))
            result=compute(scene)['result']
            self.assertEqual(result['status'],'blocked')
            self.assertNotIn('delta_world_m',result)

    def test_tilted_aabb_overlap_gets_narrow_phase(self):
        result=compute(public_scene(14))['result']
        self.assertEqual(result['status'],'candidate')
        self.assertGreaterEqual(result['narrow_phase_objects'],1)

    def test_already_satisfied_no_action(self):
        result=compute(public_scene(gap=.001))['result']
        self.assertEqual(result['status'],'satisfied')
        self.assertNotIn('delta_world_m',result)

    def test_program_has_no_import_or_private_fixture_input(self):
        tree=ast.parse(PROGRAM)
        self.assertFalse(any(isinstance(node,(ast.Import,ast.ImportFrom,ast.Attribute)) and
            not (isinstance(node,ast.Attribute) and isinstance(node.value,ast.Name) and node.value.id=='math')
            for node in ast.walk(tree)))
        self.assertNotIn('normal',PROGRAM)
        self.assertNotIn('owner',PROGRAM)
        self.assertNotIn('seed',PROGRAM)
        self.assertNotIn('oracle',PROGRAM)
        self.assertLess(len(PROGRAM),64000)

    def test_actual_isolated_worker_dense26(self):
        from verification.model_trial.deadline import EpisodeDeadline
        from verification.model_trial.isolated_compute import run_isolated_compute
        d=EpisodeDeadline(10)
        try:
            scene=public_scene(-14,.005,(-.091,.087,.013),dense=True)
            expected=compute(scene)
            started=time.perf_counter()
            actual=run_isolated_compute(PROGRAM,scene,d)
            self.assertEqual(actual,expected)
            self.assertLess(time.perf_counter()-started,8)
        finally:d.close()

    def test_invalid_explicit_task_settings_rejected(self):
        for values in ({'mode':'hidden'},{'target_m':float('nan')},{'step_cap_m':True},
                       {'step_cap_m':.001},{'target_m':0}):
            with self.assertRaises(ValueError):build_program(**values)


if __name__=='__main__':
    unittest.main(verbosity=2)
