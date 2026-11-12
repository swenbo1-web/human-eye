"""Independent fixed-input hashes and Git binding; no submitted code execution."""
import hashlib
import json
import subprocess
from pathlib import Path

ROOT=Path('D:/hefe')
IMPL=Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
BASE='verification/m4_grooved_rail_consumption_001'
PACK=IMPL/BASE/'cost_review_01'
OUT=Path(__file__).resolve().parent
DELIVERY='ea70339772159e5f0279784ebe18b1bf16e70439'
ORIGINAL='4a90bbe95ef46c6666050ef1a1096fc6719c3b97'
PRODUCT='e836e03f4b3821f869c72ac3e50df5204f28b50f'
QUALITY='e94798714d5d23694f0515f00e9eb083982a2b2f'
checks=[]
def sha(data): return hashlib.sha256(data).hexdigest()
def blob(data): return hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
def git(repo,*args): return subprocess.check_output(['git','-C',str(repo),*args])
def tree(repo,commit,prefix=None):
    args=['ls-tree','-r','-z',commit]+(['--',prefix] if prefix else [])
    rows={}
    for row in git(repo,*args).split(b'\0'):
        if row:
            meta,path=row.split(b'\t',1);rows[path.decode()]=meta.split()[2].decode()
    return rows
def check(name,passed,detail=None): checks.append({'name':name,'passed':bool(passed),'detail':detail})

check('delivery_HEAD',git(IMPL,'rev-parse','HEAD').decode().strip()==DELIVERY)
check('implementation_clean',not git(IMPL,'status','--porcelain').strip())
changes=git(IMPL,'diff','--name-only',ORIGINAL,DELIVERY).decode().splitlines()
check('only_39_new_cost_files',len(changes)==39 and all(x.startswith(BASE+'/cost_review_01/') for x in changes),len(changes))
known={'REVIEW_MANIFEST.json':'6d6c5f98336dc88bc272786556f856fb54ab8ceebfca76732698bf0c06adca3b','ORIGINAL_DATA_INDEX.json':'d8b994c10b1660a968e1273dce7562f02d5f650972f0cf70c30775fe284361ac','COST_REVIEW_READY.json':'c24c14af55155395bd34bcc82f18566df3eb12b18dc7c05d87ab290c1d6ced5a','REPORT.md':'42cc53803edf8f846555e9592d4fca08f785ab17e56bdfa4670722fc5d3114ca'}
check('callback_anchors',all(sha((PACK/k).read_bytes())==v for k,v in known.items()),len(known))
manifest=json.loads((PACK/'REVIEW_MANIFEST.json').read_bytes())
actual={f.relative_to(PACK).as_posix() for f in PACK.rglob('*') if f.is_file()}
listed={r['path'] for r in manifest['files']}|{'REVIEW_MANIFEST.json'}
check('complete_39_file_set',actual==listed and len(actual)==39,len(actual))
bad=[]
for row in manifest['files']:
    data=(PACK/row['path']).read_bytes()
    if len(data)!=row['bytes'] or sha(data)!=row['sha256']:bad.append(row['path'])
check('cost_lengths_SHA',not bad,{'count':len(manifest['files']),'mismatch':bad})
current_tree=tree(IMPL,DELIVERY); original_tree=tree(IMPL,ORIGINAL,BASE)
check('39_cost_disk_bytes_match_Git',all(current_tree.get(BASE+'/cost_review_01/'+n)==blob((PACK/n).read_bytes()) for n in actual),len(actual))
index=json.loads((PACK/'ORIGINAL_DATA_INDEX.json').read_bytes())
rows=index['original_batch_files']; bad=[]
check('original_index_complete',len(rows)==914 and {r['path'] for r in rows}==set(original_tree),len(rows))
for row in rows:
    data=(IMPL/row['path']).read_bytes(); b=blob(data)
    if not (len(data)==row['bytes'] and sha(data)==row['sha256'] and b==row['git_blob']==original_tree[row['path']]==current_tree[row['path']]): bad.append(row['path'])
check('914_originals_bytes_sha_and_two_commits',not bad,{'count':len(rows),'mismatch':bad})
qprefix='verification/m4_grooved_rail_transfer_001'
qtree=tree(IMPL,'9f38e8522cfeea9a580a19baad0e0d823eb1a16f',qprefix)
check('57_qualification_files_unchanged',len(qtree)==57 and all(blob((IMPL/n).read_bytes())==b==current_tree[n] for n,b in qtree.items()),len(qtree))
source=json.loads((IMPL/qprefix/'SOURCE_BINDING.json').read_bytes())
install=Path(source['reused_installation']['install_root']); product_tree=tree(IMPL,PRODUCT)
bad=[]
for row in source['source_manifest']:
    n=row['path']; data=(IMPL/n).read_bytes()
    if not (sha(data)==row['sha256']==sha((install/n).read_bytes()) and blob(data)==product_tree[n]==current_tree[n]):bad.append(n)
check('137_source_install_and_Git',len(source['source_manifest'])==137 and not bad,{'count':len(source['source_manifest']),'mismatch':bad})
sealpath=ROOT/'verification/fixes/20261112_m4_grooved_rail_quality_review/QUALITY_SEAL.json'
sealdata=sealpath.read_bytes();seal=json.loads(sealdata);qroot=tree(ROOT,QUALITY)
check('root_quality_seal_anchor',sha(sealdata)=='a493bd997b2003c595795ad90ae3bc9420e9a2a884a0adcf6225493f880f0c21' and blob(sealdata)==qroot[sealpath.relative_to(ROOT).as_posix()])
bad=[]
for row in seal['files']:
    data=(ROOT/row['path']).read_bytes()
    if not (len(data)==row['bytes'] and sha(data)==row['sha256'] and blob(data)==qroot[row['path']]):bad.append(row['path'])
check('all_sealed_quality_files_unchanged',not bad,{'count':len(seal['files']),'mismatch':bad})
check('author_quality_seal_exact_copy',(PACK/'quality_source/QUALITY_SEAL.json').read_bytes()==sealdata)
initial=json.loads((PACK/'integrity/check_history/initial/CONTRACT_CHECK.json').read_bytes())
final=json.loads((PACK/'integrity/CONTRACT_CHECK.json').read_bytes())
check('failed_and_final_contract_evidence_both_preserved',initial!=final and (PACK/'integrity/check_history/initial/check_contract.py').is_file())
result={'delivery':DELIVERY,'original':ORIGINAL,'product':PRODUCT,'quality_seal_commit':QUALITY,'checks':checks,'passed':sum(r['passed'] for r in checks),'failed':sum(not r['passed'] for r in checks),'new_product_Blender_consumer_API_runs':0,'scope':'Byte identities and history preservation; raw cost, budget and mechanism independently checked in sibling reports.'}
(OUT/'INTEGRITY.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'passed':result['passed'],'failed':result['failed']}))
raise SystemExit(bool(result['failed']))
