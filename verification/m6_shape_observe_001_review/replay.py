"""Replay the seven fixed witnesses from the isolated, hash-checked weights."""
import os
for name in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'):
    os.environ[name]='1'
import importlib.util
import json
from pathlib import Path
import sys
import time
import numpy as np

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import review as rv

start,cpu=time.perf_counter(),time.process_time()
import torch
torch.set_num_threads(1)
torch.set_num_interop_threads(1)
torch.use_deterministic_algorithms(True)
spec=importlib.util.spec_from_file_location('_review_observe_model',rv.O/'model.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
model=module.ResidualExpert()
checkpoint=torch.load(rv.O/'private/weights/step_1200.pt',map_location='cpu',weights_only=False)
model.load_state_dict(checkpoint['model']);model.eval()
for p in model.parameters():p.requires_grad_(False)
trace=rv.read(rv.B/'FROZEN_TRACE.json');records=[]
for row in trace['cases']:
    s=rv.load(rv.LOOKUP[row['case_id']]);values=rv.forwards(s)
    tensors=[torch.from_numpy(np.ascontiguousarray(v)) for v in values.values()]
    old=rv.npz(rv.local(row['trace_path']));captured={};step=[0]
    def encoder(_m,_i,out):captured['h0']=out.detach().numpy().copy()
    def norm(_m,_i,out):
        step[0]+=1
        if step[0] in (4,8,12):captured['h'+str(step[0])]=out.detach().numpy().copy()
    hooks=[model.node_encoder.register_forward_hook(encoder),model.layer_norm.register_forward_hook(norm)]
    before=time.perf_counter()
    with torch.inference_mode():
        u,z,p=model.forward_components(*tensors)
        hard=module.gate_prediction(u,p,tensors[5],trace['fixed_tau'])
    for hook in hooks:hook.remove()
    for name,value in zip(('u','z','p','prediction_normalized'),(u,z,p,hard)):
        captured[name]=value.numpy().copy()
    assert step[0]==12
    for name,value in captured.items():assert np.array_equal(value.view(np.uint32),old[name].view(np.uint32)),(row['case_id'],name)
    records.append({'case_id':row['case_id'],'bitwise_equal_arrays':list(captured),'layer_norm_calls':step[0],'forward_wall_s':time.perf_counter()-before})
out={'status':'passed','actual_frozen_forwards':len(records),'records':records,'new_training':0,'Bunny_arrays':0,'torch_version':torch.__version__,'wall_s_before_final_write':time.perf_counter()-start,'CPU_s_before_final_write':time.process_time()-cpu}
(HERE/'REPLAY_RESULTS.json').write_text(json.dumps(out,indent=2)+'\n',encoding='utf8',newline='\n')
print(json.dumps(out,indent=2))
