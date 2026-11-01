import copy,hashlib,json,time,unittest
from pathlib import Path
from unittest.mock import patch
from human_eye_plugin import mesh_structure as raw,surface_geometry as g
from human_eye_plugin.surface_task_service import consume_packet,query
from human_eye_plugin.surface_reference import ReferenceRegistry,ReferenceIntent
from human_eye_plugin.forward_deadline import counter_descriptor
from human_eye_plugin.blender_host import _RAW_MESH_SHA256
from verification import test_structure_task as setup
from verification.test_surface_geometry import prepared


class SurfaceHost:
    def __init__(self):
        self.p=prepared([[0,0,0],[1,0,0],[0,1,0],[0,0,0],[-1,0,0],[0,-1,0]],[[0,1,2],[3,4,5]])
        self.triangles=self.p['raw']['polygons'];self.calls=0;self.mutation=None

    def capture_scene(self):raise AssertionError('surface task must not rigid-capture another object')
    def apply_transform(self,*a,**kw):raise AssertionError('surface reads never write')

    def surface_geometry_capabilities(self):
        return dict(protocol=g.PROTOCOL,helper_sha256=hashlib.sha256(Path(g.__file__).read_bytes()).hexdigest(),raw_helper_sha256=_RAW_MESH_SHA256,
            limits=g.LIMITS,clock=counter_descriptor(),read_only=True,execution_authority=False,images=False)

    def observe_surface_geometry(self,request_id,object_id,deadline_ns,near_m):
        self.calls+=1;p=copy.deepcopy(self.p)
        value=dict(schema=g.PROTOCOL,request_id=request_id,source=p['source'],raw=p['raw'],triangles=self.triangles,
            triangle_polygons=[0,1],diagnostic=g.analyze(p,self.triangles,[0,1],budget=raw.WorkBudget(deadline_ns=deadline_ns),near_m=near_m))
        if self.mutation:self.mutation(value)
        return value

    def capture_surface_source(self,request_id,object_id,deadline_ns):
        value=self.observe_surface_geometry(request_id,object_id,deadline_ns,0)
        del value['diagnostic'];return value


class SurfaceConsumerTests(unittest.TestCase):
    def test_source_report_request_target_and_bounds_mutations_rejected(self):
        host=SurfaceHost();p,packet,report=consume_packet(host,'target',time.perf_counter_ns()+2_000_000_000,.00001)
        self.assertEqual(report['total'],1)
        changes=[lambda v:v.__setitem__('request_id','wrong'),lambda v:v['source'].__setitem__('object_id','wrong'),
            lambda v:v['raw']['vertices'][0].__setitem__(0,.1),lambda v:v['diagnostic'].__setitem__('total',0),
            lambda v:v['triangle_polygons'].__setitem__(0,1),lambda v:v['diagnostic'].__setitem__('scan_complete',False)]
        for change in changes:
            host.mutation=change
            with self.assertRaises(ValueError):consume_packet(host,'target',time.perf_counter_ns()+2_000_000_000,.00001)

    def test_expired_deadline(self):
        with self.assertRaises(ValueError):consume_packet(SurfaceHost(),'target',time.perf_counter_ns()-1,.00001)

    def test_query_no_authority_extra_reference_or_unbounded_indices(self):
        base=dict(mode='mesh_surface',operation='diagnose',request_id='a')
        for patch_value in ({'approved':True},{'near_m':float('nan')},{'near_m':True},{'reference_ref':'a'*32},{'indices':[1]}):
            with self.assertRaises(ValueError):query(dict(base,**patch_value))
        for indices in ([1,1],[True],list(range(65))):
            with self.assertRaises(ValueError):query(dict(base,operation='restore_preview',reference_ref='a'*32,indices=indices))


class SurfaceTaskTests(unittest.TestCase):
    setUp=setup.StructureTaskTests.setUp
    register=setup.StructureTaskTests.register
    state=setup.StructureTaskTests.state

    def enable(self):
        self.host=SurfaceHost();self.service.host=self.host;self.service.config['surface_diagnostics_enabled']=True

    def call(self,request,images=False,**fields):
        value=dict(mode='mesh_surface',operation='diagnose',request_id=request);value.update(fields)
        response=self.server.handle_jsonrpc_message(dict(jsonrpc='2.0',id=request,method='tools/call',
            params=dict(name='human_eye_scene_observe',arguments=dict(query=value,include_image=images,focal_id='target'))))['result']
        return json.loads(response['content'][0]['text']),response

    def test_default_opt_in_and_images_refused_before_host(self):
        self.register();self.enable();self.service.config['surface_diagnostics_enabled']=False
        value,response=self.call('a');self.assertTrue(response['isError']);self.assertEqual(self.host.calls,0)
        self.service.config['surface_diagnostics_enabled']=True
        value,response=self.call('b',images=True);self.assertTrue(response['isError']);self.assertEqual(self.host.calls,0)

    def test_registered_budget_duplicate_receipt_and_projection(self):
        self.register();self.enable();value,response=self.call('a')
        self.assertFalse(response['isError']);self.assertEqual(value['diagnostic']['total'],1)
        self.assertNotIn('pair_goal',value)
        self.assertFalse(value['execution_authority']);self.assertEqual(value['task_budget']['spent']['queries'],1)
        again,response=self.call('a');self.assertEqual(again['status'],'receipt');self.assertFalse(response['isError'])
        self.assertNotIn('diagnostic',again);self.assertEqual(self.host.calls,1)
        for i in range(5):self.call('more'+str(i))
        _,response=self.call('over');self.assertTrue(response['isError']);self.assertEqual(self.host.calls,6)

    def test_no_reference_never_infers_damage(self):
        self.register();self.enable();value,_=self.call('a',operation='reference',reference_ref='a'*32)
        self.assertEqual(value['status'],'unavailable');self.assertIn('trusted_reference_required',value['reason'])

    def test_trusted_registry_read_only_reference_and_preview(self):
        self.register();self.enable();registry=ReferenceRegistry();self.service._surface_references=registry
        ref=registry.bind(self.host.p,self.host.p,self.host.triangles,[0,1],intent=ReferenceIntent('owned','same intended shape','same_index_from_owned_copy'))
        value,_=self.call('a',operation='reference',reference_ref=ref)
        self.assertEqual(value['diagnostic']['changed_count'],0)
        value,response=self.call('b',operation='restore_preview',reference_ref=ref,indices=[0])
        self.assertFalse(response['isError'])
        self.assertEqual(value['diagnostic']['status'],'preview_only');self.assertFalse(value['diagnostic']['execution_authority'])
        registry.revoke(ref);value,_=self.call('c',operation='reference',reference_ref=ref)
        self.assertIn('revoked',value['reason'])

    def test_projection_cannot_publish_late_or_undercharged_surface_facts(self):
        from human_eye_plugin.live_spatial_mcp import _tool_result
        self.register();self.enable();value,_=self.call('a')
        value['accounted_public_text_bytes']=1
        with self.assertRaises(ValueError):_tool_result(value,is_error=False)
        value['accounted_public_text_bytes']=96*1024
        value['task_budget']['deadline_ns']=time.perf_counter_ns()-1
        with self.assertRaises(ValueError):_tool_result(value,is_error=False)


if __name__=='__main__':unittest.main()
