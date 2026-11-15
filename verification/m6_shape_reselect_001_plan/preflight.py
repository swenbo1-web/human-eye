"""Fetch the pinned upstream checkpoint; CPU load/inference preflight only."""
import hashlib
import importlib.util
import json
from pathlib import Path
import time
import urllib.request

START, CPU = time.perf_counter(),time.process_time()
HERE=Path(__file__).resolve().parent
P=HERE/'private/pointfilter'
P.mkdir(parents=True,exist_ok=True)
HEAD='6e0ec1eac59ca9f81ee9ca6751c5b3f25effeda2'
EXPECTED_BLOB='c29307db95a7eceebb1e55bfa38e33ed45908c51'
EXPECTED_SIZE=10922719
records=[]
for r in json.loads((HERE/'source_payload.json').read_bytes())['files']:
    b=r['content'].encode('utf-8')
    (P/r['path']).write_bytes(b)
    records.append({'path':r['path'],'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest(),
                    'git_blob':hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()})
weights=P/'model_full_ae.pth'
url=f'https://raw.githubusercontent.com/dongbo-z/Pointfilter/{HEAD}/Summary/pre_train_model/model_full_ae.pth'
download_start=time.perf_counter()
if not weights.exists():
    req=urllib.request.Request(url,headers={'User-Agent':'HumanEye-M6-model-selection'})
    with urllib.request.urlopen(req,timeout=45) as response:
        b=response.read(EXPECTED_SIZE+1)
    if len(b)!=EXPECTED_SIZE: raise ValueError('checkpoint size mismatch')
    if hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()!=EXPECTED_BLOB:
        raise ValueError('checkpoint blob mismatch')
    weights.write_bytes(b)
b=weights.read_bytes()
assert len(b)==EXPECTED_SIZE and hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()==EXPECTED_BLOB
download_wall=time.perf_counter()-download_start

import torch
torch.set_num_threads(1)
torch.set_num_interop_threads(1)
spec=importlib.util.spec_from_file_location('_upstream_pointfilter',P/'Pointfilter_Network_Architecture.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
load_start=time.perf_counter()
checkpoint=torch.load(weights,map_location='cpu',weights_only=True)
model=module.pointfilternet().cpu().eval()
status=model.load_state_dict(checkpoint['state_dict'],strict=True)
load_wall=time.perf_counter()-load_start
assert not status.missing_keys and not status.unexpected_keys
assert all(torch.isfinite(t).all() for t in model.state_dict().values())
# Synthetic tensor only, no geometry example or scientific quality score.
x=torch.linspace(-.5,.5,500)
z=torch.stack((x,torch.sin(x),torch.zeros_like(x))).unsqueeze(0)
forward_start=time.perf_counter()
with torch.inference_mode(): y=model(z)
forward_wall=time.perf_counter()-forward_start
assert y.shape==(1,3) and torch.isfinite(y).all()
report={'status':'checkpoint_loaded_and_one_CPU_forward_passed','repository':'dongbo-z/Pointfilter','commit':HEAD,
        'checkpoint_url':url,'checkpoint_bytes':len(b),'checkpoint_git_blob':EXPECTED_BLOB,
        'checkpoint_sha256':hashlib.sha256(b).hexdigest(),'checkpoint_keys':list(checkpoint),
        'checkpoint_epoch':checkpoint.get('epoch'),'parameter_count':sum(p.numel() for p in model.parameters()),
        'buffer_count':sum(t.numel() for t in model.buffers()),'state_tensor_count':len(model.state_dict()),
        'torch':str(torch.__version__),'device':'cpu','threads':1,
        'source_files':records,'download_wall_s':download_wall,'load_wall_s':load_wall,'one_synthetic_forward_wall_s':forward_wall,
        'input_shape':list(z.shape),'output_shape':list(y.shape),'synthetic_output':y.tolist(),
        'source_mesh_inputs':0,'quality_trials':0,'training':0,'paid_API':0,
        'body_wall_s_before_write':time.perf_counter()-START,'body_CPU_s_before_write':time.process_time()-CPU,
        'scope':'one synthetic tensor confirms loading/operator availability; not a repair score, timing benchmark or final model selection'}
(HERE/'PREFLIGHT.json').write_bytes((json.dumps(report,ensure_ascii=False,indent=2)+'\n').encode('utf-8'))
print(json.dumps({k:v for k,v in report.items() if k!='source_files'},ensure_ascii=False))
