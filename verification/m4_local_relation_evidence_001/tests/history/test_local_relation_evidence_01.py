"""Finite real-kernel checks; independent Fraction oracle, no model/Blender.

The root runs this same QA source under both guarded physical product copies.
Only assertions for the newly introduced local_evidence are role-conditional.
The old core, complete diagnostics and direct operation counts remain exported.
"""
import copy
from collections import Counter
from contextlib import ExitStack
from fractions import Fraction as Q
import hashlib
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from human_eye_plugin import surface_geometry as closed, surface_proximity as exact
from human_eye_plugin import task_query as task, live_service as service_module, live_spatial_mcp as mcp
from human_eye_plugin.runtime_identity import runtime_identity
from verification.test_concave_geometry import entity, box
from verification.test_live_service import SelfLockingHost

PRODUCT_ROLE = globals().get('PRODUCT_ROLE', 'candidate')
ROOT = Path(__file__).resolve().parents[3]
SPEC_PATH = Path(__file__).resolve().parent/'fixtures/SOURCE_AND_TETRA_SPEC.json'
EVIDENCE = {}
TOLERANCE = Q.from_float(1e-9)
TRIANGLE_SCOPE = 'current_capture_zero_based_triangles_target_then_candidate_not_polygon_ids'
POINT_SCOPE = 'boundary_crossing_localization_not_volume_interior_or_penetration_depth'


def serialized(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf8')


def stripped(value):
    """Remove the one new fact only, plus root request trace; no binding scrub."""
    result = copy.deepcopy(value)
    result.pop('trace_id', None)
    result.pop('local_evidence', None)
    if isinstance(result.get('facts'), dict):
        result['facts'].get('closed_solid_relation', {}).pop('local_evidence', None)
    for pair in result.get('pairs', []):
        pair.get('facts', {}).get('closed_solid_relation', {}).pop('local_evidence', None)
    for row in result.get('candidates', []):
        row.get('closed_solid_relation', {}).pop('local_evidence', None)
    return result


def fpoint(point): return tuple(Q.from_float(float(value)) for value in point)
def add(a,b): return tuple(x+y for x,y in zip(a,b))
def sub(a,b): return tuple(x-y for x,y in zip(a,b))
def mul(a,t): return tuple(x*t for x in a)
def dot(a,b): return sum(x*y for x,y in zip(a,b))
def cross(a,b): return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])
def normal(t): return cross(sub(t[1],t[0]),sub(t[2],t[0]))


def barycentric(point, triangle):
    """Independent Gram-system solve plus exact coplanarity, no product calls."""
    u,v,w = sub(triangle[1],triangle[0]),sub(triangle[2],triangle[0]),sub(point,triangle[0])
    if dot(cross(u,v),w): return None
    uu,uv,vv,uw,vw = dot(u,u),dot(u,v),dot(v,v),dot(u,w),dot(v,w)
    den = uu*vv-uv*uv
    if den <= 0: return None
    s,t = (uw*vv-vw*uv)/den,(vw*uu-uw*uv)/den
    return (1-s-t,s,t)


def independent_crossing(a,b):
    """Plane-slice interval intersection and strict relative-interior midpoint."""
    na,nb=normal(a),normal(b)
    axis=cross(na,nb)
    if not any(axis): return None
    def cut(triangle,n,origin):
        distances=[dot(n,sub(point,origin)) for point in triangle]
        points=[point for point,d in zip(triangle,distances) if d==0]
        for i in range(3):
            j=(i+1)%3
            if distances[i]*distances[j]<0:
                t=distances[i]/(distances[i]-distances[j])
                points.append(add(triangle[i],mul(sub(triangle[j],triangle[i]),t)))
        return list(dict.fromkeys(points))
    left,right=cut(a,nb,b[0]),cut(b,na,a[0])
    if len(left)<2 or len(right)<2: return None
    k=max(range(3),key=lambda k:abs(axis[k]))
    left.sort(key=lambda p:p[k]);right.sort(key=lambda p:p[k])
    low=max(left[0][k],right[0][k]);high=min(left[-1][k],right[-1][k])
    if low>=high:return None
    direction=sub(left[-1],left[0])
    endpoints=[add(left[0],mul(direction,(value-left[0][k])/direction[k])) for value in (low,high)]
    middle=mul(add(*endpoints),Q(1,2))
    ba,bb=barycentric(middle,a),barycentric(middle,b)
    if ba is None or bb is None or min(*ba,*bb)<=0:return None
    return {'segment':endpoints,'middle':middle,'barycentric':[ba,bb]}


