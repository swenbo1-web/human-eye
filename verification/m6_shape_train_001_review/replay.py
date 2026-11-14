"""Frozen inference and separate NumPy model equations; never trains a model."""
import os
for variable in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):
    os.environ[variable]='1'
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
import torch

HERE=Path(__file__).resolve().parent
BASE=HERE/'snapshot/verification/m6_shape_train_001'
OLD=HERE.parent/'m6_shape_data_001_review/snapshot/verification/m6_shape_data_001'
AUTHOR=Path('C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe')
sys.path.insert(0,str(BASE))
from model import ResidualExpert, graph_loss
from data_io import load_sample, forward_arrays, candidate_from_prediction, fit_standardization, batch_samples

torch.set_num_threads(1)
torch.set_num_interop_threads(1)
torch.use_deterministic_algorithms(True)
weight=BASE/'private/weights/step_1200.pt'
assert hashlib.sha256(weight.read_bytes()).hexdigest()=='3f843b0153f1c63d95f7122d6ef68e2df151bcecc8705377596c7940665adc0f'
checkpoint=torch.load(weight,map_location='cpu',weights_only=True)
assert checkpoint['step']==1200 and checkpoint['seed']==1729 and checkpoint['parameters']==6290
model=ResidualExpert(); model.load_state_dict(checkpoint['model']); model.eval()
assert sum(p.numel() for p in model.parameters())==6290
train=json.loads((OLD/'DATASET_INDEX.json').read_bytes())['cases']
val=[c for c in json.loads((BASE/'PUBLIC_DATASET_INDEX.json').read_bytes())['cases'] if c['purpose']=='validation']
cases={c['id']:c for c in train+val}
train_samples=[load_sample(c,OLD/'private/patches') for c in train]
stats=fit_standardization(train_samples)
with np.load(BASE/'private/normalization.npz',allow_pickle=False) as z:
    assert all(np.array_equal(stats[k],z[k]) for k in stats)
saved={r['id']:r for r in json.loads((BASE/'RESULTS.json').read_bytes())['model_cases']}

# Float64 equations written independently rather than calling the author network.
params={k:v.detach().numpy().astype(np.float64) for k,v in model.state_dict().items()}
def linear(x,prefix):
    return x@params[prefix+'.weight'].T+params[prefix+'.bias']
def mlp(x,prefix):
    x=linear(x,prefix+'.0');x=x/(1+np.exp(-x))
    return linear(x,prefix+'.2')
def numpy_forward(values):
    node,edge,pos,normal,ij,free=values
    node,edge,pos,normal=[a.astype(np.float64) for a in [node,edge,pos,normal]]
    i,j=ij; degree=np.maximum(np.bincount(i,minlength=len(node)),1)[:,None]
    h0=mlp(node,'node_encoder');h=h0
    for _ in range(12):
        message=mlp(np.concatenate([h[i],h[j],edge],axis=1),'edge_mlp')
        agg=np.zeros_like(h);np.add.at(agg,i,message);agg/=degree
        h=h+.1*mlp(np.concatenate([h,agg,h0],axis=1),'node_update')
        mean=h.mean(axis=1,keepdims=True);variance=((h-mean)**2).mean(axis=1,keepdims=True)
        h=(h-mean)/np.sqrt(variance+1e-5)*params['layer_norm.weight']+params['layer_norm.bias']
    alpha=mlp(np.concatenate([h,h0],axis=1),'alpha_head');beta=linear(message,'beta_head')
    vector=np.zeros_like(pos);np.add.at(vector,i,beta*(pos[j]-pos[i]))
    result=alpha*normal+vector/degree;result[~free]=0
    return result

chosen=['Yanyite_patch_08/sample_00','Yunhex_patch_01/sample_01','Richie_patch_00/sample_06',
        'Stanford_Armadillo_patch_00/sample_00','Stanford_Armadillo_patch_03/sample_06','Stanford_Armadillo_patch_03/sample_12']
rows=[];samples=[]
for cid in chosen:
    case=cases[cid]
    folder=OLD/'private/patches' if case['purpose']=='development_train_pool' else BASE/'private/public_data/patches'
    sample=load_sample(case,folder);samples.append(sample)
    values=forward_arrays(sample,stats)
    with torch.inference_mode():
        predicted=model(*(torch.from_numpy(np.ascontiguousarray(a)) for a in values)).numpy()
    candidate=candidate_from_prediction(sample,predicted)
    expected=np.load(HERE/'snapshot'/Path(saved[cid]['candidate_path']).relative_to(AUTHOR),allow_pickle=False)
    assert np.array_equal(candidate.view(np.uint64),expected.view(np.uint64)),cid
    separate=numpy_forward(values)
    difference=float(np.max(np.linalg.norm(predicted-separate,axis=1)))
    assert difference<3e-6,(cid,difference)
    rows.append({'id':cid,'saved_candidate_bitwise_equal':True,'numpy_equations_max_vector_error_normalized':difference})
forward,supervision=batch_samples(samples,stats)
with torch.inference_mode():
    prediction=model(*forward)
    actual_loss,components=graph_loss(prediction,**supervision)
e=(prediction-supervision['target']).numpy().astype(np.float64)
i,j=forward[4].numpy(); gids=supervision['graph_index'].numpy(); point=e*e
losses=[]
for g in range(len(samples)):
    A=supervision['allowed_mask'].numpy()&(gids==g)
    S=supervision['damaged_mask'].numpy()&(gids==g)
    N=supervision['normal_free_mask'].numpy()&(gids==g)
    mA=point[A].sum(axis=1).mean()
    p=mA if not S.any() else .2*mA+.4*point[S].sum(axis=1).mean()+.4*point[N].sum(axis=1).mean()
    ed=e[j]-e[i]; grad=np.mean(np.sum(ed[gids[i]==g]**2,axis=1))
    losses.append(float(p+.05*grad))
assert np.isclose(np.mean(losses),float(actual_loss),rtol=3e-6,atol=1e-9)
out={'author_commit':'9c29a9f0990421c607ee821e838394e73dcaa9f3','torch_version':torch.__version__,
     'checkpoint_sha256':hashlib.sha256(weight.read_bytes()).hexdigest(),'parameters':6290,
     'normalization_scalars_recomputed_from_231_train_only':18,'forward_cases':rows,
     'six_graph_numpy_loss':float(np.mean(losses)),'torch_loss':float(actual_loss),
     'optimizer_updates':0,'Bunny_model_or_MLS_scores':0,'source_imports':'fixed copied model.py/data_io.py, no author evaluator'}
(HERE/'REPLAY_RESULTS.json').write_text(json.dumps(out,indent=2)+'\n',encoding='utf8',newline='\n')
print(json.dumps(out,indent=2))
