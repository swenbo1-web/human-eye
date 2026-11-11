"""Directed selected-geometry contracts over actual kernels and finite hosts.

The parent runner supplies a verified physical product package. Geometry truth
comes from independently retained raw coordinates, matrices and loop triangles.
No Blender process, model consumer, socket or external service is required.
"""
import copy
from contextlib import ExitStack
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from human_eye_plugin import blender_host, live_service, live_spatial_mcp as mcp, task_query
from human_eye_plugin.runtime_identity import runtime_identity
from verification.arch_read_context_001.test_resident_task import TokenSelectedHost
from verification.test_concave_geometry import box, entity
from verification import test_blender_host_contracts as base_rna
from verification.arch_resident_001 import test_residency_contract as resident

PRODUCT_ROLE=globals().get('PRODUCT_ROLE','candidate')
RUNTIME_SOURCE_SHA256=globals().get('RUNTIME_SOURCE_SHA256',runtime_identity()['source_sha256'])
ROOT=Path(__file__).resolve().parents[3]
EVIDENCE={}
TOOL='human_eye_spatial_relations'


def encoded(value):
    return json.dumps(value,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode('utf8')


def core(value):
    return {key:copy.deepcopy(item) for key,item in value.items() if key not in ('trace_id','geometry')}


class RNAHostAdapter:
    timeout_s=10.

    def __init__(self,backend):
        self.backend=backend
        self.selected_calls=[]
        self.calls=0
        self.last_capture=None

    def capture_task_scene(self,selectors):
        self.selected_calls.append(copy.deepcopy(selectors))
        self.last_capture=self.backend.capture_task_scene(selectors)
        return self.last_capture

    def apply_transform(self,*args,**kwargs):
        self.calls+=1
        raise AssertionError('selected geometry attempted a product write')


class SelectedGeometryTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory(prefix='selected-geometry-')
        self.addCleanup(self.temporary.cleanup)
        self.folder=Path(self.temporary.name)
        self.serial=0

    def service(self,host):
        self.serial+=1
        path=self.folder/('config_'+str(self.serial)+'.json')
        path.write_text(json.dumps({'schema_version':'1.0','enabled':True,'project_root':str(ROOT),
          'state_file':'state_'+str(self.serial)+'.json','audit_file':'audit_'+str(self.serial)+'.jsonl','quad_size':64}),encoding='utf8')
        service=live_service.LiveSpatialService(path,host=host)
        return service,mcp.LiveSpatialMCPServer(service,default_session_id='selected-evidence-default',spatial_task_only=True)

    def rna(self,scale=0.125):
        # Existing RNA fixture functions call the exact guarded host class.
        resident.Host=blender_host.BlenderSceneHost
        resident.fixture.BlenderSceneHost=blender_host.BlenderSceneHost
        resident.fixture.BlenderHostError=blender_host.BlenderHostError
        resident.fixture._module=blender_host
        backend,focal,reference,graph=resident.make_host()
        self.addCleanup(backend.close_residency)
        backend.bpy.app.driver_namespace.update({'_human_eye_document_epoch_v1':'b'*32,
          '_human_eye_residency_document_v1':'c'*32})
        backend.scene.unit_settings.scale_length=scale
        focal._matrix_world=base_rna.FakeMatrix([[0.,-1.,0.,0.125],[1.,0.,0.,-0.25],[0.,0.,1.,0.5],[0.,0.,0.,1.]])
        adapter=RNAHostAdapter(backend)
        service,server=self.service(adapter)
        return adapter,service,server,focal,reference,graph

    @staticmethod
    def args(target='a',candidates=('b','c','d')):
        return {'target':{'id':target},'candidates':[{'id':value} for value in candidates]}

    def call(self,label,service,server,host,args):
        arguments=copy.deepcopy(args)
        capture_before=len(host.selected_calls)
        backend=getattr(host,'backend',None)
        work_before=backend.residency_work() if backend is not None else None
        with ExitStack() as stack:
            counters={}
            for owner,name in ((task_query,'task_result'),(task_query,'classify_closed_solids'),
                    (task_query,'measure_surface_proximity'),(live_service,'_validated_scene')):
                counters[name]=stack.enter_context(patch.object(owner,name,wraps=getattr(owner,name)))
            projection=None
            if hasattr(task_query,'project_task_geometry'):
                projection=stack.enter_context(patch.object(task_query,'project_task_geometry',wraps=task_query.project_task_geometry))
            wire=server._call_tool(TOOL,arguments)
        self.assertEqual(arguments,args)
        self.assertFalse(wire['isError'])
        self.assertEqual(len(wire['content']),1)
        result=json.loads(wire['content'][0]['text'])
        self.assertEqual(result['context']['runtime_source_sha256'],RUNTIME_SOURCE_SHA256)
        capture_count=len(host.selected_calls)-capture_before
        self.assertEqual(capture_count,1)
        counts={name:value.call_count for name,value in counters.items()}
        counts.update(capture=capture_count,host_writes=host.calls,
          geometry_projection=0 if projection is None else projection.call_count)
        self.assertEqual(host.calls,0)
        delta=None
        if backend is not None:
            work_after=backend.residency_work()
            delta={key:work_after[key]-work_before[key] for key in
              ('to_mesh','triangulations','resource_builds','world_transforms','capture_cache_hits')}
        logs=[json.loads(line) for line in service.audit_path.read_text('utf8').splitlines()]
        diagnostic=[row['task_work'] for row in logs if row.get('event')=='observe'][-1]
        EVIDENCE[label]={'arguments':copy.deepcopy(args),'result':result,'core':core(result),
          'counts':counts,'residency_delta':delta,'diagnostics':diagnostic,
          'raw_tool_result':wire,'serialized_response_bytes':len(encoded(wire)),
          'capture_selectors':copy.deepcopy(host.selected_calls[-1]),
          'offline_RPC_count':0,'scope':'offline RNA/memory host; actual RPC is measured separately at the installed entry'}
        return result,counts,delta

    def assert_source_geometry(self,row,obj,scale,triangles):
        # Signed permutation + dyadic translation/scale yields exact rational
        # results, independently of the product's float forward-map code.
        matrix=[[Fraction(float(value)) for value in values] for values in obj.matrix_world]
        expected=[[float((sum(matrix[r][c]*Fraction(float(vertex.co[c])) for c in range(3))+matrix[r][3])*Fraction(float(scale)))
          for r in range(3)] for vertex in obj.data.vertices]
        self.assertEqual(row['vertices_world'],expected)
        if triangles:
            self.assertEqual(row['triangles'],[list(triangle.vertices) for triangle in obj.data.loop_triangles])
        else:self.assertNotIn('triangles',row)
        self.assertEqual(row['name'],obj.name)
        EVIDENCE.setdefault('independent_source_oracles',{})[obj.name]={
          'vertices_local':[list(vertex.co) for vertex in obj.data.vertices],
          'matrix_world':[list(values) for values in obj.matrix_world],'unit_scale_m':scale,
          'actual_loop_triangle_order':[list(triangle.vertices) for triangle in obj.data.loop_triangles],
          'expected_vertices_world':expected}

    def test_default_has_no_geometry_or_projection_work(self):
        host,service,server,focal,reference,_=self.rna()
        args={'target':{'name':focal.name},'candidates':[{'name':reference.name}]}
        if PRODUCT_ROLE=='candidate':
            with patch.object(task_query,'project_task_geometry',side_effect=AssertionError('default geometry projection')):
                result,counts,delta=self.call('default_cold',service,server,host,args)
        else:result,counts,delta=self.call('default_cold',service,server,host,args)
        self.assertNotIn('geometry',result)
        self.assertEqual(counts['classify_closed_solids'],1)
        self.assertEqual(counts['measure_surface_proximity'],1)
        self.assertEqual(delta['to_mesh'],2)
        self.assertEqual(delta['triangulations'],2)
        self.assertEqual(delta['world_transforms'],2)
        warm,counts,delta=self.call('default_warm',service,server,host,args)
        self.assertEqual(core(warm),core(result))
        self.assertEqual((counts['task_result'],counts['classify_closed_solids'],counts['measure_surface_proximity']),(0,0,0))
        self.assertEqual([delta[key] for key in ('to_mesh','triangulations','world_transforms')],[0,0,0])

    @unittest.skipIf(PRODUCT_ROLE=='baseline','new geometry display option is candidate-only')
    def test_vertices_triangles_subsets_order_and_unit_use_actual_capture(self):
        host,service,server,focal,reference,_=self.rna()
        base={'target':{'name':focal.name},'candidates':[{'name':reference.name}]}
        selectors=[{'name':reference.name},{'id':host.backend.object_id(focal)},{'name':reference.name}]
        arguments=dict(base,geometry={'objects':selectors})
        result,_,_=self.call('vertices_alias_repeat',service,server,host,arguments)
        objects=result['geometry']['objects']
        self.assertEqual([row['name'] for row in objects],[reference.name,focal.name,reference.name])
        self.assertEqual(objects[0],objects[2])
        for row,obj in zip(objects,(reference,focal,reference)):
            self.assert_source_geometry(row,obj,0.125,False)
        triangles,counts,delta=self.call('triangles_toggle',service,server,host,
          dict(base,geometry={'objects':[{'name':focal.name}],'include_triangles':True}))
        self.assertEqual(len(triangles['geometry']['objects']),1)
        self.assert_source_geometry(triangles['geometry']['objects'][0],focal,0.125,True)
        self.assertEqual(core(triangles),core(result))
        self.assertEqual((counts['task_result'],counts['classify_closed_solids'],counts['measure_surface_proximity']),(0,0,0))
        self.assertEqual([delta[key] for key in ('to_mesh','triangulations','world_transforms')],[0,0,0])
        self.assertEqual(triangles['context']['unit'],'m')
        self.assertEqual(triangles['context']['coordinate_frame'],'world')
        self.assertEqual(triangles['geometry']['contract']['vertices_world'],'current_evaluated_vertices_world_metres_in_captured_order')
        self.assertEqual(triangles['geometry']['contract']['triangles'],'zero_based_triplets_index_vertices_world_in_captured_order')

    @unittest.skipIf(PRODUCT_ROLE=='baseline','new geometry display option is candidate-only')
    def test_same_generation_display_toggle_is_detached_from_relation_cache(self):
        host,service,server,focal,reference,_=self.rna()
        base={'target':{'name':focal.name},'candidates':[{'name':reference.name}]}
        off,_,_=self.call('toggle_off_cold',service,server,host,base)
        for index,include in enumerate((False,True,False)):
            arguments=dict(base,geometry={'objects':[{'name':focal.name}],'include_triangles':include})
            current,counts,delta=self.call('toggle_on_'+str(index),service,server,host,arguments)
            self.assertEqual(core(current),core(off))
            self.assertEqual((counts['task_result'],counts['classify_closed_solids'],counts['measure_surface_proximity']),(0,0,0))
            self.assertEqual([delta[key] for key in ('to_mesh','triangulations','world_transforms')],[0,0,0])
            current['geometry']['objects'][0]['vertices_world'][0][0]=123456.
        default,counts,_=self.call('toggle_off_again',service,server,host,base)
        self.assertEqual(core(default),core(off));self.assertNotIn('geometry',default)
        self.assertEqual(counts['geometry_projection'],0)
        restored,_,_=self.call('toggle_after_caller_mutation',service,server,host,
          dict(base,geometry={'objects':[{'name':focal.name}]}))
        self.assert_source_geometry(restored['geometry']['objects'][0],focal,0.125,False)

    @unittest.skipIf(PRODUCT_ROLE=='baseline','new geometry display option is candidate-only')
    def test_cold_display_has_same_existing_work_as_cold_default(self):
        off_host,off_service,off_server,focal,reference,_=self.rna()
        base={'target':{'name':focal.name},'candidates':[{'name':reference.name}]}
        off,off_counts,off_delta=self.call('paired_cold_off',off_service,off_server,off_host,base)
        on_host,on_service,on_server,focal,_,_=self.rna()
        on,on_counts,on_delta=self.call('paired_cold_on',on_service,on_server,on_host,
          dict(base,geometry={'objects':[{'name':focal.name}],'include_triangles':True}))
        self.assertEqual(core(on),core(off))
        self.assertEqual({k:v for k,v in on_counts.items() if k!='geometry_projection'},
          {k:v for k,v in off_counts.items() if k!='geometry_projection'})
        self.assertEqual(on_delta,off_delta)

    @unittest.skipIf(PRODUCT_ROLE=='baseline','new geometry display option is candidate-only')
    def test_exact_unresolved_selector_precedes_successful_alias(self):
        host=TokenSelectedHost()
        host.scene['meshes'][0]['name']='dup'
        host.scene['meshes'][1]['name']='dup'
        service,server=self.service(host)
        base={'target':{'id':'a'},'candidates':[{'name':'dup'}]}
        arguments=dict(base,geometry={'objects':[{'name':'dup'},{'id':'a'}],'include_triangles':True})
        result,_,_=self.call('exact_unresolved_before_alias',service,server,host,arguments)
        unresolved=result['geometry']['objects'][0]
        self.assertEqual(unresolved,{'selector':{'name':'dup'},'status':'unknown','reason':'object_name_ambiguous'})
        self.assertEqual(result['geometry']['objects'][1]['object_id'],'a')
        self.assertEqual(result['candidates'][0]['reason'],'object_name_ambiguous')
        self.assertEqual(result['candidates'][0]['closed_solid_relation']['status'],'unknown')
        self.assertEqual(host.selected_calls[-1],[{'id':'a'},{'name':'dup'}])

    @unittest.skipIf(PRODUCT_ROLE=='baseline','new geometry display option is candidate-only')
    def test_identity_dedup_keeps_repeats_but_not_distinct_same_names(self):
        host=TokenSelectedHost();service,server=self.service(host)
        base={'target':{'id':'a'},'candidates':[{'id':'b'},{'name':'b'}]}
        result,_,_=self.call('same_identity_alias_dedup',service,server,host,
          dict(base,geometry={'objects':[{'name':'b'},{'id':'b'},{'name':'b'}]}))
        rows=result['geometry']['objects']
        self.assertEqual(len(rows),3)
        self.assertTrue(all(row['object_id']=='b' for row in rows));self.assertEqual(rows[0],rows[2])
        self.assertTrue(all(row['closed_solid_relation']['status']=='unknown' for row in result['candidates']))
        host=TokenSelectedHost();host.scene['meshes'][1]['name']='dup';host.scene['meshes'][2]['name']='dup'
        service,server=self.service(host)
        result,_,_=self.call('distinct_IDs_same_name',service,server,host,
          dict(self.args(),geometry={'objects':[{'name':'dup'},{'id':'b'},{'id':'c'}]}))
        rows=result['geometry']['objects']
        self.assertEqual(rows[0],{'selector':{'name':'dup'},'status':'unknown','reason':'object_name_ambiguous'})
        self.assertEqual([row['object_id'] for row in rows[1:]],['b','c'])

    @unittest.skipIf(PRODUCT_ROLE=='baseline','new geometry display option is candidate-only')
    def test_missing_selector_and_unknown_relation_keep_their_existing_reasons(self):
        host=TokenSelectedHost();service,server=self.service(host)
        result,_,_=self.call('original_missing_binding',service,server,host,
          dict(self.args(candidates=('missing',)),geometry={'objects':[{'id':'missing'},{'id':'a'}]}))
        self.assertEqual(result['geometry']['objects'][0],{'selector':{'id':'missing'},'status':'unknown','reason':'object_not_found'})
        self.assertEqual(result['candidates'][0]['closed_solid_relation']['status'],'unknown')
        host=TokenSelectedHost()
        original=box((0,0,0),(2,2,2),'a')
        host.scene['meshes'][0]=entity('a',original.vertices,original.faces[:-1]).to_dict()
        service,server=self.service(host)
        result,_,_=self.call('open_shell_geometry_known_relation_unknown',service,server,host,
          dict(self.args(candidates=('b',)),geometry={'objects':[{'id':'a'}],'include_triangles':True}))
        self.assertEqual(result['candidates'][0]['closed_solid_relation']['status'],'unknown')
        self.assertEqual(result['geometry']['objects'][0]['triangles'],original.faces[:-1].tolist())

    @unittest.skipIf(PRODUCT_ROLE=='baseline','new geometry display option is candidate-only')
    def test_invalid_options_reject_before_capture_and_outside_does_not_expand(self):
        host=TokenSelectedHost();service,server=self.service(host)
        bad=(None,{},[],{'objects':[]},{'objects':[{'id':'a'}],'include_triangles':0},
          {'objects':[{'id':'a'}],'extra':1},{'objects':[{'id':'a','name':'a'}]},
          {'objects':[{'id':'a'}]*5})
        for value in bad:
            with self.subTest(geometry=value):
                before=len(host.selected_calls)
                with self.assertRaises(ValueError):server._call_tool(TOOL,dict(self.args(),geometry=value))
                self.assertEqual(len(host.selected_calls),before)
        before=len(host.selected_calls)
        with self.assertRaisesRegex(ValueError,'[Oo]utside'):
            server._call_tool(TOOL,dict(self.args(candidates=('b',)),geometry={'objects':[{'id':'c'}]}))
        self.assertEqual(len(host.selected_calls)-before,1)
        self.assertEqual(host.selected_calls[-1],[{'id':'a'},{'id':'b'}])

    @unittest.skipIf(PRODUCT_ROLE=='baseline','new geometry display option is candidate-only')
    def test_pose_and_geometry_changes_refresh_evidence_and_relation_binding(self):
        host,service,server,focal,reference,graph=self.rna()
        base={'target':{'name':focal.name},'candidates':[{'name':reference.name}],
          'geometry':{'objects':[{'name':focal.name}],'include_triangles':True}}
        first,_,_=self.call('source_initial',service,server,host,base)
        focal._matrix_world[0][3]+=0.375
        moved,counts,delta=self.call('source_pose_changed',service,server,host,base)
        self.assertNotEqual(first['context']['scene_fingerprint'],moved['context']['scene_fingerprint'])
        self.assertNotEqual(first['geometry']['objects'][0]['vertices_world'],moved['geometry']['objects'][0]['vertices_world'])
        self.assertEqual(counts['classify_closed_solids'],1)
        self.assertEqual((delta['to_mesh'],delta['triangulations'],delta['world_transforms']),(0,0,1))
        self.assert_source_geometry(moved['geometry']['objects'][0],focal,0.125,True)
        focal.data.vertices[0].co=(0.25,0.,0.)
        resident.notify_geometry(host.backend,graph,focal,via_data=True)
        changed,counts,delta=self.call('source_geometry_changed',service,server,host,base)
        self.assertNotEqual(changed['context']['scene_fingerprint'],moved['context']['scene_fingerprint'])
        self.assertEqual(counts['classify_closed_solids'],1)
        self.assertEqual((delta['to_mesh'],delta['triangulations'],delta['world_transforms']),(1,1,1))
        self.assert_source_geometry(changed['geometry']['objects'][0],focal,0.125,True)

