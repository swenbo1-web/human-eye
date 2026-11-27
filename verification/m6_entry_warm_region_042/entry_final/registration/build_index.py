"""Freeze public final-registration summary after read-only invariants pass."""
import importlib.util
import json
from pathlib import Path
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('_042_registration_verify',HERE/'verify.py')
v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)

def main():
 report=v.verify();r=v.p.read(v.p.RAW/'REGISTRATION.json')
 direct=v.p.FINAL/'direct/preflight_02/RESULT.json'
 value={'schema':'m6-042-final-registration-index-v1','status':'prepared_pending_native_project_review',
  'registration':report['registration'],'protocol':r['protocol'],'connector_config':r['connector_config'],
  'workspaces':{arm:{key:row[key]for key in('workspace','scope','hooks','project_config','registered_command_count')}for arm,row in r['workspaces'].items()},
  'readonly_tool':r['readonly_tool'],'mcp':r['mcp'],'runtime':r['runtime'],'binding':r['binding'],'launcher':r['launcher'],
  'check_count':report['check_count'],'definitions':report['definitions'],'probes':report['probes'],
  'direct_preflight':v.p.pin(direct)if direct.exists()else None,
  'prepared_handlers':4,'required_native_exact_definition_reviews':4,'actual_reviewed':0,
  'project_handlers':{'H0':2,'H1':2,'OFF':0},'no_home_hooks_in_formal_workspaces':True,
  'no_inline_TOML_Hooks':True,'user_mirrors_are_not_formal_configuration':True,
  'native_project_MCP_override_status':'NOT_PROVEN_before_normal_project_trust',
  'required_before_any_formal_turn':['actual project layer enabled by normal trust','project-scoped H0/H1 exact definitions reviewed natively',
   'native hooks inventory exactly2 enabled project handlers for selectedarm and0 extraHumanEye handlers;OFF0',
   'native effective MCP command uses bound041R3 serve+sharedCONFIG and status-only allowlist',
   'native actual canonical tool inventory unambiguous; expected R3 runtime+48142 identity shown before formal turn',
   'current owned G60 ready receipt matches frozen asset/port/config;completed preflight is not a live endpoint'],
  'models_or_automatic_Hook_turns':0,'trust_grants':0,'Blender_started_by_registration':False,
  'failure_originals':v.p.pin(v.p.RAW/'failures/prepare_001/FAILURE.json'),
  'official_docs':['https://learn.chatgpt.com/docs/hooks','https://learn.chatgpt.com/docs/config-file/config-reference'],
  'source_refs':{p.name:v.p.pin(p)for p in HERE.glob('*.py')}}
 raw=v.p.put(v.p.RAW/'INDEX.json',value)
 public=dict(value,raw_index=raw);v.p.put(HERE/'INDEX.json',public)
 print(json.dumps(raw))

if __name__=='__main__':main()
