"""Typed observer transport boundaries, independent of Blender rendering."""
from __future__ import annotations

import ast
import hashlib
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from human_eye_plugin.blender_process import (
    BlenderProcessHost, NATIVE_OBSERVATION_PROTOCOL,
    _validate_native_observation_capabilities, _validate_native_observation_request,
)
from human_eye_plugin.blender_mcp_host import BlenderMCPHost
from human_eye_plugin.forward_deadline import counter_descriptor
from verification.test_blender_mcp_host import _server, _reply


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'human_eye_plugin/blender_host.py'
FROZEN = ROOT / 'verification/fixes/20261031_v21_readonly_product/before/human_eye_plugin/blender_mcp_host.py'


def capability(pid=321):
    return {'schema_version':'native-readonly-capabilities-v1',
        'protocol':NATIVE_OBSERVATION_PROTOCOL,'process_id':pid,
        'clock':counter_descriptor(),'max_duration_ns':30_000_000_000,
        'host_source_sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        'read_only':True,'execution_authority':False}


def parent(caps, default=True):
    host=BlenderProcessHost.__new__(BlenderProcessHost)
    host._capabilities=caps;host._default_worker=default
    host._process=SimpleNamespace(pid=321)
    host._request=Mock(return_value={'typed':'result'})
    return host


class ReadonlyProductTransportTests(unittest.TestCase):
    def test_capability_is_exact_and_detached(self):
        raw=capability()
        got=_validate_native_observation_capabilities(raw,source=SOURCE,process_id=321)
        self.assertEqual(raw,got);self.assertIsNot(raw,got)
        got['clock']['frequency_hz']=0
        self.assertNotEqual(raw,got)

    def test_capability_rejects_every_identity_or_authority_mismatch(self):
        changes={'schema_version':'other','protocol':'other','process_id':True,
            'clock':{},'max_duration_ns':30_000_000_001,
            'host_source_sha256':'0'*64,'read_only':1,'execution_authority':0}
        for key,value in changes.items():
            with self.subTest(key=key),self.assertRaises(ValueError):
                bad=capability();bad[key]=value
                _validate_native_observation_capabilities(bad,source=SOURCE,process_id=321)
        for bad in ({},dict(capability(),extra=1),capability(999)):
            with self.assertRaises(ValueError):
                _validate_native_observation_capabilities(bad,source=SOURCE,process_id=321)

    def test_parent_old_host_is_unsupported_without_request(self):
        host=parent({})
        self.assertIsNone(host.native_observation_capabilities())
        with self.assertRaises(ValueError):host.observe_readonly_native('id','a','b','rev',1)
        host._request.assert_not_called()

    def test_parent_custom_worker_cannot_claim_new_capability(self):
        host=parent({'native_observation_capabilities':capability()},False)
        with self.assertRaises(ValueError):host.native_observation_capabilities()
        host._request.assert_not_called()

    def test_parent_typed_request_preserves_original_deadline_and_literal_ids(self):
        host=parent({'native_observation_capabilities':capability()})
        focal="part';raise RuntimeError('literal')"
        result=host.observe_readonly_native('request',focal,'base','rev',1,'XY')
        self.assertEqual(result,{'typed':'result'})
        host._request.assert_called_once_with('observe_readonly_native',{
            'request_id':'request','focal_id':focal,'reference_id':'base',
            'expected_capture_revision':'rev','deadline_ns':1,'view':'XY'})

    def test_request_rejects_invalid_values_before_transport(self):
        good=['id','a','b','rev',1,'SCENE']
        changes={0:['','\n',True,'x'*257],1:['',False],2:['a'],
            3:[''],4:[True,0,-1,1<<63],5:['scene','PAN']}
        for index,values in changes.items():
            for value in values:
                bad=list(good);bad[index]=value
                with self.subTest(index=index,value=value),self.assertRaises(ValueError):
                    _validate_native_observation_request(*bad)

    def test_diagnostic_request_does_not_create_or_extend_lease(self):
        host=parent({'native_observation_capabilities':capability()})
        host.last_readonly_native_audit('existing')
        host._request.assert_called_once_with('last_readonly_native_audit',{'request_id':'existing'})
        with self.assertRaises(ValueError):host.last_readonly_native_audit('')

    def test_socket_capability_cached_with_detached_revalidation(self):
        with _server(lambda req:_reply(req,capability()),connections=1) as (port,requests):
            host=BlenderMCPHost(ROOT,port=port)
            first=host.native_observation_capabilities();first['clock'].clear()
            self.assertEqual(host.native_observation_capabilities(),capability())
            self.assertEqual(len(requests),1)
            with patch('human_eye_plugin.blender_process.Path.read_bytes',return_value=b'changed'):
                with self.assertRaises(ValueError):host.native_observation_capabilities()
            self.assertEqual(len(requests),1)

    def test_socket_old_host_has_explicit_cached_unsupported(self):
        with _server(lambda req:_reply(req,{'supported':False}),connections=1) as (port,requests):
            host=BlenderMCPHost(ROOT,port=port)
            self.assertIsNone(host.native_observation_capabilities())
            self.assertIsNone(host.native_observation_capabilities())
            with self.assertRaises(ValueError):host.last_readonly_native_audit('id')
            self.assertEqual(len(requests),1)

    def test_socket_malformed_declared_capability_never_calls_observer(self):
        bad=capability();bad['execution_authority']=True
        with _server(lambda req:_reply(req,bad),connections=1) as (port,requests):
            host=BlenderMCPHost(ROOT,port=port)
            with self.assertRaises(ValueError):host.observe_readonly_native('id','a','b','rev',1)
            self.assertEqual([r[1]['command'] for r in requests],['native_observation_capabilities'])

    def test_socket_new_command_uses_fixed_template_and_exact_arguments(self):
        def respond(req):
            return _reply(req,capability() if req['command']=='native_observation_capabilities' else req['params'])
        with _server(respond,connections=2) as (port,requests):
            host=BlenderMCPHost(ROOT,port=port)
            got=host.observe_readonly_native('id','part\";x=1','base','rev',1,'XZ')
            self.assertEqual(got['focal_id'],'part\";x=1');self.assertEqual(got['deadline_ns'],1)
            self.assertEqual(len(requests),2)
            for command,req in requests:
                ast.parse(command['params']['code'])
                self.assertNotIn('apply_transform',command['params']['code'])
                self.assertNotIn('begin_owned_episode',command['params']['code'])

    def test_fixed_template_rejects_unknown_keys_and_oversize(self):
        host=BlenderMCPHost(ROOT)
        for command,params in [('native_observation_capabilities',{'extra':1}),
                ('last_readonly_native_audit',{}),('unrecognized',{})]:
            with self.assertRaises(ValueError):host._observation_code(command,params,'nonce')
        with self.assertRaises(ValueError):
            host._observation_code('last_readonly_native_audit',{'request_id':'x'*5000},'nonce')

    def test_legacy_capture_apply_and_supervision_templates_are_byte_exact(self):
        spec=importlib.util.spec_from_file_location('human_eye_plugin._frozen_mcp_transport',FROZEN)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        old=module.BlenderMCPHost(ROOT);new=BlenderMCPHost(ROOT)
        cases=[('capture',{}),('capture_evidence',{}),('apply',{
            'action':{'focal_id':'part','translation':[0,0,.001]},'expected_revision':'rev',
            'expected_fingerprint':'fingerprint'}),('motion_status',{'goal_id':'goal','after_event_count':0})]
        for command,params in cases:
            with self.subTest(command=command):self.assertEqual(
                old._code(command,params,'same-nonce'),new._code(command,params,'same-nonce'))


if __name__=='__main__':unittest.main()
