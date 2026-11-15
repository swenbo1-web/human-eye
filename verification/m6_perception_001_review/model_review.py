"""Independent functional encoder/head and exact fixed training replay."""
import os
for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'):os.environ[k]='1'
import hashlib,json,time,importlib.util,sys
from pathlib import Path
from collections import defaultdict
import numpy as np
import torch
from torch import nn
import torch.nn.functional as F
HERE=Path(__file__).resolve().parent;SNAP=HERE/'snapshot';P=SNAP/'verification/m6_perception_001';AUTHOR=Path('C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe')
counts=defaultdict(int);diffs=defaultdict(float)
def local(s):return SNAP/Path(s).relative_to(AUTHOR)
def j(p):return json.loads(Path(p).read_bytes())
def z(p):
 with np.load(p,allow_pickle=False) as a:return {k:a[k] for k in a.files}
def check(k,a,b,atol=2e-5,rtol=2e-5):
 counts[k]+=1
 if isinstance(a,torch.Tensor):a=a.detach().numpy()
 if isinstance(b,torch.Tensor):b=b.detach().numpy()
 a,b=np.asarray(a),np.asarray(b)
 assert a.shape==b.shape,(k,a.shape,b.shape)
 if a.dtype.kind in 'biu' and b.dtype.kind in 'biu':assert np.array_equal(a,b),k
 else:
  assert np.allclose(a,b,rtol=rtol,atol=atol,equal_nan=True),(k,float(np.nanmax(np.abs(a-b))))
  if a.size and np.isfinite(a-b).any():diffs[k]=max(diffs[k],float(np.nanmax(np.abs(a-b))))
def digest(state):
 h=hashlib.sha256()
 for name in sorted(state):
  t=state[name].detach().cpu().contiguous();m=json.dumps({'name':name,'dtype':str(t.dtype),'shape':list(t.shape)},sort_keys=True,separators=(',',':')).encode();b=t.numpy().tobytes()
  h.update(len(m).to_bytes(8,'little'));h.update(m);h.update(len(b).to_bytes(8,'little'));h.update(b)
 return h.hexdigest()
def encoder(x,state):
 for i in range(1,6):
  x=F.conv1d(x,state[f'conv{i}.weight'],state[f'conv{i}.bias'])
  x=F.batch_norm(x,state[f'bn{i}.running_mean'],state[f'bn{i}.running_var'],state[f'bn{i}.weight'],state[f'bn{i}.bias'],training=False,eps=1e-5)
  x=F.relu(x)
 return x.max(dim=2).values
class Head(nn.Module):
 def __init__(self):
  super().__init__();self.network=nn.Sequential(nn.Linear(1024,64),nn.GELU(),nn.Linear(64,1))
 def forward(self,x):return self.network(x).reshape(-1)
