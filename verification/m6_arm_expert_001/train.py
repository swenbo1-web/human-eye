"""One fixed tiny NumPy MLP fit; family-held-out sets never tune the model."""
import os
for variable in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'):
    os.environ[variable]='1'
import gzip
import hashlib
import json
from pathlib import Path
import statistics
import sys
import time
import types

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(Path(__file__).parent)]
package=types.ModuleType('human_eye_plugin');package.__path__=[str(ROOT/'human_eye_plugin')]
sys.modules['human_eye_plugin']=package
import numpy as np
from human_eye_plugin.arm_twist_expert import ArmTwistExpert,FEATURE_NAMES,FLAG_THRESHOLD,extract_features
from synthetic import generate_dataset
from geometry_baseline import predict as geometry_predict


def metrics(rows):
    truth=np.concatenate([r['truth'] for r in rows]);scores=np.concatenate([r['scores'] for r in rows])
    positive=truth>=FLAG_THRESHOLD;predicted=scores>=FLAG_THRESHOLD
    tp=int(np.sum(positive&predicted));fp=int(np.sum(~positive&predicted));fn=int(np.sum(positive&~predicted))
    ious=[]
    for row in rows:
        mask=np.asarray(row['truth'])>=FLAG_THRESHOLD;found=np.asarray(row['scores'])>=FLAG_THRESHOLD
        if mask.any():ious.append(float(np.sum(mask&found)/max(1,np.sum(mask|found))))
    return dict(sections=len(truth),mae=float(np.mean(np.abs(truth-scores))),
        max_error=float(np.max(np.abs(truth-scores))),precision=tp/max(1,tp+fp),recall=tp/max(1,tp+fn),
        f1=2*tp/max(1,2*tp+fp+fn),positive_case_localization_iou=float(np.mean(ious)) if ious else None,
        false_positive_sections=fp,false_negative_sections=fn,
        false_positive_normal_cases=sum(max(r['truth'])<FLAG_THRESHOLD and max(r['scores'])>=FLAG_THRESHOLD for r in rows))


