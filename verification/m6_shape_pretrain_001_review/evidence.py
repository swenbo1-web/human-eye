import os
for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'):os.environ[k]='1'
import base64,csv,hashlib,io,json,time
from pathlib import Path
import numpy as np
HERE=Path(__file__).resolve().parent; B=HERE/'snapshot/verification/m6_shape_pretrain_001'
AUTHOR=Path('C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe')
read=lambda p:json.loads(Path(p).read_bytes())
start,cpu=time.perf_counter(),time.process_time(); count=0
manifest=read(HERE/'SNAPSHOT.json'); expected={x['path']:x['sha256'] for x in manifest['records']}
def blob(path):
    global count
    b=Path(path).read_bytes();assert hashlib.sha256(b).hexdigest()==expected[str(path)],str(path);count+=1;return b
def array(path):return np.load(io.BytesIO(blob(path)),allow_pickle=False)
tree=read(HERE.parent/'m6_shape_reselect_001_plan/UPSTREAM_TREE.json'); tree={x['path']:x for x in tree['files']}
sources=read(B/'SOURCE_INDEX.json')['files']; source_by_path={}
for x in sources:
    b=blob(x['path']);r=tree[x['upstream_path']]
    assert len(b)==r['size'] and hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()==r['sha']
    source_by_path[x['upstream_path']]=x['path']
old_matches=0;unmatched=[]
prior_roots=[HERE.parent/x/'snapshot' for x in ('m6_shape_observe_001_review','m6_shape_objective_001_review','m6_shape_opt_001_review','m6_shape_train_001_review')]
for x in read(B/'REUSED_INPUTS.json')['files']:
    path=Path(x['path']);rel=path.relative_to(AUTHOR);b=path.read_bytes()
    assert hashlib.sha256(b).hexdigest()==x['sha256']
    if any((root/rel).is_file() and (root/rel).read_bytes()==b for root in prior_roots):old_matches+=1
    else:unmatched.append(rel.as_posix())
wheel_files=0
for pkg in read(B/'RUNTIME_LOCK.json')['packages']:
    record=Path(pkg['RECORD']['path']);raw=record.read_bytes();assert hashlib.sha256(raw).hexdigest()==pkg['RECORD']['sha256']
    root=record.parent.parent
    for path,h,size in csv.reader(io.StringIO(raw.decode('utf-8'))):
        if not h:continue
        alg,encoded=h.split('=',1);b=(root/path).read_bytes()
        assert base64.urlsafe_b64encode(hashlib.new(alg,b).digest()).decode().rstrip('=')==encoded
        assert len(b)==int(size);wheel_files+=1
cost=read(B/'COSTS.json');available={x['sha256'] for x in manifest['records']};resolved={}
for name,phase in cost['phases'].items():
    digest=phase['controller']['worker_source_sha256'];resolved[name]=digest in available
    assert resolved[name],(name,digest)
t=read(B/'TETRAHEDRON_CHECK.json');clean=array(source_by_path['Dataset/Test/Tetrahedron.npy']).astype(float);noisy=array(source_by_path['Dataset/Test/Tetrahedron_0.005.npy']).astype(float)
ids=np.floor(np.linspace(0,len(clean)-1,128)).astype(int)
candidate=array(t['results']['Tetrahedron_0.005']['candidate_path']);clean_candidate=array(t['results']['Tetrahedron']['candidate_path'])
diagonal=np.linalg.norm(np.ptp(clean,axis=0))
def distances(q):return np.array([np.sqrt(np.min(np.sum((clean-p)**2,axis=1)))/diagonal for p in q])
before,after=distances(noisy[ids]),distances(candidate[ids]);movement=np.linalg.norm(clean_candidate[ids]-clean[ids],axis=1)/diagonal
ratio=float(np.linalg.norm(after)/np.linalg.norm(before))
assert np.allclose(ratio,t['pair_evaluation']['noisy_pointset_RMSE_ratio'],atol=1e-12,rtol=1e-12)
assert np.allclose(np.sqrt(np.mean(movement**2)),t['pair_evaluation']['clean_input_requested_point_movement']['RMSE'],atol=1e-12)
pair_path=AUTHOR/'verification/m6_shape_pretrain_001/private/adapter_qa/pair_evaluation.npz'
with np.load(io.BytesIO(blob(pair_path))) as z:
    for k,v in [('noisy_before_distance',before),('noisy_after_distance',after),('clean_input_movement',movement)]:assert np.allclose(z[k],v,atol=1e-12)
handoff=read(AUTHOR/'verification/m6_shape_pretrain_001/HANDOFF.json')
out={'status':'passed','official_files':len(sources),'old_input_independent_snapshot_matches':old_matches,'old_input_not_in_prior_snapshot':unmatched,'new_dependency_hashed_RECORD_members':wheel_files,'phase_source_hashes_resolved':resolved,'official_noisy_queries':128,'official_clean_queries':128,'official_noise_distance_ratio':ratio,'official_clean_movement_RMSE':float(np.sqrt(np.mean(movement**2))),'handoff_sha256':hashlib.sha256((AUTHOR/'verification/m6_shape_pretrain_001/HANDOFF.json').read_bytes()).hexdigest(),'handoff_callback_corrections':handoff.get('callback_corrections',handoff.get('callback',{})),'model_forwards':0,'training':0,'wall_s':time.perf_counter()-start,'CPU_s':time.process_time()-cpu}
(HERE/'EVIDENCE_RESULTS.json').write_bytes((json.dumps(out,ensure_ascii=False,indent=2)+'\n').encode())
print(json.dumps(out,ensure_ascii=False))
