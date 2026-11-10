"""Finite nearest-evidence contracts using existing captures and real kernels.

The parent runs exactly these bytes under each version's original source guard.
Independent geometry expectations remain active in both versions. Only the
new-field assertions are conditional on the frozen baseline/candidate role.
"""
import copy
from contextlib import ExitStack
import hashlib
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from human_eye_plugin import blender_host, live_service as ls, live_spatial_mcp as mcp
from human_eye_plugin import surface_proximity as surface, task_query as tq
from human_eye_plugin.runtime_identity import runtime_identity
from verification import test_blender_host_contracts as contracts

contracts._module = blender_host
contracts.BlenderSceneHost = blender_host.BlenderSceneHost
contracts.BlenderHostError = blender_host.BlenderHostError
from verification.surface_nearest_entry_001.tests.test_surface_nearest_entry import (
    ActualCandidateHost, add_retained_exact_bit_budget_face)
from verification.nearest_integration_001.tests.test_integration import packet_for, yz, corner, negative_focal
from verification.test_task_complete_001 import large_world_pair, independent_corner_gap
from verification.perf030_002_cases import triangle_truth

PRODUCT_ROLE = globals().get('PRODUCT_ROLE', 'candidate')
RUNTIME_SOURCE_SHA256 = globals().get('RUNTIME_SOURCE_SHA256', runtime_identity()['source_sha256'])
ROOT = Path(__file__).resolve().parents[3]
EVIDENCE = {}
NEW_FIELDS = {'best_known_evidence', 'measurement_semantics'}
MEASUREMENT_FIELDS = ('point_a_world', 'point_b_world', 'direction_a_to_b',
    'witness_status', 'direction_status', 'witness_reason', 'direction_reason')


def core(value):
    return {key:copy.deepcopy(item) for key,item in value.items() if key not in NEW_FIELDS|{'trace_id'}}


def forbidden(*args, **kwargs):
    raise AssertionError('nearest must not invoke a solid classifier or a write path')


class PacketHost:
    timeout_s = 10.
    def __init__(self, packet):
        self.packet = copy.deepcopy(packet)
        self.captures = self.calls = self.scene_calls = self.selected_calls = self.name_calls = 0
        self.last_packet = None
        self.token = dict(instance_id='evidence-packet-host', epoch=1, revision=1,
            selection_key=packet['focal_id'])
    def capture_nearest_candidates(self, *args, **kwargs):
        self.captures += 1
        self.last_packet = copy.deepcopy(self.packet)
        self.last_packet['capture']['capture_state'] = dict(self.token)
        return self.last_packet
    capture_scene = capture_task_scene = apply_transform = forbidden


class NearestEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='nearest-evidence-')
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.serial = 0

    def service(self, host, fixed_case):
        if isinstance(host, ActualCandidateHost):
            namespace = host.backend.bpy.app.driver_namespace
            for key in ('_human_eye_document_epoch_v1', '_human_eye_residency_document_v1'):
                namespace[key] = hashlib.sha256((fixed_case+'|'+key).encode()).hexdigest()[:32]
        self.serial += 1
        config = self.folder/('config_'+str(self.serial)+'.json')
        config.write_text(json.dumps(dict(schema_version='1.0', enabled=True, project_root=str(ROOT),
            state_file='state_'+str(self.serial)+'.json', audit_file='audit_'+str(self.serial)+'.jsonl', quad_size=64)), encoding='utf8')
        return ls.LiveSpatialService(config, host=host)

    def call(self, tag, service, host, mode, selector, expected_counts):
        measurements = {}
        counts = dict(capture=0, pair=0, kernel=0, rank=0, nearest=0, closed_solid=0)
        capture_before = len(host.candidate_calls) if isinstance(host,ActualCandidateHost) else host.captures
        pair, kernel, rank, nearest = tq._surface_pair_measurement, tq.measure_surface_proximity, tq._rank_surface_results, surface._nearest
        def measured(a,b,*args,**kwargs):
            counts['pair'] += 1
            result = pair(a,b,*args,**kwargs)
            measurements[b.object_id] = copy.deepcopy(result)
            return result
        def solve(*args,**kwargs):
            counts['kernel'] += 1
            return kernel(*args,**kwargs)
        def ranked(*args,**kwargs):
            counts['rank'] += 1
            return rank(*args,**kwargs)
        def nearest_call(*args,**kwargs):
            counts['nearest'] += 1
            return nearest(*args,**kwargs)
        def closed(*args,**kwargs):
            counts['closed_solid'] += 1
            return forbidden()
        with ExitStack() as stack:
            for owner,name,replacement in ((tq,'_surface_pair_measurement',measured),
                (tq,'measure_surface_proximity',solve),(tq,'_rank_surface_results',ranked),
                (surface,'_nearest',nearest_call),(tq,'classify_closed_solids',closed),
                (tq,'_closed_solid_pair_measurement',closed)):
                stack.enter_context(patch.object(owner,name,side_effect=replacement))
            query = {'mode':'surface_nearest','objects':[copy.deepcopy(selector)]}
            tool = raw_text = None
            if mode=='direct':
                body = service.observe('evidence-session',query=query,include_image=False)
            else:
                server = mcp.LiveSpatialMCPServer(service, default_session_id='evidence-session', spatial_task_only=mode=='S')
                arguments = ({'target':copy.deepcopy(selector)} if mode=='S' else
                    {'session_id':'evidence-session','include_image':False,'query':query})
                original = copy.deepcopy(arguments)
                tool = server._call_tool('human_eye_surface_nearest' if mode=='S' else 'human_eye_scene_observe',arguments)
                self.assertEqual(arguments,original)
                self.assertEqual(len(tool['content']),1)
                self.assertEqual(tool['content'][0]['type'],'text')
                raw_text = tool['content'][0]['text']
                body = json.loads(raw_text)
                self.assertEqual(tool['isError'],body['status']=='unknown')
        counts['capture'] = (len(host.candidate_calls) if isinstance(host,ActualCandidateHost) else host.captures)-capture_before
        self.assertEqual(counts,dict(zip(counts,expected_counts)),tag)
        packet = host.last_packet
        self.assertEqual(body['binding']['runtime_source_sha256'],RUNTIME_SOURCE_SHA256)
        self.assertEqual(body['binding']['directory_sha256'],packet['binding']['directory_sha256'])
        self.assertEqual(body['binding']['document_epoch'],packet['binding']['host_identity']['document_epoch'])
        self.assertEqual(body['binding']['host_source_sha256'],packet['binding']['host_source_sha256'])
        self.assertEqual(body['focal']['id'],packet['focal_id'])
        names = {row['object_id']:row['name'] for row in packet['capture']['meshes']}
        self.assertEqual(body['focal']['name'],names[body['focal']['id']])
        for row in body['best_known_objects']:
            self.assertEqual(row['name'],names[row['id']])
        self.assertFalse(body['execution_authority'])
        self.assertEqual(body['unit'],'m')
        self.assertEqual(host.calls,0)
        logs = [json.loads(line) for line in service.audit_path.read_text(encoding='utf8').splitlines()]
        work = [row['task_work'] for row in logs if row.get('event')=='observe'][-1]
        EVIDENCE[tag] = dict(body=copy.deepcopy(body), core=core(body), raw_text=raw_text,
            raw_tool_result=copy.deepcopy(tool), raw_tool_result_json=None if tool is None else
                json.dumps(tool,ensure_ascii=False,separators=(',',':'),allow_nan=False),
            counts=counts, measurements=measurements, capture_binding=copy.deepcopy(packet['binding']),
            packet_work=copy.deepcopy(packet['work']), diagnostics=copy.deepcopy(work), selector=copy.deepcopy(selector))
        return body,measurements

    def new_fields(self, body, measurements, packet):
        if PRODUCT_ROLE=='baseline':
            self.assertFalse(NEW_FIELDS.intersection(body))
            return
        self.assertEqual(body['measurement_semantics'],dict(distance='unsigned_surface_distance_not_penetration_depth',
            coordinate_frame='world',pair_order='focal_to_candidate',
            method=next(iter(measurements.values()))['method'] if body['best_known_objects'] else None))
        self.assertEqual([row['candidate'] for row in body['best_known_evidence']],body['best_known_objects'])
        source = {row['object_id']:row for row in packet['capture']['meshes']}
        for row in body['best_known_evidence']:
            oid = row['candidate']['id']
            original = measurements[oid]
            self.assertEqual(set(row),{'candidate'}|{key for key in MEASUREMENT_FIELDS if key in original})
            self.assertNotIn('object_id',row)
            for key in MEASUREMENT_FIELDS:
                if key in original:
                    self.assertEqual(row[key],original[key],key)
            if row['witness_status']=='measured':
                self.assertAlmostEqual(math.dist(row['point_a_world'],row['point_b_world']),original['distance_m'],delta=1e-9)
                for point,mesh in ((row['point_a_world'],source[body['focal']['id']]),(row['point_b_world'],source[oid])):
                    minimum = min(triangle_truth(point,[mesh['vertices'][i] for i in face])['distance_sq'] for face in mesh['faces'])
                    self.assertLessEqual(minimum,1e-18)
            if row['direction_status']=='measured':
                self.assertAlmostEqual(math.sqrt(sum(v*v for v in row['direction_a_to_b'])),1.,delta=1e-14)

    def both(self, label, factory, expected_status, expected_distance, expected_counts):
        previous = None
        for mode in ('C','S'):
            host = factory()
            service = self.service(host,label)
            selector = {'name':'O0'} if isinstance(host,ActualCandidateHost) else {
                'name':next(row['name'] for row in host.packet['capture']['meshes'] if row['object_id']==host.packet['focal_id'])}
            body,measurements = self.call(label+'.'+mode,service,host,mode,selector,expected_counts)
            self.assertEqual(body['status'],expected_status)
            self.assertEqual(body['best_known_distance_m'],expected_distance)
            self.new_fields(body,measurements,host.last_packet)
            if previous is not None:
                self.assertEqual(core(body),core(previous))
                if PRODUCT_ROLE!='baseline':
                    self.assertEqual(body['best_known_evidence'],previous['best_known_evidence'])
            previous = body
        return previous

    def test_open_surfaces_both_entries_keep_source_and_one_existing_measurement(self):
        body = self.both('open',ActualCandidateHost,'complete',2.,(1,1,1,1,1,0))
        self.assertEqual(len(body['nearest_objects']),1)
        self.assertEqual(body['coverage'],dict(targets_excluding_focal=2,distance_valid=1,strictly_excluded=1,unresolved=0))

    def test_all_positive_exact_ties_receive_their_own_measurement(self):
        body = self.both('ties',lambda:ActualCandidateHost((0.,2.,-2.,100.)), 'complete',2.,(1,2,2,1,2,0))
        self.assertEqual(len(body['nearest_objects']),2)
        self.assertEqual(body['nearest_objects'],body['best_known_objects'])

    def test_zero_ties_do_not_invent_a_direction(self):
        body = self.both('zero_ties',lambda:ActualCandidateHost((0.,0.,0.,100.)), 'complete',0.,(1,2,2,1,2,0))
        self.assertEqual(len(body['nearest_objects']),2)
        if PRODUCT_ROLE!='baseline':
            for row in body['best_known_evidence']:
                self.assertEqual(row['point_a_world'],row['point_b_world'])
                self.assertIsNone(row['direction_a_to_b'])
                self.assertEqual(row['direction_status'],'not_applicable')
                self.assertEqual(row['direction_reason'],'undefined_zero_distance')

    def test_partial_preserves_best_known_without_claiming_global_evidence(self):
        def factory():
            host=ActualCandidateHost()
            add_retained_exact_bit_budget_face(host.objects[-1])
            return host
        body=self.both('partial',factory,'partial',2.,(1,2,2,1,1,0))
        self.assertIsNone(body['nearest_objects']);self.assertIsNone(body['distance_m'])
        self.assertEqual(len(body['best_known_objects']),1)
        self.assertEqual(body['coverage']['unresolved'],1)
        self.assertEqual(body['unresolved'][0]['reason'],'surface_exact_bit_budget')

    def test_all_unknown_has_no_fabricated_best_known_witness(self):
        def factory():
            host=ActualCandidateHost((0.,100.))
            add_retained_exact_bit_budget_face(host.objects[-1])
            return host
        body=self.both('all_unknown',factory,'unknown',None,(1,1,1,1,0,0))
        self.assertIsNone(body['nearest_objects']);self.assertEqual(body['best_known_objects'],[])
        if PRODUCT_ROLE!='baseline': self.assertEqual(body['best_known_evidence'],[])

    def test_valid_distance_keeps_unknown_world_witness_and_independent_direction(self):
        left,right=large_world_pair()
        expected=independent_corner_gap(left,right)
        body=self.both('unpublished',lambda:PacketHost(packet_for(left,[right])), 'complete',expected,(1,1,1,1,1,0))
        if PRODUCT_ROLE!='baseline':
            row=body['best_known_evidence'][0]
            self.assertEqual(row['witness_status'],'unknown')
            self.assertEqual(row['witness_reason'],'original_surface_witness_precision_exceeded')
            self.assertIsNone(row['point_a_world']);self.assertIsNone(row['point_b_world'])
            self.assertEqual(row['direction_status'],'measured')

    def test_equal_rounded_distances_do_not_add_a_false_tie(self):
        factory=lambda:PacketHost(packet_for(negative_focal(),[corner('a',1.,2**-29),corner('z',1.,2**-30)]))
        body=self.both('rounded',factory,'complete',1.,(1,2,2,1,2,0))
        self.assertEqual([row['id'] for row in body['nearest_objects']],['z'])
        if PRODUCT_ROLE!='baseline': self.assertEqual(len(body['best_known_evidence']),1)

    def test_focal_order_warm_result_and_return_mutation_do_not_flip_or_poison_evidence(self):
        host=PacketHost(packet_for(yz('z',0.),[yz('a',2.)]))
        service=self.service(host,'order')
        first,measurements=self.call('order.cold_z_service',service,host,'direct',{'name':'z'},(1,1,1,1,1,0))
        self.new_fields(first,measurements,host.last_packet)
        expected=copy.deepcopy(first)
        if PRODUCT_ROLE!='baseline':
            row=first['best_known_evidence'][0]
            self.assertEqual(row['direction_a_to_b'],[1.,0.,0.])
            row['point_a_world'][0]=999.
            row['candidate']['name']='caller-poison'
        for mode in ('C','S'):
            warm,_=self.call('order.warm_z_'+mode,service,host,mode,{'name':'z'},(1,0,0,0,0,0))
            self.assertEqual(core(warm),core(expected))
            if PRODUCT_ROLE!='baseline':
                self.assertEqual(warm['best_known_evidence'],expected['best_known_evidence'])
        host.packet=packet_for(yz('a',2.),[yz('z',0.)])
        host.token.update(revision=2,selection_key='a')
        reverse,raw=self.call('order.reverse_a_C',service,host,'C',{'name':'a'},(1,1,1,1,1,0))
        self.new_fields(reverse,raw,host.last_packet)
        self.assertEqual(reverse['focal']['id'],'a')
        if PRODUCT_ROLE!='baseline':
            self.assertEqual(reverse['best_known_evidence'][0]['direction_a_to_b'],[-1.,0.,0.])


if __name__=='__main__': unittest.main(verbosity=2)
