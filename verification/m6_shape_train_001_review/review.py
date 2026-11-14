"""Independent NumPy audit of frozen saved candidates; no author evaluator imports."""
import collections
import json
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
AUTHOR = Path('C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe')
ROOT = HERE / 'snapshot'
BASE = ROOT / 'verification/m6_shape_train_001'
OLD = HERE.parent / 'm6_shape_data_001_review/snapshot'
checks = 0

def check(ok, message):
    global checks
    checks += 1
    if not ok:
        raise AssertionError(message)

def path(value):
    relative = Path(value).relative_to(AUTHOR)
    answer = ROOT / relative
    return answer if answer.exists() else OLD / relative

def read(p):
    return json.loads(p.read_bytes())

def stats(values):
    a = np.asarray(values, dtype=float)
    if not len(a):
        return {'count': 0}
    return {'count': len(a), 'min': float(a.min()), 'median': float(np.median(a)),
            'p95': float(np.quantile(a, .95)), 'max': float(a.max())}

def same(a, b, name):
    if a is None or b is None:
        check(a is b, name)
    else:
        check(np.isclose(a, b, rtol=2e-12, atol=2e-14), name)

def metric(error, mask, scale):
    e = np.linalg.norm(error[mask], axis=1)
    values = {'count': int(mask.sum())}
    for name, fun in [('rmse', lambda x: np.sqrt(np.mean(x*x))), ('p95', lambda x: np.quantile(x, .95)), ('max', np.max)]:
        value = float(fun(e)) if len(e) else None
        values[name+'_native'] = value
        values[name+'_over_scale'] = value / scale if value is not None else None
    return values

result = read(BASE / 'RESULTS.json')
records, diagnostics = [], []
baseline = {r['id']: r for r in result['baseline_cases']}
for item in result['model_cases']:
    check(item['purpose'] != 'reserved_test', 'reserved test forbidden')
    observed = np.load(path(item['observed_path']), allow_pickle=False)
    reference = np.load(path(item['reference_path']), allow_pickle=False)
    folder = path(item['graph_path']).parent
    sample = item['id'].split('/')[-1]
    with np.load(folder/'graph.npz', allow_pickle=False) as z:
        graph = {k:z[k] for k in z.files}
    with np.load(folder/'labels'/(sample+'.npz'), allow_pickle=False) as z:
        labels = {k:z[k] for k in z.files}
    with np.load(folder/'mapping.npz', allow_pickle=False) as z:
        mapping = {k:z[k] for k in z.files}
    allowed, support, free = graph['allowed_mask'], labels['damaged_mask'], graph['free_mask']
    masks = {'A': allowed, 'S': support, 'N': allowed & ~support, 'N_F': free & ~support}
    check(np.array_equal(masks['N_F'],labels['normal_free_mask']), 'normal-free mask')
    check(np.array_equal(masks['N'],labels['normal_allowed_mask']), 'normal mask')
    faces = mapping['context_triangles'][np.isin(mapping['context_source_face_ids'],mapping['incident_source_face_ids'])]
    check(len(faces) == len(mapping['incident_source_face_ids']), 'all incident faces')
    before = np.cross(observed[faces[:,1]]-observed[faces[:,0]],observed[faces[:,2]]-observed[faces[:,0]])
    before_zero = np.linalg.norm(before,axis=1)==0
    scale = item['scale_native']
    group = 'development_center' if item['purpose']=='development_train_pool' else 'validation_'+item['position_group']
    for entry in [item,baseline[item['id']]['mls'],baseline[item['id']]['no_op']]:
        candidate=np.load(path(entry['candidate_path']),allow_pickle=False)
        check(np.isfinite(candidate).all(),'finite candidate')
        fields = {k:metric(candidate-reference,m,scale) for k,m in masks.items()}
        for domain,values in fields.items():
            for key,val in values.items():
                same(val,entry['errors'][domain][key],entry['id']+'/'+domain+'/'+key)
        changed=np.any(candidate.view(np.uint64)!=observed.view(np.uint64),axis=1)
        check(not changed[~free].any(),'fixed bits')
        after=np.cross(candidate[faces[:,1]]-candidate[faces[:,0]],candidate[faces[:,2]]-candidate[faces[:,0]])
        newzero=int(((np.linalg.norm(after,axis=1)==0)&~before_zero).sum())
        flips=int((np.sum(before*after,axis=1)<0).sum())
        check(newzero==entry['incident_quality']['new_degenerate_faces'],'new degenerate')
        check(flips==entry['incident_quality']['normal_reversals_from_input'],'normal reversals')
        normal_fail=any(fields[k]['p95_over_scale']>.02 or fields[k]['max_over_scale']>.10 for k in ['N','N_F'])
        normal_control_fail=bool(item['normal_control'] and (fields['A']['rmse_over_scale']>.01 or fields['A']['p95_over_scale']>.02 or fields['A']['max_over_scale']>.05))
        ratio = float(np.linalg.norm((candidate-reference)[support])/np.linalg.norm((observed-reference)[support])) if support.any() else None
        aimprove = 1-float(np.linalg.norm((candidate-reference)[allowed])/np.linalg.norm((observed-reference)[allowed])) if support.any() else None
        same(ratio,entry['support_rmse_ratio_to_noop'],'support ratio')
        same(aimprove,entry['allowed_improvement_to_noop'],'allowed gain')
        records.append({'id':item['id'],'method':entry['method'],'group':group,'normal_control':item['normal_control'],'errors':fields,
                        'normal_fail':normal_fail,'normal_control_fail':normal_control_fail,'support_ratio':ratio,'allowed_improvement':aimprove,
                        'flips':flips,'new_degenerate':newzero,'changed_vertices':int(changed.sum())})
        if entry['method']=='model' and support.any():
            delta=candidate-observed; target=reference-observed
            d,t=delta[support],target[support]
            dn,tn=float(np.linalg.norm(d)),float(np.linalg.norm(t))
            dot=float(np.sum(d*t)); amplitude=max(0.,dot/(dn*dn)) if dn else 0.
            normal_sse=float(np.sum((candidate-reference)[masks['N']]**2))
            total_sse=float(np.sum((candidate-reference)[allowed]**2))
            diagnostics.append({'id':item['id'],'group':group,'perfect_support_gate_allowed_improvement':1-ratio,
                                'best_nonnegative_support_amplitude':amplitude,'support_direction_cosine':dot/(dn*tn) if dn else None,
                                'support_ratio_after_label_fitted_amplitude':float(np.linalg.norm(amplitude*d-t)/tn),
                                'normal_SSE_share':normal_sse/total_sse})

