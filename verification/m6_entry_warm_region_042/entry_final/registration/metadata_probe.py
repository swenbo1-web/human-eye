"""Native project-blocking and separate user-mirror discovery, no trust or turns."""
from __future__ import annotations
import argparse
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
spec=importlib.util.spec_from_file_location('_042_final_registration',HERE/'prepare.py')
p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)
CLI=Path('C:/Program Files/WindowsApps/OpenAI.Codex_26.1120.6357.0_x64__2p2nqsd0c76g0/app/resources/codex.exe')
JOB_SOURCE=HERE.parents[2]/'m6_independent_pair_dual_spawn_039/job.py'
JOB_SOURCE=JOB_SOURCE.resolve()

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--scope',choices=('project','user_mirror'),required=True)
 parser.add_argument('--arm',choices=('H0','H1','OFF'),required=True);args=parser.parse_args()
 assert not(args.scope=='user_mirror'and args.arm=='OFF')
 registration=p.read(p.RAW/'REGISTRATION.json');arm=registration['workspaces'][args.arm]
 for key in('hooks','project_config'):p.check(arm[key])
 p.check(registration['connector_config'])
 folder=p.RAW/('metadata_'+args.scope+'_'+args.arm);folder.mkdir(parents=True,exist_ok=False)
 home=folder/'isolated_home';home.mkdir()
 if args.scope=='project':workspace=Path(arm['workspace'])
 else:
  workspace=folder/'empty_workspace';workspace.mkdir()
  # This explicitly separate mirror is a parsing/metadata fixture only. It is
  # never the desktop workspace and no preexisting user configuration is used.
  (home/'hooks.json').write_bytes(Path(arm['hooks']['path']).read_bytes())
 assert not(home/'config.toml').exists()
 spec=importlib.util.spec_from_file_location('_042_final_job',JOB_SOURCE);api=importlib.util.module_from_spec(spec)
 sys.path.insert(0,str(JOB_SOURCE.parent))
 try:spec.loader.exec_module(api)
 finally:sys.path.pop(0)
 job=api.Job();messages=queue.Queue();rawout=[];rawerr=[];tx=[];process=None;failure=None;receipts={};threads=[]
 env=os.environ.copy();env['CODEX_HOME']=str(home)
 removed=[key for key in env if re.search(r'API[_-]?KEY|AUTH[_-]?TOKEN|ACCESS[_-]?TOKEN|SECRET|CREDENTIAL|PASSWORD',key,re.I)]
 for key in removed:env.pop(key,None)
 argv=[str(CLI),'--strict-config','--cd',str(workspace),'app-server','--listen','stdio://']
 def collect(stream,body,notify):
  for line in iter(stream.readline,b''):
   body.append(line)
   if notify:messages.put(line)
 def send(row):
  assert row['method']in('initialize','initialized','hooks/list','config/read','mcpServerStatus/list')
  body=(json.dumps(row,separators=(',',':'))+'\n').encode();tx.append(body);process.stdin.write(body);process.stdin.flush()
 def request(number,method,params):
  send(dict(id=number,method=method,params=params));end=time.monotonic()+12
  while time.monotonic()<end:
   try:line=messages.get(timeout=.1)
   except queue.Empty:
    if process.poll()is not None:raise RuntimeError('app-server exited before '+method)
    continue
   row=json.loads(line)
   if row.get('id')==number:return row
  raise TimeoutError(method)
 try:
  process=subprocess.Popen(argv,cwd=workspace,env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=subprocess.CREATE_NO_WINDOW)
  api.checked(api.assign(job.handle,int(process._handle)))
  for stream,body,notify in((process.stdout,rawout,True),(process.stderr,rawerr,False)):
   t=threading.Thread(target=collect,args=(stream,body,notify),daemon=True);t.start();threads.append(t)
  receipts['initialize']=request(1,'initialize',dict(clientInfo=dict(name='m6_042_final_registration',version='1'),capabilities=dict(experimentalApi=True)))
  send(dict(method='initialized',params={}))
  receipts['hooks']=request(2,'hooks/list',dict(cwds=[str(workspace)]))
  receipts['config']=request(3,'config/read',dict(cwd=str(workspace),includeLayers=True))
  receipts['mcp_inventory']=request(4,'mcpServerStatus/list',dict(detail='toolsAndAuthOnly'))
 except BaseException as exc:failure=dict(type=type(exc).__name__,message=str(exc))
 finally:
  if process:
   try:process.stdin.close()
   except OSError:pass
  end=time.monotonic()+5
  while job.accounting()['active_processes']and time.monotonic()<end:time.sleep(.01)
  if job.accounting()['active_processes']:job.kill()
  if process:process.wait(timeout=5)
  for t in threads:t.join(timeout=2)
  cleanup=dict(accounting=job.accounting(),pids=job.pids(),readers_joined=all(not t.is_alive()for t in threads));job.close()
  for label,rows in(('TX',tx),('RX',rawout),('STDERR',rawerr)):
   with(folder/(label+'.bin')).open('xb')as file:file.write(b''.join(rows))
 refs={name:p.put(folder/(name.upper()+'.json'),value)for name,value in receipts.items()}
 result={'schema':'m6-042-final-native-registration-discovery-v1','status':'metadata_complete'if failure is None else'metadata_failed',
  'scope':args.scope,'arm':args.arm,'registration':p.pin(p.RAW/'REGISTRATION.json'),'source':p.pin(__file__),
  'workspace':str(workspace),'isolated_HOME':str(home),'binary':p.pin(CLI),'argv':argv,'receipts':refs,'cleanup':cleanup,'failure':failure,
  'project_only_desktop_claim':args.scope=='project','user_mirror_is_not_desktop_project':args.scope=='user_mirror',
  'existing_auth_or_trust_copied':False,'home_config_written':False,'trust_grants':0,'turns':0,'models':0,'Blender_calls':0,
  'sources_unchanged':all(p.pin(arm[key]['path'])==arm[key]for key in('hooks','project_config')),
  'home_auth_file_names':[f.name for f in home.iterdir()if re.search('auth|key|token|credential',f.name,re.I)]}
 print(json.dumps(p.put(folder/'RESULT.json',result)))

if __name__=='__main__':main()
