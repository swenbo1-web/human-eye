"""Resident nearest integration with existing exact packet fixtures, no RPC."""
import copy
from contextlib import ExitStack
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from human_eye_plugin import live_service as ls, task_query as tq, auto_router, scene_cache
from verification.nearest_integration_001.tests.test_integration import (
    packet_for,yz,corner,negative_focal,triangle,far_with_late_line)
from verification.arch_read_context_001.test_resident_task import ResidentTaskTests

def forbidden(*a,**kw):raise AssertionError('Repeated normalization, IO, network or execution')
def clean(value):return {key:item for key,item in value.items() if key!='trace_id'}

class Host:
    timeout_s=10.
    def __init__(self):
        self.token={'instance_id':'nearest-host','epoch':1,'revision':1,'selection_key':'f'}
        self.packet=packet_for(yz('f',0),[yz('b',2),yz('c',-2)])
        self.captures=0
    @property
    def last_token(self):forbidden()
    def capture_nearest_candidates(self,*a,**kw):
        self.captures+=1
        packet=copy.deepcopy(self.packet)
        if self.token is not None:packet['capture']['capture_state']=dict(self.token)
        return packet
    capture_scene=forbidden
    apply_transform=forbidden

class Nearest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name);self.config=self.base/'config.json'
        self.config.write_text(json.dumps({'schema_version':'1.0','project_root':str(ROOT),
            'state_file':'state.json','audit_file':'audit.jsonl','quad_size':64,'enabled':True}))
        self.host=Host();self.service=ls.LiveSpatialService(self.config,host=self.host)
    def observe(self,selector=None):
        return self.service.observe('s',focal_id='f' if selector is None else None,
            query={'mode':'surface_nearest',**({'objects':[selector]} if selector else {})},include_image=False)

    def test_warm_skips_normalization_qualifier_kernel_and_ledger_io(self):
        self.service.state_path.write_bytes(b'opaque action ledger bytes')
        cold=self.observe()
        with ExitStack() as stack:
            for name in ('_locked','_save','_runtime'):
                stack.enter_context(patch.object(self.service,name,side_effect=forbidden))
            stack.enter_context(patch.object(ls,'_validated_scene',side_effect=forbidden))
            stack.enter_context(patch.object(tq,'surface_nearest_result',side_effect=forbidden))
            stack.enter_context(patch.object(Path,'read_bytes',side_effect=forbidden))
            warm=self.observe()
        self.assertEqual(clean(cold),clean(warm))
        self.assertEqual([row['id'] for row in warm['nearest_objects']],['b','c'])
        self.assertEqual(self.host.captures,2)
        self.assertEqual(self.service.state_path.read_bytes(),b'opaque action ledger bytes')
        self.assertNotIn('capture_state',json.dumps(warm))

    def test_versions_epoch_instance_selection_and_names_refresh(self):
        self.observe()
        for field,value in (('revision',2),('epoch',2),('instance_id','replacement'),('selection_key','new-selection')):
            self.host.token[field]=value
            self.host.packet['capture']['meshes'][0]['name']=str(value)
            with patch.object(ls,'_validated_scene',wraps=ls._validated_scene) as normalize:
                answer=self.observe()
            self.assertEqual(normalize.call_count,1)
            self.assertEqual(answer['focal']['name'],str(value))
        self.host.packet=packet_for(yz('f',0),[yz('b',3)])
        self.host.token['revision']+=1
        self.assertEqual(self.observe()['distance_m'],3.)

    def test_old_host_no_token_fresh_normalize_and_content_pair_memo(self):
        self.host.token=None
        self.observe()
        with patch.object(ls,'_validated_scene',wraps=ls._validated_scene) as normalize, \
             patch.object(tq,'measure_surface_proximity',side_effect=forbidden):
            self.observe()
        self.assertEqual(normalize.call_count,1)
        self.host.packet=packet_for(yz('f',0),[yz('b',4)])
        self.assertEqual(self.observe()['distance_m'],4.)

    def test_partial_unknown_and_precise_order_survive_result_cache(self):
        from verification.test_concave_geometry import entity
        tiny=2.**-1070
        bad=entity('bad',[(100,0,0),(100,1,0),(100,0,1),
                          (1,0,0),(1,tiny,0),(1,0,tiny)],[[0,1,2],[3,4,5]])
        cases=[packet_for(yz('f',0),[yz('near',2),bad]),
               packet_for(yz('f',0),[bad]),
               packet_for(negative_focal(),[corner('a',1.,2**-29),corner('z',1.,2**-30)])]
        for index,packet in enumerate(cases):
            self.host.packet=packet;self.host.token['revision']=index+2
            cold=self.observe();warm=self.observe()
            self.assertEqual(clean(cold),clean(warm))
            if index==0:
                self.assertEqual(cold['status'],'partial');self.assertIsNone(cold['nearest_objects'])
            if index==1:
                self.assertEqual(cold['status'],'unknown');self.assertIsNone(cold['distance_m'])
            if index==2:self.assertEqual([row['id'] for row in cold['nearest_objects']],['z'])

    def test_first_packet_qualification_and_retry_after_rejection(self):
        packet=copy.deepcopy(self.host.packet)
        self.host.packet['binding']['host_source_sha256']='0'*64
        with patch.object(tq,'_surface_pair_measurement',side_effect=forbidden):
            with self.assertRaisesRegex(ValueError,'source binding'):self.observe()
        self.host.packet=packet
        self.assertEqual(self.observe()['status'],'complete')

    def test_request_selector_not_cached_from_different_query(self):
        first=self.observe()
        self.assertEqual(self.observe({'name':'f'})['nearest_objects'],first['nearest_objects'])
        with self.assertRaisesRegex(ValueError,'selector mismatch'):self.observe({'name':'missing'})

