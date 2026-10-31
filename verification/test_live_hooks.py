"""Actual hook wire contract; manual probes are not host activation evidence."""
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from human_eye_plugin.live_hooks import route_live_hook,SPATIAL_TRANSFORM
from human_eye_plugin.blender_process import HostTransportError


class HookService:
    def __init__(self):self.config={'enabled':True};self.calls=[];self.records=[];self.fail=False
    def record_event(self,*args,**kwargs):self.records.append((args,kwargs))
    def observe(self,*args,**kwargs):
        self.calls.append(('observe',args,kwargs))
        if self.fail:raise ConnectionError()
        return {'status':'observed','routing':{'route':'engine','context_text':'measured geometry',
                'scene_revision':'r1','engine_invoked':True,'reason_codes':[],'image':{'data':'not_inline'}}}
    def preview_action(self,*args,**kwargs):
        self.calls.append(('preview',args))
        if self.fail:raise ConnectionError()
        return {'status':'preview','allow_action':True,'routing':{'context_text':'checked endpoint','route':'engine'}}


class LiveHooksTests(unittest.TestCase):
    def event(self,event='UserPromptSubmit',**changes):
        value={'hook_event_name':event,'session_id':'s','prompt':'Inspect scene.',
               'turn_id':'turn','tool_use_id':'call','tool_name':SPATIAL_TRANSFORM,
               'tool_input':{'action':{'focal_id':'part','reference_id':'base','translation':[0,0,.1]}}}
        value.update(changes);return value

    def test_prompt_automatically_observes_and_labels_text_delivery(self):
        service=HookService();result=route_live_hook(self.event(),service)
        self.assertEqual(service.calls[0][0],'observe')
        text=result['hookSpecificOutput']['additionalContext']
        self.assertIn('text_only_hook_no_native_image',text);self.assertNotIn('not_inline',text)
        self.assertEqual(service.records[-1][1]['turn_id'],'turn')

    def test_pretool_previews_only_and_does_not_override_host_permissions(self):
        service=HookService();result=route_live_hook(self.event('PreToolUse'),service)
        self.assertEqual(service.calls[0][0],'preview')
        self.assertNotIn('permissionDecision',result['hookSpecificOutput'])

    def test_error_blocks_registered_transform_but_closed_blender_does_not_block_prompt(self):
        service=HookService();service.fail=True
        # An untyped application error keeps the previous conservative fallback.
        self.assertEqual(route_live_hook(self.event(),service),{})
        result=route_live_hook(self.event('PreToolUse'),service)
        self.assertEqual(result['hookSpecificOutput']['permissionDecision'],'deny')

    def test_host_transport_failure_reports_missing_observation_without_denying_prompt(self):
        service=HookService()
        with patch.object(service,'observe',side_effect=HostTransportError('No matching response')):
            result=route_live_hook(self.event(),service)
        output=result['hookSpecificOutput']
        self.assertNotIn('permissionDecision',output)
        context=json.loads(output['additionalContext'])
        self.assertEqual(context['human_eye_live'],'unavailable')
        self.assertEqual(context['observation_status'],'unavailable')
        self.assertEqual(context['reason_codes'],['host_observation_unavailable'])
        self.assertTrue(context['requires_reobserve'])

    def test_posttool_retains_tool_delivery_without_recapture_or_replay(self):
        service=HookService();result=route_live_hook(self.event('PostToolUse'),service)
        self.assertEqual(result,{})
        self.assertEqual(service.calls,[])
        self.assertTrue(any(record[1].get('status')=='tool_result_delivery_retained' for record in service.records))

    def test_blocked_preview_preserves_top_level_reasons_and_scope(self):
        service=HookService()
        capability={'supported':False,'reasons':[{'reason':'nonrigid_or_nonuniform_world_frame'}]}
        value={'status':'blocked','allow_action':False,
            'reason_codes':['host_execution_capability_required'],
            'routing':{'reason_codes':['generic_routing_failure']},
            'observation_status':'partial',
            'scene_assessment':{'status':'unknown','scope':'all_scene_objects','unknown_object_ids':['plane']},
            'action_eligibility':{'status':'blocked','reason_codes':['host_execution_capability_required']},
            'pair_goal':{'status':'satisfied','scope':'known_mesh_pair_clearance_alignment_and_world_pivot'},
            'execution_status':'not_started','task_succeeded_scope':'known_mesh_pair',
            'host_execution':capability,
            'prompt':'must not be forwarded','meshes':[{'vertices':'must not be forwarded'}]}
        with patch.object(service,'preview_action',return_value=value):
            result=route_live_hook(self.event('PreToolUse'),service)
        self.assertEqual(result['hookSpecificOutput']['permissionDecision'],'deny')
        context=json.loads(result['hookSpecificOutput']['additionalContext'])
        self.assertEqual(context['reason_codes'],['host_execution_capability_required'])
        for field in ('observation_status','scene_assessment','action_eligibility','pair_goal',
                      'execution_status','task_succeeded_scope','host_execution'):
            self.assertEqual(context[field],value[field])
        self.assertNotIn('prompt',context);self.assertNotIn('meshes',context)

    def test_empty_or_malformed_top_level_reasons_fall_back_to_routing(self):
        for reason in (None,[],{},'unknown',[''],[0]):
            with self.subTest(reason=reason):
                service=HookService()
                value={'status':'preview','allow_action':False,'reason_codes':reason,
                    'routing':{'reason_codes':['candidate_collision'],'context_text':'checked endpoint'}}
                with patch.object(service,'preview_action',return_value=value):
                    result=route_live_hook(self.event('PreToolUse'),service)
                context=json.loads(result['hookSpecificOutput']['additionalContext'])
                self.assertEqual(context['reason_codes'],['candidate_collision'])
                self.assertEqual(result['hookSpecificOutput']['permissionDecision'],'deny')
                reason=result['hookSpecificOutput']['permissionDecisionReason']
                brief=json.loads(reason.split(': ',1)[1])
                self.assertEqual(brief['reason_codes'],['candidate_collision'])

    def test_unrelated_tools_and_events_are_noops(self):
        service=HookService()
        for event in (self.event('Stop'),self.event('PreToolUse',tool_name='Bash'),
                      self.event('PostToolUse',tool_name='mcp__blender__execute_blender_code')):
            self.assertEqual(route_live_hook(event,service),{})
        self.assertEqual(service.calls,[])

    def test_disabled_and_bad_input_do_not_invoke_engine(self):
        service=HookService();service.config['enabled']=False
        self.assertEqual(route_live_hook(self.event(),service),{})
        result=route_live_hook(self.event('PreToolUse'),service)
        self.assertEqual(result['hookSpecificOutput']['permissionDecision'],'deny')
        self.assertEqual(service.calls,[])

    def test_manual_probe_audit_is_explicit(self):
        service=HookService();route_live_hook(self.event(),service,invocation_source='manual_probe')
        self.assertEqual(service.records[-1][1]['invocation_source'],'manual_probe')

    def test_bad_cli_json_and_unrelated_tool_with_missing_config_stay_valid_json(self):
        root=Path(__file__).resolve().parents[1]
        for text in ('[]','broken',json.dumps(self.event('PreToolUse',tool_name='Bash'))):
            proc=subprocess.run([sys.executable,'-B','-m','human_eye_plugin.live_hooks','--config','missing.json'],
                                input=text,text=True,capture_output=True,cwd=root,timeout=10)
            self.assertEqual(proc.returncode,0,proc.stderr);self.assertEqual(json.loads(proc.stdout),{})


if __name__=='__main__':unittest.main()
