"""Read-only final registration invariants and actual metadata receipts."""
from __future__ import annotations
import base64
import importlib.util
import json
from pathlib import Path
import re
import tomllib

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('_042_final_preparation',HERE/'prepare.py')
p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)

def verify():
 registration=p.read(p.RAW/'REGISTRATION.json');p.check(registration['connector_config']);p.check(registration['protocol'])
 checks=[];definitions=[];probe_rows=[]
 expected_config=None
 for arm in('H0','H1','OFF'):
  row=registration['workspaces'][arm];hooks=p.read(p.check(row['hooks']));config=tomllib.loads(p.check(row['project_config']).read_text())
  assert set(config)=={'mcp_servers'}and set(config['mcp_servers'])=={'human_eye_live'}
  mcp=config['mcp_servers']['human_eye_live']
  assert mcp['enabled_tools']==['human_eye_connection_status']and mcp['enabled']
  assert mcp['command']==registration['mcp']['command']and mcp['args']==registration['mcp']['args']
  if expected_config is None:expected_config=config
  else:assert config==expected_config
  if arm=='OFF':assert hooks['hooks']=={}and row['registered_command_count']==0
  else:
   assert set(hooks['hooks'])==set(p.EVENTS)and row['registered_command_count']==2
   for command in row['commands']:
    event=command['event'];groups=hooks['hooks'][event];assert len(groups)==1 and len(groups[0]['hooks'])==1
    handler=groups[0]['hooks'][0];assert handler['type']=='command'and handler['timeout']==30 and handler['command']==command['command']
    assert groups[0].get('matcher')==(p.MATCHER if event=='PostToolUse'else None)
    argv=command['logical_argv'];assert argv[-1]==registration['connector_config']['path']and argv[-3]==event
    if arm=='H0':
     prefix,encoded=handler['command'].rsplit(' ',1)
     script=base64.b64decode(encoded,validate=True).decode('utf-16-le')
     assert re.findall(r"'([^']*)'",script)==argv and script.endswith('; exit $LASTEXITCODE')
     assert prefix.endswith('-NoProfile -NonInteractive -EncodedCommand')
    definitions.append(dict(arm=arm,event=event,command_sha256=p.hashlib.sha256(handler['command'].encode()).hexdigest(),matcher=groups[0].get('matcher')))
  assert row['user_layer_files_created']==0 and row['trust_state_written']is False
  checks.append('project_'+arm+'_exact_definition_and_status_only_MCP')
 for scope,arms in(('project',('H0','H1','OFF')),('user_mirror',('H0','H1'))):
  for arm in arms:
   folder=p.RAW/('metadata_'+scope+'_'+arm);result=p.read(folder/'RESULT.json');hooks=p.read(folder/'HOOKS.json')
   assert result['status']=='metadata_complete'and result['failure']is None and result['sources_unchanged']
   assert result['cleanup']['pids']==[]and result['cleanup']['accounting']['active_processes']==0 and result['cleanup']['readers_joined']
   assert result['turns']==result['models']==result['trust_grants']==result['Blender_calls']==0
   assert result['home_auth_file_names']==[]and result['existing_auth_or_trust_copied']is False
   home=Path(result['isolated_HOME']);assert not(home/'config.toml').exists()
   entries=[hook for data in hooks['result']['data']for hook in data['hooks']]
   cfg=p.read(folder/'CONFIG.json')['result'];inventory=p.read(folder/'MCP_INVENTORY.json')['result']
   assert inventory['data']==[]and cfg['config']['mcp_servers']=={}
   if scope=='project':
    assert not entries and not(home/'hooks.json').exists()
    layers=[layer for layer in cfg['layers']if layer['name']['type']=='project'];assert len(layers)==1 and layers[0]['disabledReason']
    assert layers[0]['config']['mcp_servers']['human_eye_live']==expected_config['mcp_servers']['human_eye_live']
    assert 'until the project is trusted'in(folder/'STDERR.bin').read_text()
   else:
    assert not(Path(result['workspace'])/'.codex').exists()and len(entries)==2
    wanted={c['event']:c for c in registration['workspaces'][arm]['commands']}
    for entry in entries:
     event={'userPromptSubmit':'UserPromptSubmit','postToolUse':'PostToolUse'}[entry['eventName']]
     assert entry['command']==wanted[event]['command']and entry['matcher']==wanted[event]['matcher']
     assert entry['source']=='user'and entry['sourcePath']==str(home/'hooks.json')
     assert entry['enabled']is True and entry['trustStatus']=='untrusted'
   probe_rows.append({'scope':scope,'arm':arm,'result':p.pin(folder/'RESULT.json'),
    'hooks':p.pin(folder/'HOOKS.json'),'config':p.pin(folder/'CONFIG.json'),'mcp_inventory':p.pin(folder/'MCP_INVENTORY.json'),
    'stderr':p.pin(folder/'STDERR.bin'),'raw_TX':p.pin(folder/'TX.bin'),'raw_RX':p.pin(folder/'RX.bin'),
    'discovered_count':len(entries),'native_entries':[{key:h.get(key)for key in('eventName','matcher','source','currentHash','enabled','trustStatus')}for h in entries]})
   checks.append('native_'+scope+'_'+arm)
 assert len(definitions)==4 and registration['definition_count']==4
 return dict(status='pass',checks=checks,check_count=len(checks),definitions=definitions,probes=probe_rows,
  native_project_review_completed=False,positive_project_MCP_override_proven=False,actual_automatic_turns=0,
  registration=p.pin(p.RAW/'REGISTRATION.json'),config=registration['connector_config'])

if __name__=='__main__':print(json.dumps(verify(),ensure_ascii=False))
