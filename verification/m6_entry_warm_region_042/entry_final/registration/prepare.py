"""Freeze final042 project-only H0/H1/OFF registration. Never writes trust."""
from __future__ import annotations
import base64
import hashlib
import json
from pathlib import Path
import subprocess
import tomllib

HERE=Path(__file__).resolve().parent
RAW=Path('D:/HumanEye/runs/M6-042-ENTRY-WARM-REGION/E_FINAL_001/registration')
FINAL=RAW.parent
CONFIG=FINAL/'direct/CONFIG.json'
PINS=Path('D:/HumanEye/runs/M6-041-KERNEL-HOOK/delivery/install/PINS.json')
MATCHER=r'^mcp__human_eye_live__human_eye_connection_status$'
EVENTS=('UserPromptSubmit','PostToolUse')

def pin(path):
 path=Path(path).resolve(strict=True);body=path.read_bytes()
 return {'path':str(path),'bytes':len(body),'sha256':hashlib.sha256(body).hexdigest()}
def read(path):return json.loads(Path(path).read_bytes())
def put(path,value):
 path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
 with path.open('x',encoding='utf8')as file:json.dump(value,file,ensure_ascii=False,indent=2)
 return pin(path)
def check(ref):assert pin(ref['path'])==ref;return Path(ref['path'])

def main():
 RAW.mkdir(parents=True,exist_ok=True);marker=RAW/'REGISTRATION.json';assert not marker.exists()
 protocol=read(FINAL/'FORMAL_PROTOCOL.json');r3=read(PINS)['arms']['r3'];cfg=read(CONFIG)
 assert protocol['mcp']['regex']==MATCHER and protocol['mcp']['canonical']=='mcp__human_eye_live__human_eye_connection_status'
 assert protocol['endpoint']['port']==48142
 assert cfg['blender']['host']=='127.0.0.1'and cfg['blender']['port']==48142
 assert cfg['enabled']and cfg['observe_on_prompt']and Path(cfg['project_root']).resolve()==Path(r3['site']).resolve()
 assert cfg['expected_identity']['source_sha256']==r3['identity']['source_sha256']
 check(r3['binding']);check(r3['launcher'])
 expected='ebd8068712ae70af74d4cfacc6fd8e05f5056e6047334c91c6487f1cd18dff0e'
 assert r3['identity']['source_sha256']==expected
 python=r3['dependency_python'];launcher=r3['launcher']['path'];mcp_args=['-I','-B',launcher,'serve','--config',str(CONFIG)]
 config_body='\n'.join(('[mcp_servers.human_eye_live]',
  'command = '+json.dumps(python),'args = '+json.dumps(mcp_args),
  'cwd = '+json.dumps(str(FINAL/'direct')),'enabled = true',
  'enabled_tools = ["human_eye_connection_status"]','startup_timeout_sec = 30','tool_timeout_sec = 30',''))
 assert tomllib.loads(config_body)['mcp_servers']['human_eye_live']['enabled_tools']==['human_eye_connection_status']
 rows={}
 for arm in('H0','H1','OFF'):
  workspace=RAW/'workspaces'/arm;dot=workspace/'.codex';dot.mkdir(parents=True,exist_ok=False)
  hooks={'description':'M6-042 '+arm+' project-only read-only Human Eye definitions. Native review is required.','hooks':{}}
  commands=[]
  if arm!='OFF':
   for event in EVENTS:
    argv=[python,'-I','-B',launcher,'hook','--agent','codex','--event',event,'--config',str(CONFIG)]
    command=subprocess.list2cmdline(argv)
    if arm=='H0':
     assert all("'"not in word for word in argv)
     script='& '+' '.join("'"+word+"'"for word in argv)+'; exit $LASTEXITCODE'
     command='C:\\WINDOWS\\System32\\WindowsPowerShell\\v1.0\\powershell.exe -NoProfile -NonInteractive -EncodedCommand '+base64.b64encode(script.encode('utf-16-le')).decode('ascii')
    group={'hooks':[{'type':'command','command':command,'timeout':30}]}
    if event=='PostToolUse':group['matcher']=MATCHER
    hooks['hooks'][event]=[group]
    commands.append({'event':event,'command':command,'logical_argv':argv,'matcher':group.get('matcher')})
  hook_ref=put(dot/'hooks.json',hooks)
  with (dot/'config.toml').open('x',encoding='utf8')as file:file.write(config_body)
  assert 'hooks'not in tomllib.loads((dot/'config.toml').read_text())
  rows[arm]={'workspace':str(workspace),'scope':'project_only','hooks':hook_ref,'project_config':pin(dot/'config.toml'),
   'registered_command_count':len(commands),'commands':commands,'user_layer_files_created':0,'trust_state_written':False}
 public={'schema':'m6-042-final-project-registration-v1','status':'prepared_native_project_trust_pending',
  'protocol':pin(FINAL/'FORMAL_PROTOCOL.json'),'runtime':r3['identity'],'binding':r3['binding'],'launcher':r3['launcher'],
  'connector_config':pin(CONFIG),'endpoint':protocol['endpoint'],'readonly_tool':protocol['mcp'],
  'mcp':{'server':'human_eye_live','command':python,'args':mcp_args,'enabled_tools':['human_eye_connection_status']},
  'workspaces':rows,'definition_count':4,'native_reviewed_definition_count':0,
  'no_user_or_inline_TOML_hooks':True,'no_PreToolUse_or_Stop_or_Interrupt':True,
  'no_model_or_Blender_started':True,'source':pin(__file__)}
 print(json.dumps(put(marker,public)))

if __name__=='__main__':main()
