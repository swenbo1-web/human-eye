"""No training: exercise the proposed equations and proper symmetry properties."""
import os
for k in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'): os.environ[k]='1'
import json
from pathlib import Path
import time
import numpy as np

HERE=Path(__file__).resolve().parent
rng=np.random.default_rng(713)
weights={}
def layer(name,a,b):
    weights[name]=(rng.normal(0,.04,(a,b)),rng.normal(0,.01,b))
for name,a,b in [('en1',7,24),('en2',24,24),('ed1',52,24),('ed2',24,24),('up1',72,24),('up2',24,24),('al1',48,24),('al2',24,1),('be',24,1)]: layer(name,a,b)
weights['ln']=(np.ones(24),np.zeros(24))
parameters=sum(x.size for pair in weights.values() for x in pair)
assert parameters==6290
def linear(x,key,zero=False):
    w,b=weights[key]
    return np.zeros((len(x),len(b))) if zero else x@w+b
def silu(x): return x/(1+np.exp(-x))
def forward(z,zero=False):
    h0=linear(silu(linear(z['node_features'],'en1')),'en2'); h=h0.copy()
    a,b=z['edge_index']; degree=np.maximum(np.bincount(a,minlength=len(h)),1)[:,None]
    for _ in range(12):
        m=linear(silu(linear(np.concatenate([h[a],h[b],z['edge_features']],axis=1),'ed1')),'ed2')
        total=np.zeros_like(h); np.add.at(total,a,m); total/=degree
        h+=.1*linear(silu(linear(np.concatenate([h,total,h0],axis=1),'up1')),'up2')
        h=(h-h.mean(axis=1,keepdims=True))/np.sqrt(h.var(axis=1,keepdims=True)+1e-5)
        h=h*weights['ln'][0]+weights['ln'][1]
    alpha=linear(silu(linear(np.concatenate([h,h0],axis=1),'al1')),'al2',zero)
    beta=linear(m,'be',zero)
    output=alpha*z['normals']; total=np.zeros_like(output)
    np.add.at(total,a,beta*(z['positions'][b]-z['positions'][a])); output+=total/degree
    output[~z['free_mask']]=0
    return output

started=time.perf_counter(); records=[]
axis=np.array([1.,2.,3.]); axis/=np.linalg.norm(axis); angle=.731
skew=np.array([[0.,-axis[2],axis[1]],[axis[2],0.,-axis[0]],[-axis[1],axis[0],0.]])
rotation=np.eye(3)*np.cos(angle)+(1-np.cos(angle))*np.outer(axis,axis)+np.sin(angle)*skew
for path in sorted((HERE/'private').glob('*.npz')):
    with np.load(path,allow_pickle=False) as saved: data={k:saved[k] for k in saved.files}
    z={k:data[k].astype(np.float64) if data[k].dtype.kind=='f' else data[k] for k in ['node_features','edge_features','positions','normals','edge_index','free_mask']}
    transformed={**z,**{k:data['transformed_'+k].astype(np.float64) for k in ['node_features','edge_features','positions','normals']}}
    predicted=forward(z); changed=forward(transformed)
    assert np.array_equal(forward(z,zero=True),np.zeros_like(predicted))
    assert np.max(np.abs(predicted))>1e-5
    # new ordering: new index i holds old index permutation[i]
    permutation=rng.permutation(len(predicted)); inverse=np.argsort(permutation)
    permuted={**z,**{k:z[k][permutation] for k in ['node_features','positions','normals','free_mask']},'edge_index':inverse[z['edge_index']]}
    permutation_error=float(np.abs(forward(permuted)-predicted[permutation]).max())
    rotation_error=float(np.abs(changed-predicted@rotation.T).max())
    assert permutation_error<1e-12 and rotation_error<2e-6
    records.append({'input':path.stem,'normalized_prediction_max':float(np.abs(predicted).max()),'permutation_max_error':permutation_error,'rotation_max_error':rotation_error,'zero_initialization_exact':True,'fixed_output_zero':bool(np.all(predicted[~z['free_mask']]==0))})
result={'status':'passed_untrained_representation_checks','parameters':parameters,'seed':713,'cases':records,'message_steps':12,'training_calls':0,'prediction_quality_measured':False,'wall_s':time.perf_counter()-started,'limits':'NumPy float64 equation probe on float32 observation features; not the future torch implementation, convergence, reflection equivariance or performance acceptance. Scale2.3 and translation are included in transformed observation features; normalized output tested under proper rotation.'}
(HERE/'REPRESENTATION_PROBE.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf8',newline='\n')
print(json.dumps(result))
