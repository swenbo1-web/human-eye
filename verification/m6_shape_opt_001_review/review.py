"""Independent saved-array audit of the final one-optimization candidate."""
import json
from pathlib import Path
import numpy as np

HERE=Path(__file__).resolve().parent
ROOT=HERE/'snapshot'
BASE=ROOT/'verification/m6_shape_opt_001'
PRIOR=HERE.parent/'m6_shape_train_001_review/snapshot'
DATA=HERE.parent/'m6_shape_data_001_review/snapshot'
AUTHOR=Path('C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe')
checks=0
def check(v,msg):
    global checks
    checks+=1
    if not v: raise AssertionError(msg)
def locate(v):
    rel=Path(v).relative_to(AUTHOR)
    for root in (ROOT,PRIOR,DATA):
        p=root/rel
        if p.exists(): return p
    raise FileNotFoundError(v)
def read(p):return json.loads(p.read_bytes())
def stats(v):
    a=np.asarray(v,dtype=float)
    return {'count':len(a),'min':float(a.min()),'median':float(np.median(a)),'p95':float(np.quantile(a,.95)),'max':float(a.max())} if len(a) else {'count':0}
def close(a,b,msg):
    check(a is b if a is None or b is None else np.isclose(a,b,rtol=3e-12,atol=3e-14),msg)
def metrics(e,m,l):
    x=np.linalg.norm(e[m],axis=1)
    out={'count':int(m.sum())}
    for name,f in [('rmse',lambda a:np.sqrt(np.mean(a*a))),('p95',lambda a:np.quantile(a,.95)),('max',np.max)]:
        v=float(f(x)) if len(x) else None
        out[name+'_native']=v;out[name+'_over_scale']=v/l if v is not None else None
    return out
def auc(pos,neg):
    if not len(pos) or not len(neg):return None
    ordered=np.sort(neg)
    return float(np.mean((np.searchsorted(ordered,pos,'left')+np.searchsorted(ordered,pos,'right'))/2)/len(neg))

