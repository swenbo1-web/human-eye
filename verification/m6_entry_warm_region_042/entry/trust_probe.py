"""Actual isolated app-server discovery only. No turns, trust writes, or Hook dispatch."""
from __future__ import annotations
import argparse
import base64
import importlib.util
import json
import os
from pathlib import Path
import queue
import re
import subprocess
import sys
import threading
import time

HERE=Path(__file__).resolve().parent
RAW=Path('D:/HumanEye/runs/M6-042-ENTRY-WARM-REGION/entry')
OLD=Path('D:/HumanEye/runs/M6-041-KERNEL-HOOK/delivery')
BINARIES={
 'desktop_bundled':Path('C:/Program Files/WindowsApps/OpenAI.Codex_26.1120.6357.0_x64__2p2nqsd0c76g0/app/resources/codex.exe'),
 'standalone':Path('C:/Users/Administrator/AppData/Local/Programs/OpenAI/Codex/bin/codex.exe')}

def read(path):return json.loads(Path(path).read_bytes())
def pin(path):
 import hashlib
 p=Path(path).resolve();b=p.read_bytes();return dict(path=str(p),bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def save(path,value):
 path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
 with path.open('x',encoding='utf8')as f:json.dump(value,f,indent=2)
 return pin(path)

def prepare(out,arm):
 home=out/'codex_home';workspace=out/'workspace';home.mkdir();workspace.mkdir()
 r3=read(OLD/'install/PINS.json')['arms']['r3']
 assert pin(r3['launcher']['path'])==r3['launcher'] and pin(r3['binding']['path'])==r3['binding']
 template=Path('D:/HumanEye/runs/M3-BVH-DEEP-COMPARE-040/entry_runs/light_matrix_002/r1/prompt_unrelated/direct/connector.json')
 cfg=read(template);cfg.update(project_root=r3['site'],state_file=str(out/'HE_state.json'),audit_file=str(out/'HE_audit.jsonl'))
 cfg['blender']['port']=9
 for key in('base_version','implementation_revision','build_id'):cfg['expected_identity'][key]=r3['identity'][key]
 config=save(out/'connector.json',cfg)
 argv=[r3['dependency_python'],'-I','-B',r3['launcher']['path'],'hook','--agent','codex','--event','UserPromptSubmit','--config',config['path']]
 command=subprocess.list2cmdline(argv)
 if arm=='H0':
  assert all("'"not in value for value in argv)
  script='& '+' '.join("'"+value+"'"for value in argv)+'; exit $LASTEXITCODE'
  encoded=base64.b64encode(script.encode('utf-16-le')).decode('ascii')
  command='C:\\WINDOWS\\System32\\WindowsPowerShell\\v1.0\\powershell.exe -NoProfile -NonInteractive -EncodedCommand '+encoded
 hooks={'description':'042 isolated untrusted registration discovery; never imported existing trust',
  'hooks':{'UserPromptSubmit':[{'hooks':[{'type':'command','command':command,'timeout':30}]}]}}
 save(home/'hooks.json',hooks);save(workspace/'.codex/hooks.json',hooks)
 # Native TOML and compatibility JSON are deliberately isolated discovery
 # probes. No handler is trusted or run; source paths disambiguate recognition.
 (home/'config.toml').write_text('[features]\nhooks = true\n\n[[hooks.user_prompt_submit]]\n[[hooks.user_prompt_submit.hooks]]\ntype = "command"\ncommand = '+json.dumps(command)+'\ntimeout = 30\n',encoding='utf8')
 return home,workspace,dict(arm=arm,config=config,logical_argv=argv,command=command,registration_refs=[pin(home/'config.toml'),pin(home/'hooks.json'),pin(workspace/'.codex/hooks.json')],
  runtime_identity=r3['identity'],launcher=r3['launcher'],binding=r3['binding'])

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--binary',choices=BINARIES,default='desktop_bundled');parser.add_argument('--attempt',default='trust_metadata_001')
 parser.add_argument('--arm',choices=('H0','H1'),default='H1');parser.add_argument('--reuse-registration',type=Path)
 args=parser.parse_args();out=RAW/args.attempt;out.mkdir(parents=True,exist_ok=False)
 if args.reuse_registration:
  prior=args.reuse_registration.resolve();assert prior.is_relative_to(RAW.resolve())
  old=read(prior/'RESULT.json');home=Path(old['CODEX_HOME']);workspace=Path(old['workspace']);definition=old['definition']
  assert definition['arm']==args.arm
  for ref in definition['registration_refs']:assert pin(ref['path'])==ref
 else:home,workspace,definition=prepare(out,args.arm)
 # Only use the old read-only Windows Job helper, never its workload runner.
 job_source=HERE.parents[1]/'m6_independent_pair_dual_spawn_039/job.py'
 spec=importlib.util.spec_from_file_location('_042_job',job_source);api=importlib.util.module_from_spec(spec)
 sys.path.insert(0,str(job_source.parent))
 try:spec.loader.exec_module(api)
 finally:sys.path.pop(0)
 job=api.Job();incoming=queue.Queue();stdout=[];stderr=[];sent=[];process=None;failure=None;rows=[]
 env=os.environ.copy();env['CODEX_HOME']=str(home)
 removed=[key for key in env if re.search(r'API[_-]?KEY|AUTH[_-]?TOKEN|ACCESS[_-]?TOKEN|SECRET|CREDENTIAL|PASSWORD',key,re.I)]
 for key in removed:env.pop(key,None)
 argv=[str(BINARIES[args.binary]),'app-server','--listen','stdio://']
 def collect(stream,items,notify=False):
  for line in iter(stream.readline,b''):
   items.append(line)
   if notify:incoming.put(line)
 def send(value):
  assert value.get('method')in('initialize','initialized','hooks/list')
  body=(json.dumps(value,separators=(',',':'))+'\n').encode();sent.append(body);process.stdin.write(body);process.stdin.flush()
 def response(id):
  end=time.monotonic()+10
  while time.monotonic()<end:
   try:line=incoming.get(timeout=.1)
   except queue.Empty:
    if process.poll()is not None:raise RuntimeError('app-server exited: '+str(process.returncode))
    continue
   row=json.loads(line);rows.append(row)
   if row.get('id')==id:return row
  raise TimeoutError('metadata response deadline')
 threads=[]
 try:
  process=subprocess.Popen(argv,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,cwd=workspace,env=env,creationflags=subprocess.CREATE_NO_WINDOW)
  api.checked(api.assign(job.handle,int(process._handle)))
  for stream,items,notify in((process.stdout,stdout,True),(process.stderr,stderr,False)):
   thread=threading.Thread(target=collect,args=(stream,items,notify),daemon=True);thread.start();threads.append(thread)
  send(dict(id=1,method='initialize',params=dict(clientInfo=dict(name='m6_042_entry_probe',version='1'),capabilities=dict(experimentalApi=True))))
  initialized=response(1);send(dict(method='initialized',params={}))
  send(dict(id=2,method='hooks/list',params=dict(cwds=[str(workspace)])));listed=response(2)
  save(out/'INITIALIZE.json',initialized);save(out/'HOOKS_LIST.json',listed)
 except BaseException as exc:failure=dict(type=type(exc).__name__,message=str(exc))
 finally:
  if process and process.stdin:
   try:process.stdin.close()
   except OSError:pass
  end=time.monotonic()+5
  while job.accounting()['active_processes']and time.monotonic()<end:time.sleep(.01)
  if job.accounting()['active_processes']:job.kill()
  if process:
   try:process.wait(timeout=5)
   except subprocess.TimeoutExpired:failure=failure or dict(type='CleanupTimeout',message='owned app-server did not exit')
  for thread in threads:thread.join(timeout=2)
  cleanup=dict(accounting=job.accounting(),pids=job.pids(),readers_joined=all(not t.is_alive()for t in threads));job.close()
  for name,items in(('TX',sent),('RX',stdout),('STDERR',stderr)):
   with (out/(name+'.bin')).open('xb')as f:f.write(b''.join(items))
 result=dict(status='metadata_complete'if failure is None else'metadata_failed',failure=failure,binary=pin(BINARIES[args.binary]),argv=argv,
  workspace=str(workspace),CODEX_HOME=str(home),definition=definition,cleanup=cleanup,job_source=pin(job_source),
  turns_started=0,model_requests=0,trust_writes=0,Blender_observations=0,automatic_hook_dispatch_tested=False,
  source=pin(__file__),registration_after=[pin(home/'config.toml'),pin(home/'hooks.json'),pin(workspace/'.codex/hooks.json')],
  auth_or_key_files_copied=False,credential_environment_variable_names_removed=removed,
  credential_file_names_present=[p.name for p in home.iterdir()if re.search(r'auth|credential|secret|token',p.name,re.I)])
 print(json.dumps(save(out/'RESULT.json',result)))

if __name__=='__main__':main()
