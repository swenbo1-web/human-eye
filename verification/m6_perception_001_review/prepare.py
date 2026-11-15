import hashlib, json, subprocess, time
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
AUTHOR=Path('C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe')
COMMIT='38fa3e2d01300498aabd43a051876a6f779dab68'
REL='verification/m6_perception_001'
SNAP=HERE/'snapshot'
def sha(b): return hashlib.sha256(b).hexdigest()
def git(*args): return subprocess.check_output(['git',*args],cwd=AUTHOR)
def main():
    start=time.perf_counter();cpu=time.process_time()
    names=git('ls-tree','-r','--name-only',COMMIT,'--',REL).decode().splitlines()
    entries=[]
    for name in names:
        b=git('show',COMMIT+':'+name)
        assert (AUTHOR/name).read_bytes()==b,name
        p=SNAP/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b)
        entries.append({'relative':name,'sha256':sha(b),'bytes':len(b),'kind':'git_public'})
    manifest=json.loads((SNAP/REL/'EVIDENCE_MANIFEST.json').read_bytes())
    for key in ('public_files','private_files'):
        for r in manifest[key]:
            name=REL+'/'+r['path'];b=(AUTHOR/name).read_bytes()
            assert sha(b)==r['sha256'] and len(b)==r['bytes'],name
            if key=='private_files':
                p=SNAP/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b)
                entries.append({'relative':name,'sha256':sha(b),'bytes':len(b),'kind':'new_private'})
    reused=json.loads((SNAP/REL/'REUSED_INPUTS.json').read_bytes())['files']
    priors=[p/'snapshot' for p in ROOT.glob('verification/*_review') if p!=HERE and (p/'snapshot').is_dir()]
    old=[];matches=0
    for r in reused:
        p=Path(r['path']);relative=p.relative_to(AUTHOR).as_posix();b=p.read_bytes()
        assert len(b)==r['bytes'] and sha(b)==r['sha256'],str(p)
        earlier=None
        for prior in priors:
            candidate=prior/relative
            if candidate.is_file() and sha(candidate.read_bytes())==r['sha256']:
                earlier=str(candidate);break
        matches+=earlier is not None
        target=SNAP/relative;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(b)
        old.append({'relative':relative,'sha256':sha(b),'bytes':len(b),'matched_prior':earlier})
    before=git('status','--short').decode()
    changed=git('diff','--name-only','7ae143a6b062ac3c9fedcbf50939b79082884963',COMMIT).decode().splitlines()
    assert all(x.startswith(REL+'/') for x in changed)
    out={'author_commit':COMMIT,'author_tracked_status':before,'changed_files':changed,
         'new_entries':entries,'reused_inputs':old,'new_manifest_records':sum(len(manifest[k]) for k in ('public_files','private_files')),
         'prior_independent_matches':matches,'private_bytes':manifest['private_bytes'],
         'elapsed_wall_s':time.perf_counter()-start,'CPU_s':time.process_time()-cpu}
    (HERE/'SNAPSHOT.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({k:v for k,v in out.items() if k not in ('new_entries','reused_inputs','changed_files')}))
if __name__=='__main__':main()