r=read(BASE/'RESULTS.json');cal=read(BASE/'LOC_CALIBRATION.json');tau=cal['tau']
cal_arrays=[np.load(locate(c['scores_path']),allow_pickle=False) for c in cal['cases']]
cal_p=np.concatenate(cal_arrays)
check(len(cal_arrays)==33 and len(cal_p)==10405,'calibration denominators')
check(float(np.quantile(cal_p,.995,method='linear'))==cal['q995'],'single prescribed quantile')
check(max(.5,cal['q995'])==tau,'tau')
check(int((cal_p.astype(np.float64)>tau).sum())==53,'strict threshold count')
rows=[];scores={g:{'S':[],'N_F':[],'case_auc':[]} for g in ['development_center','validation_center','validation_offcenter']}
soft_saved=read(BASE/'EVAL_STEP_1200.json')
soft_cases={c['id']:c for side in ['development','validation'] for c in soft_saved[side]['cases']}
for c in r['model_cases']:
    check(c['purpose']!='reserved_test','Bunny remains excluded')
    group='development_center' if c['purpose']=='development_train_pool' else 'validation_'+c['position_group']
    observed=np.load(locate(c['observed_path']),allow_pickle=False)
    ref=np.load(locate(c['reference_path']),allow_pickle=False)
    candidate=np.load(locate(c['candidate_path']),allow_pickle=False)
    folder=locate(c['graph_path']).parent;sid=c['id'].split('/')[-1]
    with np.load(folder/'graph.npz',allow_pickle=False) as z:g={k:z[k] for k in z.files}
    with np.load(folder/'labels'/(sid+'.npz'),allow_pickle=False) as z:lab={k:z[k] for k in z.files}
    with np.load(folder/'mapping.npz',allow_pickle=False) as z:mp={k:z[k] for k in z.files}
    with np.load(locate(c['component_path']),allow_pickle=False) as z:comp={k:z[k] for k in z.files}
    free,A,S=g['free_mask'],g['allowed_mask'],lab['damaged_mask'];N=free&~S
    p,u,z=comp['p'],comp['u'],comp['z']
    check(np.isfinite(p).all() and np.isfinite(u).all(),'finite components')
    check(np.allclose(p,1/(1+np.exp(-z.astype(np.float64))),rtol=2e-7,atol=1e-8),'sigmoid')
    selected=free&(p.astype(np.float64)>tau)
    pred=np.zeros_like(u);pred[selected]=u[selected]
    check(np.array_equal(selected,comp['selected']),'selected flags')
    check(np.array_equal(pred,comp['prediction_normalized']),'hard gate output')
    expected=observed.copy();correction=pred.astype(np.float64)*c['scale_native'];active=free[:,None]&(correction!=0)
    expected[active]+=correction[active]
    check(np.array_equal(expected.view(np.uint64),candidate.view(np.uint64)),'actual candidate reconstruction')
    changed=np.any(candidate.view(np.uint64)!=observed.view(np.uint64),axis=1)
    check(not changed[~free].any(),'fixed binary64 preservation')
    domains={'A':A,'S':S,'N':A&~S,'N_F':N}
    measure={name:metrics(candidate-ref,mask,c['scale_native']) for name,mask in domains.items()}
    for domain,values in measure.items():
        for key,v in values.items():close(v,c['errors'][domain][key],'saved shape metric')
    normalfail=any(measure[d]['p95_over_scale']>.02 or measure[d]['max_over_scale']>.1 for d in ['N','N_F'])
    controlfail=bool(c['normal_control'] and (measure['A']['rmse_over_scale']>.01 or measure['A']['p95_over_scale']>.02 or measure['A']['max_over_scale']>.05))
    tp=int((selected&S).sum());fp=int((selected&~S).sum());fn=int((~selected&S&free).sum());tn=int((~selected&~S&free).sum())
    counts={'TP':tp,'FP':fp,'FN':fn,'TN':tn}
    for k,v in counts.items():check(v==c['classification'][k],'saved classification')
    faces=mp['context_triangles'][np.isin(mp['context_source_face_ids'],mp['incident_source_face_ids'])]
    check(len(faces)==len(mp['incident_source_face_ids']),'incident closure')
    before=np.cross(observed[faces[:,1]]-observed[faces[:,0]],observed[faces[:,2]]-observed[faces[:,0]])
    after=np.cross(candidate[faces[:,1]]-candidate[faces[:,0]],candidate[faces[:,2]]-candidate[faces[:,0]])
    flip=int((np.sum(before*after,axis=1)<0).sum());degen=int(((np.linalg.norm(before,axis=1)!=0)&(np.linalg.norm(after,axis=1)==0)).sum())
    check(flip==c['incident_quality']['normal_reversals_from_input'],'flipped faces')
    check(degen==c['incident_quality']['new_degenerate_faces'],'degenerate faces')
    ratio=float(np.linalg.norm((candidate-ref)[S])/np.linalg.norm((observed-ref)[S])) if S.any() else None
    gain=1-float(np.linalg.norm((candidate-ref)[A])/np.linalg.norm((observed-ref)[A])) if S.any() else None
    close(ratio,c['support_rmse_ratio_to_noop'],'support ratio');close(gain,c['allowed_improvement_to_noop'],'A gain')
    soft=observed.copy();softdelta=(p[:,None]*u).astype(np.float64)*c['scale_native']
    nonzero=free[:,None]&(softdelta!=0);soft[nonzero]+=softdelta[nonzero]
    so=soft_cases[c['id']]
    check(np.array_equal(soft.view(np.uint64),np.load(locate(so['candidate_path']),allow_pickle=False).view(np.uint64)),'soft candidate from frozen components')
    raw_support_ratio=float(np.linalg.norm((observed-ref)[S]+u[S].astype(np.float64)*c['scale_native'])/np.linalg.norm((observed-ref)[S])) if S.any() else None
    scores[group]['S'].append(p[S]);scores[group]['N_F'].append(p[N])
    case_auc=auc(p[S],p[N])
    if case_auc is not None:scores[group]['case_auc'].append(case_auc)
    rows.append({'id':c['id'],'group':group,'normal_control':c['normal_control'],'errors':measure,'normal_fail':normalfail,'control_fail':controlfail,'noop':not changed.any(),
                 'classification':counts,'ratio':ratio,'gain':gain,'flipped_faces':flip,'new_degenerate':degen,
                 'soft_support_ratio':so['support_rmse_ratio_to_noop'],'soft_A_gain':so['allowed_improvement_to_noop'],
                 'label_assisted_raw_u_support_ratio':raw_support_ratio,'learned_score_auc':case_auc})