def main():
    out=Path(sys.argv[1]).resolve();out.mkdir(parents=True,exist_ok=True)
    t0=time.perf_counter_ns();cases=generate_dataset(seed=1729);generation_ns=time.perf_counter_ns()-t0
    encoded=json.dumps(cases,separators=(',',':'),allow_nan=False).encode('utf8')
    compressed=gzip.compress(encoded,mtime=0);(out/'dataset.json.gz').write_bytes(compressed)
    splits={name:[c for c in cases if c['metadata']['split']==name] for name in ('train','validation','test')}
    for field in ('asset_id','shape_family','skeleton_family','weight_family'):
        sets=[{c['metadata'][field] for c in splits[s]} for s in splits]
        assert all(not (a&b) for i,a in enumerate(sets) for b in sets[i+1:]),field
    t0=time.perf_counter_ns();features={c['metadata']['case_id']:extract_features(c['packet'])[0] for c in cases}
    feature_ns=time.perf_counter_ns()-t0
    x=np.concatenate([features[c['metadata']['case_id']] for c in splits['train']])
    y=np.concatenate([c['label_severity'] for c in splits['train']])
    assert x.shape==(len(y),len(FEATURE_NAMES))
    mean=x.mean(axis=0);scale=x.std(axis=0);scale=np.where(scale>1e-8,scale,1.)
    x=(x-mean)/scale
    rng=np.random.default_rng(1729);width=12
    tensors={'w1':rng.normal(0.,.15,(len(FEATURE_NAMES),width)), 'b1':np.zeros(width),
             'w2':rng.normal(0.,.15,width),'b2':np.zeros(1)}
    first={k:np.zeros_like(v) for k,v in tensors.items()};second={k:np.zeros_like(v) for k,v in tensors.items()}
    row_weight=1+3*(y>.05);row_weight=row_weight/row_weight.mean()
    initial=None;loss_history=[];t0=time.perf_counter_ns()
    for step in range(1,601):
        hidden=np.tanh(x@tensors['w1']+tensors['b1']);prediction=hidden@tensors['w2']+tensors['b2'][0]
        residual=prediction-y;loss=float(np.mean(row_weight*residual**2))
        if initial is None:initial=loss
        if step==1 or step%100==0:loss_history.append({'step':step,'weighted_mse':loss})
        output_grad=2*row_weight*residual/len(y)
        hidden_grad=output_grad[:,None]*tensors['w2']*(1-hidden**2)
        grads={'w2':hidden.T@output_grad+1e-6*tensors['w2'],'b2':np.array([output_grad.sum()]),
               'w1':x.T@hidden_grad+1e-6*tensors['w1'],'b1':hidden_grad.sum(axis=0)}
        for key in tensors:
            first[key]=.9*first[key]+.1*grads[key];second[key]=.999*second[key]+.001*grads[key]**2
            tensors[key]-=.015*(first[key]/(1-.9**step))/(np.sqrt(second[key]/(1-.999**step))+1e-8)
    training_ns=time.perf_counter_ns()-t0
    parameters={'schema':'arm-twist-mlp-v1','model_id':'arm-twist-tiny-mlp-seed1729-v1',
        'feature_names':list(FEATURE_NAMES),'mean':mean.tolist(),'scale':scale.tolist(),
        **{key:value.tolist() for key,value in tensors.items()},
        'training':{'seed':1729,'steps':600,'hidden_units':width,'learning_rate':.015,'train_only_standardization':True,
                    'dataset_sha256':hashlib.sha256(encoded).hexdigest(),'task':'constructed twist artifact severity, not measured injury',
                    'train_assets':sorted({c['metadata']['asset_id'] for c in splits['train']})}}
    weights=ROOT/'human_eye_plugin/arm_twist_weights.py'
    weights.write_text('"""Learned tensors and train-only preprocessing; generated by m6 train.py."""\nPARAMETERS = '+
        repr(parameters)+'\n',encoding='utf8',newline='\n')
    model=ArmTwistExpert(parameters)
    results={};per_case=[];feature_times=[];inference_times=[];baseline_times=[]
    for split,selected in splits.items():
        model_rows=[];baseline_rows=[]
        for case in selected:
            patch=case['packet'];target=np.asarray(case['label_severity']);case_id=case['metadata']['case_id']
            t0=time.perf_counter_ns();f,context=extract_features(patch);feature_times.append(time.perf_counter_ns()-t0)
            assert not context['reason'],context['reason']
            t0=time.perf_counter_ns();scores=np.clip(np.tanh(((f-mean)/scale)@model._w1+model._b1)@model._w2+model._b2[0],0,1)
            inference_times.append(time.perf_counter_ns()-t0)
            t0=time.perf_counter_ns();baseline=geometry_predict(patch);baseline_times.append(time.perf_counter_ns()-t0)
            report=model.predict(patch)
            assert report['status']=='estimated'
            assert np.allclose(scores,[r['predicted_severity'] for r in report['regions']],rtol=0,atol=1e-14)
            row={'truth':target.tolist(),'scores':scores.tolist(),'family':case['metadata']['pose_family']}
            model_rows.append(row);baseline_rows.append(dict(row,scores=baseline.tolist()))
            per_case.append({'case_id':case_id,'split':split,'pose_family':row['family'],
                'truth':target.tolist(),'model':scores.tolist(),'geometry_baseline':baseline.tolist()})
        results[split]={'model':metrics(model_rows),'geometry_baseline':metrics(baseline_rows),'by_pose':{}}
        for family in sorted({r['family'] for r in model_rows}):
            results[split]['by_pose'][family]={'model':metrics([r for r in model_rows if r['family']==family]),
                'geometry_baseline':metrics([r for r in baseline_rows if r['family']==family])}
    timing={name:{'median_ms':statistics.median(values)/1e6,'max_ms':max(values)/1e6,'samples':len(values)}
            for name,values in [('feature',feature_times),('network_only',inference_times),('geometry_baseline',baseline_times)]}
    result={'trained':True,'model_kind':'one_hidden_layer_tanh_mlp_numpy','parameter_count':sum(v.size for v in tensors.values()),
        'generation_ms':generation_ns/1e6,'feature_generation_ms':feature_ns/1e6,'training_ms':training_ns/1e6,
        'initial_train_weighted_mse':initial,'train_history':loss_history,'results':results,'timing':timing,
        'data_bytes':len(encoded),'data_compressed_bytes':len(compressed),'data_sha256':hashlib.sha256(encoded).hexdigest(),
        'weights_bytes':weights.stat().st_size,'weights_sha256':hashlib.sha256(weights.read_bytes()).hexdigest(),
        'cases':{split:len(selected) for split,selected in splits.items()},
        'split_families':{split:{field:sorted({c['metadata'][field] for c in selected}) for field in
            ('asset_id','shape_family','skeleton_family','weight_family')} for split,selected in splits.items()},
        'per_case':per_case,'threshold':FLAG_THRESHOLD,'heldout_tuning':False,'blender_processes':0,'external_api_calls':0}
    (out/'result.json').write_text(json.dumps(result,indent=2,allow_nan=False),encoding='utf8',newline='\n')
    print(json.dumps({'trained':True,'training_ms':result['training_ms'],'parameters':result['parameter_count'],
        'heldout':results['test'],'result':str(out/'result.json')},allow_nan=False))


if __name__=='__main__':main()