def main():
 start=time.perf_counter();cpu=time.process_time();torch.set_num_threads(1);torch.set_num_interop_threads(1);torch.use_deterministic_algorithms(True)
 env=j(SNAP/'verification/m6_shape_pretrain_001/ENVIRONMENT.json')
 for path in env['dependency_paths']:sys.path.insert(0,path)
 official=SNAP/'verification/m6_shape_pretrain_001/private/pointfilter'
 spec=importlib.util.spec_from_file_location('fixed_official_pca',official/'Pointfilter_Utils.py');util=importlib.util.module_from_spec(spec);spec.loader.exec_module(util)
 official_state=torch.load(official/'model_full_ae.pth',map_location='cpu',weights_only=True)['state_dict']
 enc={k.removeprefix('encoder.'):v for k,v in official_state.items() if k.startswith('encoder.')}
 identity=j(P/'MODEL_IDENTITY.json');assert digest(enc)==identity['encoder_initial_tensor_sha256']
 for name in ['encoder_initial.pth','encoder_after_features.pth','encoder_after_head_training.pth']:
  state=torch.load(P/'private/model'/name,weights_only=True)
  for k,v in enc.items():check('frozen_encoder_state',state[k],v,0,0)
  assert digest(state)==digest(enc)
 fi=j(P/'FEATURES.json');pred={r['id']:r for r in j(P/'PREDICTIONS.json')['cases']};white={r['id']:r for r in j(P/'INPUT_WHITELIST.json')['cases']}
 source={};features={};metadata={};feature_count=0;replays=0;geometry_queries=0;sampling_queries=0
 for row in fi['cases']:
  w=white[row['id']];a=z(local(row['path']));detail=z(local(row['detail_path']));features[row['id']]=a['features'];metadata[row['id']]=a
  mapping=z(local(w['mapping_path']));graph=z(local(w['graph_path']));context=mapping['context_source_ids'];fc=np.flatnonzero(graph['free_mask']);fc=fc[np.argsort(context[fc])]
  check('free_context',a['free_context_ids'],fc);check('free_source',a['free_source_ids'],context[fc]);check('query_ids',detail['query_source_ids'],a['free_source_ids'])
  if w['source'] not in source:source[w['source']]=z(local(w['snapshot']['path']))['vertices']
  v=source[w['source']].copy();v[context]=np.load(local(w['observed']['path']),allow_pickle=False)
  radius=.05*np.linalg.norm(v.max(axis=0)-v.min(axis=0));check('radius',detail['radius'],radius,1e-12,1e-12)
  rng=np.random.RandomState(1729);n=len(fc);selected=sorted({0,n//2,n-1});reconstructed=[];selected_valid=[]
  for i,qid in enumerate(a['free_source_ids']):
   lo,hi=detail['neighbor_offsets'][i:i+2];ids=detail['neighbor_source_ids'][lo:hi];check('neighborhood_count',len(ids),detail['neighbor_count'][i]);sampling_queries+=1
   if len(ids)<3:
    check('unavailable_query',detail['query_status_codes'][i],1);check('unavailable_feature',a['features'][i],np.zeros(1024));continue
   chosen=rng.choice(len(ids),size=500,replace=len(ids)<=500);check('sampled_IDs',detail['sampled_source_ids'][i],ids[chosen])
   if i in selected:
    allids=np.flatnonzero(np.sum((v-v[qid])**2,axis=1)<=radius**2)
    check('brute_radius_neighbors',np.sort(ids),allids);geometry_queries+=1
    aligned,inv=util.pca_alignment(v[ids]-v[qid]);check('official_PCA_inverse',detail['pca_inverse'][i],inv,1e-9,1e-9)
    points=(aligned[chosen]/radius).astype(np.float32);check('source_normalized_points',detail['normalized_points'][i],points,1e-6,1e-6)
    reconstructed.append(points);selected_valid.append(i)
  if reconstructed:
   tensor=torch.from_numpy(np.stack(reconstructed)).transpose(1,2).contiguous()
   with torch.inference_mode():out=encoder(tensor,enc).numpy()
   check('encoder_features',a['features'][selected_valid],out);replays+=len(selected_valid)
  check('valid_mask',a['valid_mask'],detail['query_status_codes']==0)
  feature_count+=n
 norms=z(P/'private/model/normalization.npz');train=j(P/'TRAIN_LOG.json');ids=train['case_ids'];total=sum(len(features[i]) for i in ids)
 mean=sum(np.sum(features[i],axis=0,dtype=np.float64) for i in ids)/total
 var=sum(np.sum((features[i].astype(float)-mean)**2,axis=0) for i in ids)/total
 std=np.sqrt(var);divisor=np.where(std<1e-6,1.,std)
 for k,value in [('mean',mean),('standard_deviation',std),('divisor',divisor)]:check('development_normalization_'+k,norms[k],value,1e-12,1e-12)
 final=torch.load(P/'private/model/head_final.pth',weights_only=True);initial=torch.load(P/'private/model/head_initial.pth',weights_only=True)
 assert digest(final['state_dict'])==identity['head_final_tensor_sha256']
 weights=final['state_dict'];prediction_points=0
 with torch.inference_mode():
  for case_id,x in features.items():
   t=torch.from_numpy(((x.astype(float)-mean)/divisor).astype(np.float32))
   h=F.gelu(F.linear(t,weights['network.0.weight'],weights['network.0.bias']),approximate='none')
   logits=F.linear(h,weights['network.2.weight'],weights['network.2.bias']).reshape(-1).numpy();scores=torch.sigmoid(torch.from_numpy(logits)).numpy()
   valid=metadata[case_id]['valid_mask'];logits[~valid]=0;scores[~valid]=0;p=z(local(pred[case_id]['path']))
   check('all_head_logits',p['logits'],logits);check('all_head_scores',p['scores'],scores);prediction_points+=len(x)
 X=torch.from_numpy(np.concatenate([((features[i].astype(float)-mean)/divisor).astype(np.float32) for i in ids]))
 targets=[];sizes=[]
 for i in ids:
  w=white[i];observed=local(w['observed']['path']);label=z(observed.parents[1]/'labels'/(observed.stem+'.npz'))['damaged_mask'][metadata[i]['free_context_ids']].astype(np.float32)
  targets.append(label);sizes.append(len(label))
 pi=float(np.mean([v.mean(dtype=np.float64) for v in targets]));posweight=(1-pi)/pi;check('case_prior',pi,train['case_equal_pi'],1e-12,1e-12);check('positive_weight',posweight,train['positive_weight'],1e-12,1e-12)
 y=torch.from_numpy(np.concatenate(targets));offset=np.r_[0,np.cumsum(sizes)];trajectory=z(P/'private/training/sampling.npz');sampler=np.random.RandomState(1729)
 pairs=np.zeros((1200,1024,2),np.int32)
 for step in range(1200):
  for b in range(1024):
   c=sampler.randint(len(ids));pairs[step,b]=(c,sampler.randint(sizes[c]))
 check('all_sampling_case_pairs',trajectory['case_index'],pairs[:,:,0]);check('all_sampling_row_pairs',trajectory['F_row_index'],pairs[:,:,1])
 torch.manual_seed(1729);model=Head()
 for k,v in initial['state_dict'].items():check('seed_initial_state',model.state_dict()[k],v,0,0)
 model.load_state_dict(initial['state_dict']);optimizer=torch.optim.AdamW(model.parameters(),lr=.001,weight_decay=.0001,betas=(.9,.999),eps=1e-8,foreach=False)
 optimizer.load_state_dict(initial['optimizer']);losses=[];replay_start=time.perf_counter()
 for step in range(1200):
  index=offset[pairs[step,:,0]]+pairs[step,:,1]
  optimizer.zero_grad(set_to_none=True);logits=model(X[index]);loss=F.binary_cross_entropy_with_logits(logits,y[index],pos_weight=torch.tensor(posweight,dtype=torch.float32))
  loss.backward();optimizer.step();actual=float(loss.detach());losses.append(actual);check('training_step_loss',actual,train['steps'][step]['loss'],1e-7,1e-7)
 for k,v in model.state_dict().items():check('replayed_final_parameter',v,final['state_dict'][k],1e-7,1e-7)
 actualopt=optimizer.state_dict()
 for pid,state in actualopt['state'].items():
  for k,v in state.items():check('replayed_optimizer_'+k,v,final['optimizer']['state'][pid][k],1e-7,1e-7)
 replay_digest=digest(model.state_dict());assert replay_digest==identity['head_final_tensor_sha256']
 out={'status':'passed','assertions':sum(counts.values()),'checks':dict(counts),'max_differences':dict(diffs),'coverage':{'cases':len(fi['cases']),'F_points':feature_count,'encoder_replay_queries':replays,'brute_radius_queries':geometry_queries,'saved_sampling_queries':sampling_queries,'head_predictions':prediction_points,'training_pairs':pairs.shape[0]*pairs.shape[1],'replayed_training_steps':1200},
      'head_final_replay_tensor_sha256':replay_digest,'training_replay_wall_s':time.perf_counter()-replay_start,'wall_s':time.perf_counter()-start,'CPU_s':time.process_time()-cpu,
      'candidate_training_runs':0,'exact_existing_training_replays':1,'decoder_forwards':0,'encoder_training_updates':0,'scope':'Independent functional encoder/head plus one exact recorded training verification; not a new search, candidate or deployment'}
 (HERE/'MODEL_RESULTS.json').write_bytes((json.dumps(out,indent=2)+'\n').encode());print(json.dumps({k:v for k,v in out.items() if k not in ('checks','max_differences')}))
if __name__=='__main__':main()