summary={}
for group in ['development_center','validation_center','validation_offcenter']:
    summary[group]={}
    for method in ['model','mls','no_op']:
        rows=[r for r in records if r['group']==group and r['method']==method]
        dent=[r for r in rows if not r['normal_control']]; ctrl=[r for r in rows if r['normal_control']]
        s={'cases':len(rows),'dent':len(dent),'controls':len(ctrl),'support_ratio':stats([r['support_ratio'] for r in dent]),
           'allowed_improvement':stats([r['allowed_improvement'] for r in dent]),
           'normal_point_failures':sum(r['normal_fail'] for r in rows),'normal_control_failures':sum(r['normal_control_fail'] for r in rows),
           'normal_reversal_faces':sum(r['flips'] for r in rows),'normal_reversal_cases':sum(r['flips']>0 for r in rows),
           'new_degenerate_faces':sum(r['new_degenerate'] for r in rows),'exact_noop_cases':sum(r['changed_vertices']==0 for r in rows),
           'normal_control_rmse':stats([r['errors']['A']['rmse_over_scale'] for r in ctrl])}
        summary[group][method]=s
        a=result['summaries'][group][method]
        check(s['normal_point_failures']==a['normal_point_gate_failures'],'aggregate normal failures')
        check(s['normal_control_failures']==a['normal_control_gate_failures'],'aggregate control failures')
        for stat in ['median','p95','max']:
            same(s['support_ratio'][stat],a['support_RMSE_ratio_to_noop'][stat],'aggregate support')
            same(s['allowed_improvement'][stat],a['allowed_improvement_to_noop'][stat],'aggregate allowed')
    dd=[d for d in diagnostics if d['group']==group]
    summary[group]['label_assisted_diagnosis_not_deployable']={k:stats([d[k] for d in dd]) for k in dd[0] if k not in ('id','group')}

log=read(BASE/'TRAIN_LOG.json'); uses=collections.Counter(); divisions=[]; components=[]
for step in log['steps']:
    check(len(step['cases'])==4 and len(step['components'])==4,'four graphs')
    check(len({x.split('_patch_')[0] for x in step['cases']})==4,'one per source file')
    check(sum(x.endswith('sample_00') for x in step['cases'])==1,'one normal control')
    for cid,c in zip(step['cases'],step['components']):
        uses[cid]+=1; m=c['mse']; n=c['denominators']; normal=c['normal_control']
        point=m['A'] if normal else .2*m['A']+.4*m['S']+.4*m['normal_free']
        check(np.isclose(point,c['point_loss'],rtol=3e-7,atol=1e-10),'loss arithmetic')
        check(np.isclose(point+.05*c['directed_edge_gradient_mse'],c['total_loss'],rtol=3e-7,atol=1e-10),'total loss')
        if not normal:
            divisions.append((.2/n['A']+.4/n['S'])/(.2/n['A']+.4/n['normal_free']))
            if step['step']>1000:
                components.append({'S':.4*m['S'],'N_F':.4*m['normal_free'],'A':.2*m['A'],'edge':.05*c['directed_edge_gradient_mse']})
    check(np.isclose(np.mean([c['total_loss'] for c in step['components']]),step['loss'],rtol=3e-7,atol=1e-10),'batch loss')
check(len(uses)==231,'all train observations seen')
online=read(BASE/'ONLINE_RESULTS.json')
cold=[r['cold_model_minus_MLS_wall_s'] for r in online['paired_differences']]
warm=[v for r in online['paired_differences'] for v in r['warm_model_minus_MLS_wall_s']]
out={'author_commit':'9c29a9f0990421c607ee821e838394e73dcaa9f3','checks':checks,'candidate_observations':len(records),
     'summary':summary,'per_case_metrics':records,'label_assisted_diagnosis':diagnostics,
     'training_audit':{'steps':len(log['steps']),'graphs':sum(uses.values()),'unique_cases':len(uses),'uses':dict(uses),
                       'per_support_vertex_vs_normal_free_point_loss_weight':stats(divisions),
                       'last_200_dent_loss_contributions_mean':{k:float(np.mean([c[k] for c in components])) for k in components[0]}},
     'paired_online_model_minus_MLS_s':{'cold':stats(cold),'warm':stats(warm),'coupling_included':False},
     'Bunny_model_or_MLS_scoring':0,'new_training_runs':0,'scope':'saved-output review and label-assisted attribution, not product/full-contact acceptance'}
(HERE/'INDEPENDENT_RESULTS.json').write_text(json.dumps(out,indent=2)+'\n',encoding='utf8',newline='\n')
print(json.dumps({'checks':checks,'candidate_observations':len(records),'summary':summary,'training_audit':{k:v for k,v in out['training_audit'].items() if k!='uses'},'paired_cost':out['paired_online_model_minus_MLS_s']},indent=2))
