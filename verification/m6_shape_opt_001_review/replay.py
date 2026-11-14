"""Frozen score/candidate replay and independent NumPy equations; no updates."""
import os
for name in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):os.environ[name]='1'
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
import torch

HERE=Path(__file__).resolve().parent
BASE=HERE/'snapshot/verification/m6_shape_opt_001'
PRIOR=HERE.parent/'m6_shape_train_001_review/snapshot/verification/m6_shape_train_001'
DATA=HERE.parent/'m6_shape_data_001_review/snapshot/verification/m6_shape_data_001'
AUTHOR=Path('C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe')
sys.path.insert(0,str(BASE));sys.path.append(str(PRIOR))
from model import ResidualExpert, gate_prediction, optimization_loss
from data_io import load_sample, forward_arrays, candidate_from_prediction, batch_samples
torch.set_num_threads(1);torch.set_num_interop_threads(1);torch.use_deterministic_algorithms(True)
weight=BASE/'private/weights/step_1200.pt'
assert hashlib.sha256(weight.read_bytes()).hexdigest()=='a82f2d5d4f27e1e7f4be6cf74999f4a488edf5fdcbf38f92fed9264046a153ff'
checkpoint=torch.load(weight,map_location='cpu',weights_only=True)
assert checkpoint['step']==1200 and checkpoint['seed']==1729 and checkpoint['parameters']==6339
model=ResidualExpert();model.load_state_dict(checkpoint['model']);model.eval()
assert sum(p.numel() for p in model.parameters())==6339
initial=torch.load(BASE/'private/weights/step_0000.pt',map_location='cpu',weights_only=True)['model']
previous=torch.load(PRIOR/'private/weights/step_0000.pt',map_location='cpu',weights_only=True)['model']
assert len(previous)==20 and all(torch.equal(v,initial[k]) for k,v in previous.items())
assert all(torch.count_nonzero(v)==0 for k,v in initial.items() if k.startswith('localization_head.'))
assert (BASE/'private/normalization.npz').read_bytes()==(PRIOR/'private/normalization.npz').read_bytes()
with np.load(BASE/'private/normalization.npz',allow_pickle=False) as z:stats={k:z[k] for k in z.files}
train=json.loads((DATA/'DATASET_INDEX.json').read_bytes())['cases']
val=[c for c in json.loads((PRIOR/'PUBLIC_DATASET_INDEX.json').read_bytes())['cases'] if c['purpose']=='validation']
cases={c['id']:c for c in train+val}
saved={c['id']:c for c in json.loads((BASE/'RESULTS.json').read_bytes())['model_cases']}
cal=json.loads((BASE/'LOC_CALIBRATION.json').read_bytes());tau=cal['tau']
def local(p):return HERE/'snapshot'/Path(p).relative_to(AUTHOR)
def sample_for(cid,labels=False):
    c=cases[cid];root=DATA/'private/patches' if c['purpose']=='development_train_pool' else PRIOR/'private/public_data/patches'
    return load_sample(c,root,with_labels=labels)
def inputs(sample):return tuple(torch.from_numpy(np.ascontiguousarray(x)) for x in forward_arrays(sample,stats))

cal_replayed=[]
for control in cal['cases']:
    sample=sample_for(control['id'])
    with torch.inference_mode():u,z,p=model.forward_components(*inputs(sample))
    a=p.numpy()[sample['graph']['free_mask']]
    assert np.array_equal(a,np.load(local(control['scores_path']),allow_pickle=False))
    cal_replayed.append(a)
all_scores=np.concatenate(cal_replayed)
assert float(np.quantile(all_scores,.995,method='linear'))==cal['q995']

params={k:v.detach().numpy().astype(np.float64) for k,v in model.state_dict().items()}
def lin(x,name):return x@params[name+'.weight'].T+params[name+'.bias']
def mlp(x,name):
    a=lin(x,name+'.0');return lin(a/(1+np.exp(-a)),name+'.2')