def rational_json(value):
    if isinstance(value,Q):return str(value)
    if isinstance(value,(tuple,list)):return [rational_json(item) for item in value]
    if isinstance(value,dict):return {key:rational_json(item) for key,item in value.items()}
    return value


def frozen_pair():
    spec=json.loads(SPEC_PATH.read_bytes())['source']
    raw=(ROOT/spec['path']).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=spec['sha256']:raise AssertionError('frozen actual world source changed')
    data=json.loads(raw)
    if data['unit']!='m' or data['coordinate_frame']!='world':raise AssertionError('frozen metric contract changed')
    rows={obj['name']:obj for obj in data['objects']}
    return tuple(entity(name,rows[name]['world_vertices'],rows[name]['triangles']) for name in spec['objects'])


def tetra_pair(shift=0):
    spec=json.loads(SPEC_PATH.read_bytes())['synthetic_tetra']
    return tuple(entity(name,np.asarray(spec[key],float)+shift,spec['faces'])
        for name,key in (('tetra-target','left_vertices'),('tetra-candidate','right_vertices')))


def transformed(mesh,rotation=None,shift=(0,0,0)):
    rotation=np.eye(3) if rotation is None else np.asarray(rotation,float)
    return entity(mesh.object_id,mesh.vertices@rotation.T+np.asarray(shift),mesh.faces)


class WorkSpy:
    """Observe actual calls/loop yields; never replace their computed results."""
    def __enter__(self):
        self.stack=ExitStack();self.counts=Counter();self.stages=Counter();self.amounts=Counter();self.versions=[]
        for owner,name,label in ((closed,'classify_closed_solids','kernel'),(task,'classify_closed_solids','kernel'),
                (task,'_closed_solid_pair_measurement','pair'),(exact,'_intersection','intersection'),
                (closed,'_closed_in_triangle','point_in_triangle'),(closed,'_closed_location','point_in_solid'),
                (closed,'_closed_transverse','transverse'),(task,'measure_surface_proximity','surface_kernel')):
            original=getattr(owner,name)
            def wrapped(*args,_original=original,_label=label,**kwargs):
                self.counts[_label]+=1
                return _original(*args,**kwargs)
            self.stack.enter_context(patch.object(owner,name,side_effect=wrapped))
        original=closed.candidate_pairs
        def pairs(*args,**kwargs):
            kind='cross' if kwargs.get('other_bounds') is not None else 'self'
            self.counts[kind+'_iterator']+=1
            for pair in original(*args,**kwargs):
                self.counts[kind+'_yield']+=1
                yield pair
        self.stack.enter_context(patch.object(closed,'candidate_pairs',side_effect=pairs))
        original_consume=closed._ClosedWork.consume
        def consume(budget,amount,stage):
            self.stages[stage]+=1;self.amounts[stage]+=amount
            return original_consume(budget,amount,stage)
        self.stack.enter_context(patch.object(closed._ClosedWork,'consume',consume))
        from human_eye_plugin.scene_cache import SpatialSceneCache
        original_pair=SpatialSceneCache.pair_measurement
        def cache_pair(cache,*args,**kwargs):
            self.versions.append(kwargs['algorithm_version'])
            return original_pair(cache,*args,**kwargs)
        self.stack.enter_context(patch.object(SpatialSceneCache,'pair_measurement',cache_pair))
        return self
    def __exit__(self,*args):return self.stack.__exit__(*args)
    def evidence(self):
        names=('kernel','pair','intersection','point_in_triangle','point_in_solid','transverse',
            'surface_kernel','self_iterator','self_yield','cross_iterator','cross_yield')
        return {'calls':{name:self.counts[name] for name in names},'loop_counts':dict(self.stages),
            'loop_work_amounts':dict(self.amounts),'cache_algorithm_versions':self.versions}


class LocalRelationEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory(prefix='m4-local-relation-')
        self.addCleanup(self.temporary.cleanup)
        self.folder=Path(self.temporary.name);self.serial=0

    def record(self,case,result,meshes,spy,diagnostics=None,**extra):
        EVIDENCE[case]={'input':[mesh.to_dict() for mesh in meshes], 'result':copy.deepcopy(result),
            'core':stripped(result),'diagnostics':copy.deepcopy(diagnostics),**spy.evidence(),
            'raw_json':serialized(result).decode('utf8'),'serialized_bytes':len(serialized(result)),**extra}

    def assert_local(self,result,left,right,*,point='approximate'):
        self.assertTrue(result['measurement_valid']);self.assertEqual(result['relation'],'penetrating')
        self.assertEqual(result['certificate'],'transverse_boundary_interiors')
        if PRODUCT_ROLE=='baseline':
            self.assertNotIn('local_evidence',result)
            return None
        evidence=result['local_evidence']
        self.assertEqual(evidence['type'],'transverse_triangle_crossing')
        self.assertEqual(evidence['triangle_scope'],TRIANGLE_SCOPE)
        self.assertEqual(evidence['point_scope'],POINT_SCOPE)
        self.assertEqual(evidence['publication_tolerance_m'],1e-9)
        indices=evidence['triangle_indices']
        self.assertEqual(len(indices),2)
        triangles=[]
        for mesh,index,reported in zip((left,right),indices,evidence['triangle_vertices_world_m']):
            self.assertIs(type(index),int);self.assertGreaterEqual(index,0);self.assertLess(index,len(mesh.faces))
            expected=mesh.vertices[mesh.faces[index]].tolist()
            self.assertEqual(reported,expected)
            triangles.append(tuple(map(fpoint,expected)))
        proof=independent_crossing(*triangles)
        self.assertIsNotNone(proof,'returned pair is not an independently certified transverse segment')
        self.assertEqual(evidence['point_status'],point)
        middle=proof['middle']
        squared_error=sum((Q.from_float(float(value))-value)**2 for value in middle)
        if point=='approximate':
            self.assertIsInstance(evidence['point_world_m'],list)
            published=fpoint(evidence['point_world_m'])
            self.assertLessEqual(sum((a-b)**2 for a,b in zip(published,middle)),TOLERANCE*TOLERANCE)
            self.assertLessEqual(squared_error,TOLERANCE*TOLERANCE)
            self.assertNotIn('point_reason',evidence)
        else:
            self.assertIsNone(evidence['point_world_m'])
            self.assertEqual(evidence['point_reason'],'world_point_precision_exceeded')
            self.assertGreater(squared_error,TOLERANCE*TOLERANCE)
        return rational_json(proof)

    def measure(self,case,left,right,*,holder=None):
        diagnostic={};stages=[]
        with WorkSpy() as spy:
            result=closed.classify_closed_solids(left,right,stages.append,
                diagnostics=diagnostic,prepared_holder=holder)
        self.assertEqual(spy.counts['kernel'],1)
        self.record(case,result,(left,right),spy,diagnostic,checkpoint_counts=dict(Counter(stages)))
        return result

    def test_frozen_actual_pair_swap_and_rigid_transform(self):
        left,right=frozen_pair()
        rotation=((0,-1,0),(0,0,1),(-1,0,0));shift=(8,-16,32)
        variants=(('frozen',left,right),('frozen_swapped',right,left),
            ('frozen_rigid',transformed(left,rotation,shift),transformed(right,rotation,shift)))
        for case,a,b in variants:
            with self.subTest(case=case):
                result=self.measure(case,a,b)
                EVIDENCE[case]['independent_local_proof']=self.assert_local(result,a,b)

    def test_first_contact_is_not_the_final_transverse_witness(self):
        left,right=tetra_pair();holder={}
        # The first two bottom triangles have a common strict planar point.
        for mesh in (left,right):
            tri=tuple(map(fpoint,mesh.vertices[mesh.faces[0]]))
            self.assertTrue(all(v>0 for v in barycentric((Q(3,2),Q(3,2),Q(0)),tri)))
        result=self.measure('contact_then_transverse',left,right,holder=holder)
        self.assertEqual(list(holder['boundary_contact']['triangles']),[0,0])
        self.assertFalse(any(cross(normal(tuple(map(fpoint,left.vertices[left.faces[0]]))),
            normal(tuple(map(fpoint,right.vertices[right.faces[0]]))))))
        proof=self.assert_local(result,left,right)
        if PRODUCT_ROLE!='baseline':
            self.assertEqual(result['local_evidence']['triangle_indices'],[3,1])
            self.assertEqual(proof['middle'],['11/5','1','4/5'])
        EVIDENCE['contact_then_transverse']['independent_local_proof']=proof
        EVIDENCE['contact_then_transverse']['first_contact_triangle_indices']=[0,0]

    def test_large_translation_retains_surfaces_but_refuses_inaccurate_point(self):
        left,right=tetra_pair(2.**40)
        result=self.measure('large_point_unavailable',left,right)
        EVIDENCE['large_point_unavailable']['independent_local_proof']=self.assert_local(result,left,right,point='unknown')

    def test_nontransverse_classifications_do_not_fabricate_evidence(self):
        left=box((0,0,0),(2,2,2),'target')
        open_mesh=entity('open',left.vertices,left.faces[:-1])
        cases=(('separated',left,box((4,0,0),(2,2,2),'separate'),'separated'),
            ('touching',left,box((2,0,0),(2,2,2),'touch'),'touching'),
            ('contained',box((0,0,0),(4,4,4),'outer'),box((0,0,0),(1,1,1),'inner'),'penetrating'),
            ('open_unknown',open_mesh,box((4,0,0),(2,2,2),'other'),None))
        for case,a,b,relation in cases:
            with self.subTest(case=case):
                result=self.measure(case,a,b)
                self.assertNotIn('local_evidence',result)
                self.assertEqual(result['measurement_valid'],relation is not None)
                self.assertEqual(result['relation'],relation)
                if relation is None:self.assertEqual(result['reason'],'closed_solid_open_nonmanifold_or_orientation')
                elif case=='contained':self.assertNotEqual(result['certificate'],'transverse_boundary_interiors')

    def service(self,left,right):
        self.serial+=1
        config=self.folder/('config_'+str(self.serial)+'.json')
        config.write_text(json.dumps({'schema_version':'1.0','enabled':True,'project_root':str(ROOT),
            'state_file':'state_'+str(self.serial)+'.json','audit_file':'audit_'+str(self.serial)+'.jsonl','quad_size':64}),encoding='utf8')
        host=SelfLockingHost()
        host.scene={'revision':'r1','unit':'m','coordinate_frame':'world','source':'m4_local_frozen_world',
            'meshes':[left.to_dict(),right.to_dict()],
            'capture_state':{'instance_id':'m4-local-evidence-fixed-host','epoch':1,'revision':1,'selection_key':'two-objects'}}
        return service_module.LiveSpatialService(config,host=host),host

    def observe(self,case,service,host,left,right,query=None,entry=None):
        query=query or {'mode':'task','objects':[{'id':left.object_id},{'id':right.object_id}],
            'requested_facts':['closed_solid_relation']}
        captures=host.captures
        with WorkSpy() as spy:
            if entry is None:
                result=service.observe('m4-local-default',query=query,include_image=False);wire=None
            else:
                server=mcp.LiveSpatialMCPServer(service,default_session_id='m4-local-default',spatial_task_only=entry=='compact')
                args=({'target':{'id':left.object_id},'candidates':[{'id':right.object_id}]} if entry=='compact' else
                    {'session_id':'m4-local-default','include_image':False,'query':query})
                original=copy.deepcopy(args)
                wire=server._call_tool('human_eye_spatial_relations' if entry=='compact' else 'human_eye_scene_observe',args)
                self.assertEqual(args,original);self.assertFalse(wire['isError'])
                result=json.loads(wire['content'][0]['text'])
        logs=[json.loads(line) for line in service.audit_path.read_text('utf8').splitlines()]
        diagnostic=[row['task_work'] for row in logs if row.get('event')=='observe'][-1]
        self.assertEqual(host.captures-captures,1);self.assertEqual(host.calls,0)
        self.record(case,result,(left,right),spy,diagnostic,capture_calls=host.captures-captures,
            host_rpc_calls=0,host_write_calls=host.calls,raw_tool_result=wire)
        return result,spy

    def test_cold_warm_geometry_invalidation_and_new_cache_version(self):
        left,right=frozen_pair();service,host=self.service(left,right)
        cold,cold_spy=self.observe('service_cold',service,host,left,right)
        original=copy.deepcopy(cold)
        cold['facts']['closed_solid_relation']['caller_mutation']='must not enter cache'
        if PRODUCT_ROLE!='baseline':cold['facts']['closed_solid_relation']['local_evidence']['triangle_vertices_world_m'][0][0][0]=123456.
        warm,warm_spy=self.observe('service_warm',service,host,left,right)
        self.assertEqual(stripped(warm),stripped(original))
        self.assertEqual(warm['facts'],original['facts'])
        self.assertEqual((cold_spy.counts['kernel'],warm_spy.counts['kernel']),(1,0))
        host.scene['revision']='r2';host.scene['capture_state']['revision']=2
        rebound,rebound_spy=self.observe('service_same_geometry_new_generation',service,host,left,right)
        self.assertEqual(rebound['facts'],original['facts']);self.assertEqual(rebound_spy.counts['kernel'],0)
        self.assertNotEqual(rebound['binding']['scene_fingerprint'],original['binding']['scene_fingerprint'])
        moved=transformed(right,shift=(10,0,0))
        host.scene['meshes'][1]=moved.to_dict();host.scene['revision']='r3';host.scene['capture_state']['revision']=3
        changed,changed_spy=self.observe('service_geometry_changed',service,host,left,moved)
        self.assertEqual(changed_spy.counts['kernel'],1)
        self.assertEqual(changed['facts']['closed_solid_relation']['value'],'separated')
        self.assertNotIn('local_evidence',changed['facts']['closed_solid_relation'])
        expected_version=('task-closed-solid-exact-v1' if PRODUCT_ROLE=='baseline' else
            'task-closed-solid-exact-local-evidence-v2')
        self.assertEqual(cold_spy.versions,[expected_version])
        self.assertEqual(rebound_spy.versions,[expected_version])
        self.assertEqual(changed_spy.versions,[expected_version])

    def test_public_ordinary_and_compact_deliver_same_current_local_evidence(self):
        left,right=frozen_pair()
        query={'mode':'task','target':{'id':left.object_id},'candidates':[{'id':right.object_id}],
            'requested_facts':['closed_solid_relation','surface_proximity']}
        ordinary,host=self.service(left,right)
        full,full_spy=self.observe('public_ordinary',ordinary,host,left,right,query,entry='ordinary')
        compact,host=self.service(left,right)
        brief,brief_spy=self.observe('public_compact',compact,host,left,right,query,entry='compact')
        full_fact=full['pairs'][0]['facts']['closed_solid_relation']
        brief_fact=brief['candidates'][0]['closed_solid_relation']
        self.assertEqual(full_fact['value'],brief_fact['value'])
        self.assertEqual(full_fact.get('local_evidence'),brief_fact.get('local_evidence'))
        if PRODUCT_ROLE!='baseline':
            self.assertIn('local_evidence',full_fact)
            wrapper={'measurement_valid':True,'relation':full_fact['value'],
                'certificate':full_fact['certificate'],'local_evidence':full_fact['local_evidence']}
            EVIDENCE['public_ordinary']['independent_local_proof']=self.assert_local(wrapper,left,right)
        self.assertEqual(full_spy.evidence(),brief_spy.evidence())
        self.assertEqual((full_spy.counts['kernel'],full_spy.counts['surface_kernel']),(1,1))

