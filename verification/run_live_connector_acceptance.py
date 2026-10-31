"""External CLI hooks + MCP acceptance; requires the disposable UI fixture."""
import base64
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys

from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from human_eye_plugin.blender_mcp_host import BlenderMCPHost


def main():
    out=ROOT/'verification/fixes/20261022_live_hooks';out.mkdir(parents=True,exist_ok=True)
    fixture=json.loads((out/'live_fixture.json').read_text(encoding='utf-8'))
    config=json.loads((ROOT/'.human-eye/live-connector.json').read_text(encoding='utf-8'))
    config.update(project_root=str(ROOT),state_file=str(out/'acceptance-state.json'),
                  audit_file=str(out/'acceptance-events.jsonl'),
                  focal_name=fixture['focal_name'],reference_name=fixture['reference_name'])
    config_path=out/'acceptance-connector.json';config_path.write_text(json.dumps(config,indent=2),encoding='utf-8')
    # Each fixture/run gets its own state; never reset a previously used journal.
    if (out/'acceptance-state.json').exists():
        raise RuntimeError('Acceptance state already exists; use a fresh evidence directory')
    sid='codex:live-cli-probe'
    checks=[]
    def check(name,valid,**facts):
        checks.append({'test':name,'passed':bool(valid),**facts})
        if not valid:raise AssertionError(name+': '+str(facts))
    def run(mode,payload):
        args=[sys.executable,'-B',str(ROOT/'examples/agents/live_entry.py'),mode,'--config',str(config_path)]
        if mode=='hook':args+=['--agent','codex','--probe']
        proc=subprocess.run(args,input=json.dumps(payload,ensure_ascii=False)+'\n',text=True,
                            encoding='utf-8',capture_output=True,cwd=ROOT,timeout=30)
        check(mode+'_cli_exit',proc.returncode==0,stderr=proc.stderr[-400:])
        return json.loads(proc.stdout)
    def hook(kind,action=None):
        return run('hook',{'hook_event_name':kind,'session_id':'live-cli-probe','turn_id':'manual-probe-only',
             'tool_use_id':'manual-tool-call','tool_name':'mcp__human_eye_live__human_eye_transform',
             'prompt':'Inspect the part/base clearance.','tool_input':{'action':action} if action else {}})
    def tool(name,args):
        response=run('serve',{'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':name,'arguments':args}})
        return response['result']
    report={'kind':'manual_hook_and_real_mcp_live_blender_integration',
            'host_hook_automatic_activation_proven':False,'model_api_calls':0,
            'blender_version':fixture['blender_version'],'tests':checks}
    host=BlenderMCPHost(ROOT)
    before=host.capture_scene()
    first=hook('UserPromptSubmit')
    text=first['hookSpecificOutput']['additionalContext']
    check('prompt_hook_runs_engine_against_live_scene','text_only_hook_no_native_image' in text and '0.1' in text)
    observed=tool('human_eye_scene_observe',{'session_id':sid,'focal_id':fixture['focal_id'],
                  'reference_id':fixture['reference_id']})
    check('live_mcp_observation_success',observed['isError'] is False)
    image=next(item for item in observed['content'] if item['type']=='image')
    png=base64.b64decode(image['data'],validate=True)
    with Image.open(io.BytesIO(png)) as decoded:
        check('actual_native_png_content',decoded.format=='PNG' and decoded.size==(768,768))
    (out/'live_mcp_observation.png').write_bytes(png)
    check('image_not_duplicated_in_text',image['data'] not in observed['content'][0]['text'])
    bad={'focal_id':fixture['focal_id'],'reference_id':fixture['reference_id'],'translation':[0,0,-.15]}
    pre=hook('PreToolUse',bad)
    check('pretool_collision_denial',pre['hookSpecificOutput'].get('permissionDecision')=='deny')
    # Bypass the command hook deliberately: the tool must still reject internally.
    rejected=tool('human_eye_transform',{'session_id':sid,'action':bad})
    check('mcp_inner_gate_without_pre_hook',rejected['isError'] is True)
    check('rejected_transform_does_not_change_live_scene',host.capture_scene()==before)
    good={**bad,'translation':[0,0,.05],'rotation_euler_deg':[0,0,12]}
    pre=hook('PreToolUse',good)
    check('pretool_pass_keeps_host_permissions','permissionDecision' not in pre['hookSpecificOutput'])
    applied=tool('human_eye_transform',{'session_id':sid,'action':good})
    metadata=json.loads(applied['content'][0]['text'])
    check('actual_mcp_transform_and_readback',not applied['isError'] and metadata['verified'] is True)
    facts=json.loads(metadata['routing']['context_text'])
    check('live_readback_gap_150mm',abs(facts['measurement']['signed_clearance_m']-.15)<1e-6,
          actual_clearance_m=facts['measurement']['signed_clearance_m'])
    after=host.capture_scene();post=hook('PostToolUse',good)
    check('posttool_reobserves_without_repeating_motion','hookSpecificOutput' in post and host.capture_scene()==after)
    status=tool('human_eye_connection_status',{})
    state=json.loads(status['content'][0]['text'])
    check('no_uncertain_operation_left',not state['inflight_operation'] and not state['quarantined'])
    events=[json.loads(line) for line in (out/'acceptance-events.jsonl').read_text(encoding='utf-8').splitlines()]
    hook_events=[item for item in events if item['event']=='host_hook']
    check('manual_probe_not_mislabeled_as_host_activation',len(hook_events)>=4 and
          all(item['invocation_source']=='manual_probe' for item in hook_events))
    check('audit_contains_no_prompt_or_mesh_dump',all('prompt' not in item and 'meshes' not in item for item in events))
    report['passed']=all(c['passed'] for c in checks);report['test_count']=len(checks)
    report['png_sha256']=hashlib.sha256(png).hexdigest()
    (out/'live_connector_acceptance.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'passed':report['passed'],'checks':len(checks),
                      'report':str(out/'live_connector_acceptance.json')},ensure_ascii=False))


if __name__=='__main__':main()
