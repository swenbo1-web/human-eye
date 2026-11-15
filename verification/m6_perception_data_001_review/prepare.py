import hashlib,json,subprocess,time
from pathlib import Path
HERE=Path(__file__).resolve().parent;SNAP=HERE/'snapshot'
AUTHOR=Path('C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe')
REL='verification/m6_perception_data_001'
COMMIT='a463116f52cc954812cfb6f54513ecfea0eb46ef'
def sha(b):return hashlib.sha256(b).hexdigest()
def git(*args):return subprocess.check_output(['git',*args],cwd=AUTHOR)
def main():
 start=time.perf_counter();cpu=time.process_time();records=[]
 public=git('ls-tree','-r','--name-only',COMMIT,'--',REL).decode().splitlines()
 for name in public:
  b=git('show',COMMIT+':'+name);assert (AUTHOR/name).read_bytes()==b,name
  target=SNAP/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(b)
  records.append({'path':name,'bytes':len(b),'sha256':sha(b),'kind':'git_public'})
 m=json.loads((SNAP/REL/'MANIFEST.json').read_bytes())
 for kind in ['public_files','private_files']:
  for r in m[kind]:
   name=REL+'/'+r['path'];b=(AUTHOR/name).read_bytes()
   assert sha(b)==r['sha256'] and len(b)==r['bytes'],name
   if kind=='private_files':
    target=SNAP/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(b)
    records.append({'path':name,'bytes':len(b),'sha256':sha(b),'kind':'private'})
 for name in ['PLAN.json','PLAN_FREEZE.json','SOURCE_INDEX.json','SPLIT.json','ORIENTATION_SOURCE.json']:
  assert git('show','1d690ec2540be2ea86dc80037b2125ba63792919:'+REL+'/'+name)==(SNAP/REL/name).read_bytes(),name
 assert subprocess.run(['git','merge-base','--is-ancestor','1d690ec2540be2ea86dc80037b2125ba63792919',COMMIT],cwd=AUTHOR).returncode==0
 changed=git('diff','--name-only','38fa3e2d01300498aabd43a051876a6f779dab68',COMMIT).decode().splitlines()
 assert all(x.startswith(REL+'/') for x in changed)
 out={'status':'passed','author_commit':COMMIT,'public_files':len(public),'manifest_records':sum(len(m[k]) for k in ['public_files','private_files']),
      'private_bytes':sum(r['bytes'] for r in m['private_files']),'author_tracked_status':git('status','--short').decode(),'records':records,
      'wall_s':time.perf_counter()-start,'CPU_s':time.process_time()-cpu}
 (HERE/'SNAPSHOT.json').write_bytes((json.dumps(out,ensure_ascii=False,indent=2)+'\n').encode());print(json.dumps({k:v for k,v in out.items() if k!='records'}))
if __name__=='__main__':main()