class CacheBoundaries(ResidentTaskTests):
    # Run these two new boundary methods explicitly, not the inherited suite.
    def test_cold_host_binding_mutation_does_not_poison_normalized_new_question(self):
        cold=self.observe(self.query(aabb=False))
        expected=copy.deepcopy(cold['binding']['host_identity'])
        cold['binding']['host_identity']['document_epoch']='caller-poison'
        cold['binding']['host_identity']['object_instances'].clear()
        fresh=self.observe(self.query(aabb=True))
        self.assertEqual(fresh['binding']['host_identity'],expected)

    def test_source_generation_resets_measurements_and_normalized_resources(self):
        self.observe(self.query(('b',)))
        old=self.service._read_context.scene_cache
        self.service._identity=copy.deepcopy(self.service._identity)
        self.service._identity['source_sha256']='f'*64
        with patch.object(tq,'classify_closed_solids',wraps=tq.classify_closed_solids) as closed:
            result=self.observe(self.query(('b',)))
        self.assertEqual(closed.call_count,1)
        self.assertIsNot(old,self.service._read_context.scene_cache)
        self.assertEqual(result['binding']['runtime_source_sha256'],'f'*64)

    def test_new_aabb_question_does_not_encode_entire_mesh_again(self):
        self.observe(self.query(aabb=False))
        with patch.object(scene_cache,'_mesh_dict',side_effect=forbidden):
            answer=self.observe(self.query(aabb=True))
        self.assertEqual(len(answer['facts']['aabb']),4)

if __name__=='__main__':
    with patch.object(socket,'socket',side_effect=forbidden),patch.object(socket,'create_connection',side_effect=forbidden),patch.object(subprocess,'Popen',side_effect=forbidden):
        # Select only our new tests; imported/inherited task tests have their
        # own original log and later run once against final product bytes.
        suite=unittest.TestSuite([unittest.defaultTestLoader.loadTestsFromTestCase(Nearest)])
        for name in ('test_cold_host_binding_mutation_does_not_poison_normalized_new_question',
                     'test_source_generation_resets_measurements_and_normalized_resources',
                     'test_new_aabb_question_does_not_encode_entire_mesh_again'):
            suite.addTest(CacheBoundaries(name))
        result=unittest.TextTestRunner(verbosity=2).run(suite)
        sys.exit(0 if result.wasSuccessful() else 1)