def equations(values):
    node,edge,pos,normal,ij,free=values
    node,edge,pos,normal=[a.astype(np.float64) for a in (node,edge,pos,normal)]
    i,j=ij;degree=np.maximum(np.bincount(i,minlength=len(node)),1)[:,None]
    h0=mlp(node,'node_encoder');h=h0
    for _ in range(12):
        message=mlp(np.concatenate([h[i],h[j],edge],axis=1),'edge_mlp')
        agg=np.zeros_like(h);np.add.at(agg,i,message);agg/=degree
        h=h+.1*mlp(np.concatenate([h,agg,h0],axis=1),'node_update')
        mean=h.mean(axis=1,keepdims=True);variance=((h-mean)**2).mean(axis=1,keepdims=True)
        h=(h-mean)/np.sqrt(variance+1e-5)*params['layer_norm.weight']+params['layer_norm.bias']
    combined=np.concatenate([h,h0],axis=1)
    alpha=mlp(combined,'alpha_head');beta=lin(message,'beta_head')
    vec=np.zeros_like(pos);np.add.at(vec,i,beta*(pos[j]-pos[i]))
    u=alpha*normal+vec/degree;u[~free]=0
    z=lin(combined,'localization_head')[:,0];p=1/(1+np.exp(-z))
    return u,z,p

chosen=['Yanyite_patch_07/sample_01','Richie_patch_00/sample_06','Chipow_patch_03/sample_00',
        'Stanford_Armadillo_patch_00/sample_00','Stanford_Armadillo_patch_00/sample_01','Stanford_Armadillo_patch_00/sample_07']
rows=[];samples=[]
for cid in chosen:
    sample=sample_for(cid,labels=True);samples.append(sample)
    with torch.inference_mode():
        u,z,p=model.forward_components(*inputs(sample));d=gate_prediction(u,p,inputs(sample)[5],tau)
    comp=np.load(local(saved[cid]['component_path']),allow_pickle=False)
    assert all(np.array_equal(x.numpy(),comp[k]) for x,k in [(u,'u'),(z,'z'),(p,'p'),(d,'prediction_normalized')])
    actual=candidate_from_prediction(sample,d.numpy());expected=np.load(local(saved[cid]['candidate_path']),allow_pickle=False)
    assert np.array_equal(actual.view(np.uint64),expected.view(np.uint64))
    nu,nz,np_=equations(forward_arrays(sample,stats))
    ud=float(np.max(np.linalg.norm(nu-u.numpy(),axis=1)));pd=float(np.max(np.abs(np_-p.numpy())))
    assert ud<4e-6 and pd<3e-6,(cid,ud,pd)
    rows.append({'id':cid,'components_and_candidate_bitwise_equal':True,'numpy_u_max_vector_difference':ud,'numpy_score_max_difference':pd})

forward,supervision=batch_samples(samples,stats)
with torch.inference_mode():
    u,z,p=model.forward_components(*forward)
    loss,components=optimization_loss(u,z,p,**supervision)
u,z,p=[x.numpy().astype(np.float64) for x in (u,z,p)]
target=supervision['target'].numpy().astype(np.float64);soft=u*p[:,None];e=soft-target
i,j=forward[4].numpy();gids=supervision['graph_index'].numpy();error=np.sum(e*e,axis=1);ed=np.sum((e[j]-e[i])**2,axis=1)
losses=[]
for g in range(len(samples)):
    A=supervision['allowed_mask'].numpy()&(gids==g);S=supervision['damaged_mask'].numpy()&(gids==g);N=supervision['normal_free_mask'].numpy()&(gids==g)
    point=error[A].mean() if not S.any() else .2*error[A].mean()+.4*error[S].mean()+.4*error[N].mean()
    conditional=0 if not S.any() else .4*np.mean(np.sum((u[S]-target[S])**2,axis=1))
    loc=np.logaddexp(0,z[N]).mean() if not S.any() else .5*(np.logaddexp(0,-z[S]).mean()+np.logaddexp(0,z[N]).mean())
    losses.append(float(point+.05*ed[gids[i]==g].mean()+conditional+.05*loc))
assert np.isclose(np.mean(losses),float(loss),rtol=2e-6,atol=1e-8)
out={'author_commit':'36694d0e3730a60b0611376b017f978f809a79c0','weight_sha256':hashlib.sha256(weight.read_bytes()).hexdigest(),
     'parameters':6339,'original_initial_tensors_bitwise_equal':20,'normalization_bytes_equal':True,
     'control_score_forward_replays':33,'score_points':10405,'original_tau_recomputed':tau,'new_threshold_selections':0,
     'representative_replays':rows,'numpy_six_graph_loss':float(np.mean(losses)),'actual_torch_loss':float(loss),
     'optimizer_updates':0,'Bunny_scores':0,'torch_version':torch.__version__}
(HERE/'REPLAY_RESULTS.json').write_text(json.dumps(out,indent=2)+'\n',encoding='utf8',newline='\n')
print(json.dumps(out,indent=2))
