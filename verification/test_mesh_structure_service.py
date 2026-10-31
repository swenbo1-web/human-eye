import copy,json,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
from human_eye_plugin import mesh_structure as m
from human_eye_plugin.mesh_structure_service import validate_result
from human_eye_plugin.blender_host import _RAW_MESH_SHA256
from human_eye_plugin.live_service import LiveSpatialService
from human_eye_plugin.live_spatial_mcp import _tool_result,LIVE_MCP_TOOLS_SCHEMA
from verification.test_host_runtime import MutableHost
from verification.test_mesh_structure_runtime import raw_case,identity
from verification.mesh_structure_fixtures import fixtures


class TypedRawHost(MutableHost):
    def __init__(self):super().__init__();self.raw_calls=0;self.bad=None
    def mesh_structure_capabilities(self):
        return dict(protocol=m.PROTOCOL,supported_categories=list(m.SUPPORTED),helper_sha256=_RAW_MESH_SHA256,
                    clock={'test_clock':True},read_only=True,execution_authority=False,images=False)
    def observe_mesh_structure(self,request_id,object_id,categories,deadline_ns):
        self.raw_calls+=1;ids=identity();ids['object_id']=object_id
        value=m.analyze_raw(raw_case(fixtures()[1]),ids,task_id=request_id,categories=categories,
                            budget=m.WorkBudget(deadline_ns=deadline_ns))
        if self.bad:self.bad(value)
        return value


class MeshStructureServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.path=self.root/'live.json'
        self.path.write_text(json.dumps(dict(schema_version='1.0',enabled=True,
            project_root=str(Path(__file__).resolve().parents[1]),state_file='state.json',
            audit_file='audit.jsonl',quad_size=64,max_sessions=4)),encoding='utf8')
        self.host=TypedRawHost();self.service=LiveSpatialService(self.path,host=self.host)
        self.clock=patch('human_eye_plugin.mesh_structure_service.counter_descriptor',return_value={'test_clock':True})
        self.clock.start();self.addCleanup(self.clock.stop)

    def test_single_target_private_service_reaches_mcp_content_projection(self):
        result=self.service.observe_mesh_structure('s','only-target')
        self.assertEqual(result['status'],'observed');self.assertEqual(self.host.raw_calls,1)
        self.assertEqual(self.host.calls,0);self.assertEqual(self.host.captures,0)
        self.assertFalse(self.service.state_path.exists())
        payload=_tool_result(result,is_error=False)
        self.assertTrue(payload['content']);self.assertEqual(payload['content'][0]['type'],'text')
        self.assertIn('boundary_edges',payload['content'][0]['text'])
        self.assertFalse(any(c['type']=='image' for c in payload['content']))
        self.assertFalse(result['allow_action']);self.assertFalse(result['executed'])

    def test_no_public_fifth_tool_or_new_query_is_advertised(self):
        self.assertEqual(len(LIVE_MCP_TOOLS_SCHEMA),4)
        from human_eye_plugin.query_policy import validate_query
        with self.assertRaises(ValueError):validate_query({'mode':'mesh_structure'})

    def test_invalid_task_request_never_calls_host(self):
        for kwargs in ({'include_image':True},{'categories':['surface_damage']},{'categories':[]},{'categories':['boundary_edges']*2}):
            with self.subTest(kwargs=kwargs),self.assertRaises(ValueError):
                self.service.observe_mesh_structure('s','target',**kwargs)
        self.assertEqual(self.host.raw_calls,0)

    def test_unavailable_typed_host_never_falls_back_to_pair_capture(self):
        service=LiveSpatialService(self.path,host=MutableHost())
        result=service.observe_mesh_structure('s','target')
        self.assertEqual(result['status'],'unsupported');self.assertEqual(service.host.captures,0)

    def test_task_source_deadline_and_flags_tampering_refused(self):
        edits=[lambda r:r['report']['task'].update(task_id='other'),
               lambda r:r['report']['source'].update(object_id='other'),
               lambda r:r.update(execution_authority=True),
               lambda r:r['accounting'].update(deadline_ns=r['accounting']['deadline_ns']+1),
               lambda r:r['report'].update(natural_visibility='visible'),
               lambda r:r['report']['checks']['boundary_edges'].update(total=0),
               lambda r:r['patches'][0].update(raw_sha256='b'*64),
               lambda r:r['coverage'].update(component_categories_completed=[]),
               lambda r:r['report']['not_checked'].remove('surface_damage')]
        for edit in edits:
            self.host.bad=edit
            with self.subTest(edit=edit),self.assertRaises(ValueError):
                self.service.observe_mesh_structure('s','target')
        self.assertEqual(self.host.calls,0)

    def test_no_reuse_of_old_source_on_host_failure(self):
        self.service.observe_mesh_structure('s','target')
        with patch.object(self.host,'observe_mesh_structure',side_effect=RuntimeError('source gone')):
            with self.assertRaisesRegex(RuntimeError,'source gone'):self.service.observe_mesh_structure('s','target')

    def test_source_bound_regions_survive_consumer_validation(self):
        value=self.service.observe_mesh_structure('s','target')['diagnostic']
        valid=validate_result(value,object_id='target',request_id=value['report']['task']['task_id'],
            categories=m.DEFAULT_CATEGORIES,deadline_ns=value['accounting']['deadline_ns'])
        valid['patches'].clear();self.assertEqual(len(value['patches']),1)


if __name__=='__main__':unittest.main()
