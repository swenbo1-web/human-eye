"""Bind reviewed results to actual snapshots, raw stdio and audit records."""
import hashlib,json,subprocess
from pathlib import Path
ROOT=Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
BASE=ROOT/'verification/m4_surface_scan_001'
OUT=Path(__file__).resolve().parent
FILES={};CHECKS=[]
def raw(p):
 b=p.read_bytes();FILES[p.relative_to(ROOT).as_posix()]={'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()};return b
def read(p):return json.loads(raw(p))
def check(label,value):
 CHECKS.append({'name':label,'passed':bool(value)})
 if not value:raise AssertionError(label)
def normalized(snapshot):return {k:v for k,v in snapshot.items() if k not in ('pid','blend_filepath')}
def dump(name,x):(OUT/name).write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n',encoding='utf8',newline='\n')
def main():
 frozen={state:read(BASE/'qualification'/f'{state.upper()}_SNAPSHOT.json') for state in ('base','edit')}
 asset=hashlib.sha256(raw(BASE/'qualification/assembly.blend')).hexdigest()
 for seq in range(1,6):
  path=BASE/'engineering/run_01'/f'sequence_{seq:02d}';data=read(path/'RESULTS.json')
  audits=[json.loads(s) for s in raw(path/'audit.jsonl').splitlines() if s]
  tx=[json.loads(raw(f)) for f in sorted((path/'product').glob('*/TX.bin'))]
  rx=[json.loads(raw(f)) for f in sorted((path/'product').glob('*/RX.bin'))]
  check(f'{seq}.exactly_3_scans',sum(r.get('params',{}).get('name')=='human_eye_scene_observe' for r in tx)==3)
  check(f'{seq}.input_asset',hashlib.sha256(raw(path/'native/input.blend')).hexdigest()==asset)
  for state in ('base','edit'):
   snap=read(path/(state+'_ACTUAL_SNAPSHOT.json'))
   check(f'{seq}.{state}.actual_snapshot',normalized(snap)==normalized(frozen[state]))
  for row in data['business']:
   label=f'{seq}.{row["state"]}';request=row['request'];response=row['response']
   check(label+'.raw_request',sum(r==request for r in tx)==1)
   check(label+'.raw_response',sum(r==response for r in rx)==1)
   events=[a for a in audits if a.get('event')=='observe' and a.get('trace_id')==row['body']['trace_id']]
   check(label+'.raw_diagnostics',len(events)==1 and events[0]['task_work']==row['diagnostics'])
   check(label+'.raw_body',json.loads(response['result']['content'][0]['text'])==row['body'])
 process=BASE/'engineering/process_01';data=read(process/'RESULTS.json')
 check('Process.input_asset',hashlib.sha256(raw(process/'input.blend')).hexdigest()==asset)
 commands=[json.loads(line) for line in raw(process/'Blender_STDIN_UTF8.bin').splitlines() if line]
 check('Process.actual_commands',[r['command'] for r in commands]==['capabilities','capture_surface_scan','shutdown'])
 audits=[json.loads(line) for line in raw(process/'audit.jsonl').splitlines() if line]
 events=[r for r in audits if r.get('event')=='observe' and r.get('trace_id')==data['body']['trace_id']]
 check('Process.raw_diagnostics',len(events)==1 and events[0]['task_work']==data['diagnostics'])
 for rel,metadata in FILES.items():
  content=subprocess.check_output(['git','show','726e88efba548e85eba1eb148b91486470c5d2c1:'+rel],cwd=ROOT)
  check('git:'+rel,hashlib.sha256(content).hexdigest()==metadata['sha256'])
 dump('BINDING_CHECKS.json',CHECKS);dump('BINDING_INPUTS.json',FILES)
 result={'passed':True,'assertions':len(CHECKS),'files_read':len(FILES),'main_actual_snapshots':10,'main_raw_requests_and_responses':15,'main_raw_audit_bindings':15,'process_asset_and_command_binding':True}
 dump('BINDING_RESULTS.json',result);print(json.dumps(result))
if __name__=='__main__':
 try:main()
 except BaseException:
  dump('BINDING_FAILURE.json',CHECKS);raise
