"""042 E metadata evidence index. Never trusts/runs a Hook or starts a turn."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
RAW=Path('D:/HumanEye/runs/M6-042-ENTRY-WARM-REGION/entry')
OLD=Path('D:/HumanEye/runs/M6-041-KERNEL-HOOK/delivery')

def read(path):return json.loads(Path(path).read_bytes())
def pin(path):
 p=Path(path).resolve();b=p.read_bytes();return dict(path=str(p),bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def put(path,value):
 with Path(path).open('x',encoding='utf8')as f:json.dump(value,f,ensure_ascii=False,indent=2)
 return pin(path)

def methods(path):
 values=[]
 def walk(x):
  if isinstance(x,dict):
   title=x.get('title')
   if isinstance(title,str)and title.endswith('RequestMethod'):values.extend(x.get('enum',[]))
   for v in x.values():walk(v)
  elif isinstance(x,list):
   for v in x:walk(v)
 walk(read(path));return sorted(set(v for v in values if 'hook'in v.lower()or v.startswith('config/')))

def main():
 # Preserve the prelaunch/mislabel diagnostics individually. Never overwrite
 # their original RESULT, stdout, registration or source identity records.
 for arm in('H0','H1'):
  folder=RAW/f'trust_{arm}_standalone_001'
  if folder.exists()and not(folder/'FAILURE.json').exists():
   put(folder/'FAILURE.json',dict(status='prelaunch_failed',cause='arm label was overwritten by installation descriptor; reuse arm assertion rejected before process creation',
      app_server_started=False,turns=0,models=0,Blender=0))
 for arm in('H0','H1'):
  folder=RAW/f'trust_{arm}_desktop_001'
  if not(folder/'LABEL_FIX.json').exists():
   put(folder/'LABEL_FIX.json',dict(status='diagnostic_excluded_from_final_four',requested_arm=arm,
      actual_command_kind='H1_direct',cause='installation descriptor shadowed arm label; corrected in002',
      original_result_unchanged=pin(folder/'RESULT.json'),automatic_Hook_dispatch=False))
 # Verify all143 actual selected R3 source files using the unchanged041 roster.
 pins=read(OLD/'install/PINS.json');r3=pins['arms']['r3'];binding=read(r3['binding']['path'])
 assert pin(r3['binding']['path'])==r3['binding'] and pin(r3['launcher']['path'])==r3['launcher']
 source_rows=[]
 for row in binding['source_files']:
  path=Path(r3['site'])/row['path'];actual=pin(path);assert actual['sha256']==row['sha256']
  source_rows.append(dict(relative_path=row['path'],bytes=actual['bytes'],sha256=actual['sha256']))
 assert len(source_rows)==143
 install=put(RAW/'R3_SOURCE_CHECK.json',dict(status='pass',identity=r3['identity'],binding=r3['binding'],launcher=r3['launcher'],source_count=143,files=source_rows,
      HumanEye_executed=False))
 cases=[]
 for arm in('H0','H1'):
  same=[]
  for client in('desktop','standalone'):
   folder=RAW/f'trust_{arm}_{client}_002';result=read(folder/'RESULT.json');listed=read(folder/'HOOKS_LIST.json')
   entries=[hook for item in listed['result']['data']for hook in item['hooks']]
   assert result['status']=='metadata_complete'and len(entries)==1
   hook=entries[0];assert hook['enabled']is True and hook['trustStatus']=='untrusted'
   assert result['cleanup']['accounting']['active_processes']==0 and result['cleanup']['pids']==[]and result['cleanup']['readers_joined']
   assert result['auth_or_key_files_copied']is False and result['credential_file_names_present']==[]
   assert result['turns_started']==result['model_requests']==result['trust_writes']==result['Blender_observations']==0
   assert result['definition']['arm']==arm and hook['command']==result['definition']['command']
   assert result['registration_after']==result['definition']['registration_refs']
   assert not Path(result['definition']['config']['path']).with_name('HE_audit.jsonl').exists()
   assert not Path(result['definition']['config']['path']).with_name('HE_state.json').exists()
   same.append((hook['key'],hook['currentHash'],hook['command']))
   cases.append(dict(id=folder.name,arm=arm,surface='desktop_bundled_app_server'if client=='desktop'else'standalone_app_server',
     status='registered_enabled_untrusted_no_turn',result=pin(folder/'RESULT.json'),discovery=pin(folder/'HOOKS_LIST.json'),
     TX=pin(folder/'TX.bin'),RX=pin(folder/'RX.bin'),startup_warning=pin(folder/'STDERR.bin'),
     current_hash=hook['currentHash'],source_scope=hook['source'],source_path=hook['sourcePath'],
     enabled=True,trust_status='untrusted',job_cleanup=result['cleanup'],auth_or_key_files_copied=False,
     credential_file_names_present=[],turns=0,models=0,trust_grants=0,Hook_executions=0,Blender_observations=0))
  assert same[0]==same[1],arm
 diagnostics=[]
 for folder,classification in(
   ('trust_metadata_001','prelaunch_Job_helper_import_failure'),('trust_metadata_002','preliminary_user_hook_discovery'),
   ('trust_H0_desktop_001','arm_label_bug_direct_command_excluded'),('trust_H1_desktop_001','arm_type_bug_excluded'),
   ('trust_H0_standalone_001','prelaunch_arm_assertion'),('trust_H1_standalone_001','prelaunch_arm_assertion')):
  path=RAW/folder;refs={name:pin(path/name)for name in('RESULT.json','FAILURE.json','LABEL_FIX.json')if(path/name).exists()}
  diagnostics.append(dict(id=folder,classification=classification,artifacts=refs,formal_denominator=False))
 schemas={b:dict(client_request=pin(RAW/'host_preflight_001'/b/'schema/ClientRequest.json'),
  relevant_methods=methods(RAW/'host_preflight_001'/b/'schema/ClientRequest.json'))for b in('standalone','desktop_bundled')}
 value=dict(schema='m6-042-E-entry-evidence-v1',status='blocked_pending_native_exact_hook_review',
  contract='c7c00d98:docs/M6_FORMAL_ENTRY_AND_WARM_REGION_042_TASK.md',
  runtime_source_check=install,host_identity=pin(RAW/'host_preflight_001/RESULT.json'),cases=cases,diagnostics=diagnostics,
  schemas=schemas,proven_surfaces=['standalone app-server discovery','desktop-bundled app-server discovery'],
  untested_surfaces=['desktop GUI automatic dispatch','interactive CLI /hooks review','codex exec automatic dispatch'],
  normal_approval=dict(official_documentation='https://learn.chatgpt.com/docs/hooks',
   official_TUI_implementation='https://github.com/openai/codex/blob/main/codex-rs/tui/src/hooks_rpc.rs',
   CLI='/hooks exact definition review in the owning isolated CODEX_HOME',
   desktop='open prepared workspace, complete normal project trust, Review hooks or Settings > Hooks; project identity must be freshly discovered',
   app_server='hooks/list is discovery; generic config/batchWrite is used after review by native TUI, not implicit permission',
   native_human_approval_performed=False),
  formal=dict(unrelated_prompt=dict(status='NOT_RUN',rotation_groups_planned=3,turns=0,valid_timings=0),
   G60_spatial_prompt_and_readonly_PostToolUse=dict(status='NOT_RUN',paired_groups_planned=3,turns=0,observations=0,delivery_proofs=0),
   native_cancel=dict(status='NOT_RUN',attempts=0,started_then_cancelled=0)),
  no_paid_API=True,no_auth_or_key_files_copied=True,no_existing_trust_reused=True,no_trust_bypass=True,
  no_model_turn_started=True,no_Blender_started=True,
  limits=['app-server metadata is not desktop GUI qualification','untrusted inventory is not an observed skipped model turn',
    'metadata timing is not Hook or model response timing','prepared connector uses unused port9 and is not a G60 observation setup'])
 ref=put(RAW/'DELIVERY_INDEX.json',value)
 # Git copy contains only public metadata and local evidence descriptors, no
 # configuration/credentials, raw event bodies, or encoded commands.
 public=dict(value)
 for case in public['cases']:case.pop('source_path')
 public['raw_index']=ref
 put(HERE/'INDEX.json',public)
 print(json.dumps(ref))

if __name__=='__main__':main()
