"""Independent offline OPT1 byte and source binding audit."""
from pathlib import Path
import base64, csv, hashlib, io, json, subprocess, zipfile

ROOT=Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
OUT=Path(__file__).resolve().parent
PREFIX='verification/m4_surface_scan_001_opt1'
BASE=ROOT/PREFIX
DELIVERY='860b87138d40de9cc08b01c947dd864d58da9295'
PRODUCT='c1cb2da32034e056a270384e691a2cde8dddbc0d'
OLD='c6355a01a4c6ee204a0d676cd9309f02428fe3ba'
OLD_DELIVERY='726e88efba548e85eba1eb148b91486470c5d2c1'
checks=[]
def sha(b):return hashlib.sha256(b).hexdigest()
def read(p):return json.loads(p.read_bytes())
def git(*a):return subprocess.check_output(['git',*a],cwd=ROOT)
def blob(b):return hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()
def tree(commit,*paths):
    return {n.decode():m.split()[2].decode() for row in git('ls-tree','-r','-z',commit,'--',*paths).split(b'\0') if row for m,n in [row.split(b'\t',1)]}
def check(n,v,detail=None):
    checks.append(dict(name=n,passed=bool(v),detail=detail))
    assert v,n
def manifest(p,commit,anchor=None):
    if anchor:check(p.name+'_anchor',sha(p.read_bytes())==anchor)
    m=read(p);rows=m['files'];entries=tree(commit,'verification')
    bad=[]
    for row in rows:
        path=ROOT/row['path'];b=path.read_bytes()
        if len(b)!=row['bytes'] or sha(b)!=row['sha256'] or blob(b)!=entries.get(row['path']):bad.append(row['path'])
    check(str(p.relative_to(ROOT))+'_bytes_Git',not bad,dict(count=len(rows),bad=bad))
    return m
def main():
    check('HEAD',git('rev-parse','HEAD').decode().strip()==DELIVERY)
    check('clean_tracked_tree',not git('status','--porcelain').strip())
    m=manifest(BASE/'DELIVERY_MANIFEST.json',DELIVERY,'3f0c07fd4637050cfc6ece32acc05e0a8e22d813d3b63d48c9fc45f20ddc757d')
    names={r['path'] for r in m['files']}
    check('1110_unique_files',len(names)==len(m['files'])==1110)
    check('complete_delivery_file_set',set(tree(DELIVERY,PREFIX))==names|{PREFIX+'/DELIVERY_MANIFEST.json'})
    check('total_manifest_bytes',sum(r['bytes'] for r in m['files'])==m['bytes']==121171174)
    old_base=ROOT/'verification/m4_surface_scan_001'
    manifest(old_base/'DELIVERY_MANIFEST.json',OLD_DELIVERY,'d2258591204d8215414e0f9d1952484fbbb2894ffb799ab7ce4db9d1a98eea82')
    check('input_commit_unchanged',not git('diff','--name-only','96fce78b98cb749885792112e039a406744d282b',DELIVERY,'--','verification/m4_surface_scan_001/qualification').strip())
    ready=read(BASE/'OPT1_READY.json')
    check('ready_derived_anchors',all(sha((BASE/n).read_bytes())==h for n,h in ready['review_files'].items()),len(ready['review_files']))
    for label,path,commit in [('A',old_base,OLD),('B',BASE,PRODUCT)]:
        identity=read(path/'CANDIDATE_SOURCE.json')['identity'];rows=identity['source_files']
        installation=read(path/'installation/run_01/READY.json');site=Path(installation['install_root'])
        wheels=list((path/'installation/run_01/bundle').glob('*.whl'))
        check(label+'_wheel_unique',len(wheels)==1)
        check(label+'_wheel_anchor',sha(wheels[0].read_bytes())==installation['wheel_sha256'])
        expected=tree(commit,*[r['path'] for r in rows]);bad=[];count=0
        with zipfile.ZipFile(wheels[0]) as z:
            for row in rows:
                n=row['path'];b=z.read(n)
                if sha(b)!=row['sha256'] or blob(b)!=expected.get(n) or (site/n).read_bytes()!=b or (label=='B' and (ROOT/n).read_bytes()!=b):bad.append(n)
            record=next(n for n in z.namelist() if n.endswith('.dist-info/RECORD'))
            for name,digest,size in csv.reader(io.StringIO(z.read(record).decode())):
                if not digest:check(label+'_record_unhashed',name==record);continue
                b=z.read(name);method,want=digest.split('=',1)
                check(label+'_wheel_member_'+name,method=='sha256' and len(b)==int(size) and base64.urlsafe_b64encode(hashlib.sha256(b).digest()).decode().rstrip('=')==want);count+=1
        check(label+'_138_commit_wheel_install',len(rows)==138 and not bad,bad)
        digest={'base_version':identity['base_version'],'implementation_revision':identity['implementation_revision'],'files':rows}
        aggregate=sha(json.dumps(digest,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode())
        check(label+'_aggregate',aggregate==identity['source_sha256']==installation['source_sha256'])
        if label=='B':check('B_callback_source',aggregate=='c4832b1a1ced9438f904e25a431e2327c2d7532e2f4efbb34e34ce58a7ed1943')
    check('product_unchanged_after_freeze',not git('diff','--name-only',PRODUCT,DELIVERY,'--','human_eye_plugin').strip())
    check('no_pyc_committed',not any(n.endswith('.pyc') for n in names))
    return dict(passed=True,delivery=DELIVERY,product=PRODUCT,checks=checks,new_Blender_consumer_API_runs=0)

if __name__=='__main__':
    OUT.mkdir(parents=True,exist_ok=True)
    try:result=main()
    except Exception as exc:
        (OUT/'FAILED.json').write_text(json.dumps(dict(error=repr(exc),checks=checks),indent=2)+'\n',encoding='utf8');raise
    (OUT/'INTEGRITY.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf8',newline='\n')
    print(json.dumps(dict(passed=True,checks=len(checks))))