summaries={}
for group,parts in scores.items():
    rr=[v for v in rows if v['group']==group];dent=[v for v in rr if not v['normal_control']]
    positive=np.concatenate(parts['S']);negative=np.concatenate(parts['N_F'])
    counts={k:sum(v['classification'][k] for v in rr) for k in ('TP','FP','FN','TN')}
    summaries[group]={'cases':len(rr),'dents':len(dent),'controls':len(rr)-len(dent),'noop_cases':sum(v['noop'] for v in rr),
        'normal_failures':sum(v['normal_fail'] for v in rr),'control_failures':sum(v['control_fail'] for v in rr),
        'flipped_faces':sum(v['flipped_faces'] for v in rr),'flipped_cases':sum(v['flipped_faces']>0 for v in rr),'new_degenerate':sum(v['new_degenerate'] for v in rr),
        'S_ratio':stats([v['ratio'] for v in dent]),'A_gain':stats([v['gain'] for v in dent]),'classification':counts,
        'learned_scores_S':stats(positive),'learned_scores_N_F':stats(negative),'point_pooled_score_AUC':auc(positive,negative),
        'dent_case_score_AUC':stats(parts['case_auc']),
        'soft_S_ratio':stats([v['soft_support_ratio'] for v in dent]),'soft_A_gain':stats([v['soft_A_gain'] for v in dent]),
        'raw_u_support_ratio_LABEL_DIAGNOSIS_ONLY':stats([v['label_assisted_raw_u_support_ratio'] for v in dent])}
log=read(BASE/'TRAIN_LOG.json');old=read(PRIOR/'verification/m6_shape_train_001/TRAIN_LOG.json')
check(len(log['steps'])==len(old['steps'])==1200,'1200 steps')
for step,original in zip(log['steps'],old['steps']):
    check(step['cases']==original['cases'],'same sampling sequence')
    for c in step['components']:
        m=c['mse']; n=c['denominators'];normal=c['normal_control']
        point=m['A'] if normal else .2*m['A']+.4*m['S']+.4*m['normal_free']
        base=point+.05*c['directed_edge_gradient_mse']
        cond=0 if normal else .4*c['conditional_support_mse']
        means=c['localization_means']
        loc=.05*(means['F_control_negative'] if normal else .5*(means['S_positive']+means['N_F_negative']))
        for x,y in [(base,c['base_total_loss']),(cond,c['conditional_loss']),(loc,c['localization_loss']),(base+cond+loc,c['total_loss'])]:
            check(np.isclose(x,y,rtol=4e-7,atol=2e-9),'recorded loss arithmetic')
        check(c['localization_denominators']=={'S':n['S'],'N_F':n['normal_free'],'F':n['S']+n['normal_free']},'loss denominators')
    check(np.isclose(np.mean([c['total_loss'] for c in step['components']]),step['loss'],rtol=4e-7,atol=2e-9),'equal graph mean')
online=read(BASE/'ONLINE_RESULTS.json');paired=online['paired_differences']
out={'author_commit':'36694d0e3730a60b0611376b017f978f809a79c0','checks':checks,'candidate_observations':len(rows),
     'calibration':{'tau':tau,'points':len(cal_p),'controls':len(cal_arrays),'selected_training_control_points':53},
     'groups':summaries,'per_case':rows,'training_batches_verified':1200,'graphs_verified':4800,
     'paired_cost_excluding_coupling':{'cold_s':stats([v['cold_model_minus_MLS_wall_s'] for v in paired]),'warm_s':stats([x for v in paired for x in v['warm_model_minus_MLS_wall_s']])},
     'new_training_updates':0,'new_threshold_candidates':0,'Bunny_scores':0,
     'rank_diagnosis_scope':'Saved learned scores only. Repeated vertices across variants are not independent assets. Does not prove raw observations uninformative.',
     'decision':'close_current_candidate_quality_failure'}
(HERE/'INDEPENDENT_RESULTS.json').write_text(json.dumps(out,indent=2)+'\n',encoding='utf8',newline='\n')
print(json.dumps({k:v for k,v in out.items() if k!='per_case'},indent=2))
