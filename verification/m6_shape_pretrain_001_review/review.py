"""Independent frozen-output and representative-forward review; no author evaluator imports."""
import os
for key in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'): os.environ[key]='1'
import ast, hashlib, importlib.util, io, json, time
from pathlib import Path
import numpy as np
import torch
HERE=Path(__file__).resolve().parent; ROOT=HERE.parents[1]
AUTHOR=Path('C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe')
B=HERE/'snapshot/verification/m6_shape_pretrain_001'
OLD=HERE.parent/'m6_shape_observe_001_review/snapshot'
START,CPU=time.perf_counter(),time.process_time()
read=lambda p:json.loads(Path(p).read_bytes())
E=read(B/'EVALUATION.json'); O=read(B/'MODEL_OUTPUTS.json'); I=read(B/'INPUT_INDEX.json')
expected={Path(x['path']):x['sha256'] for x in read(HERE/'SNAPSHOT.json')['records']}
old_index={x['relative']:x['sha256'] for x in read(HERE.parent/'m6_shape_observe_001_review/SNAPSHOT.json')['snapshot_files']}
checked=set(); checks=0; errors={}
for x in E['input_file_identities']+read(B/'REUSED_INPUTS.json')['files']:
    expected[Path(x['path'])]=x['sha256']
def data(path):
    path=Path(path); blob=path.read_bytes()
    assert hashlib.sha256(blob).hexdigest()==expected[path],str(path)
    checked.add(str(path)); return blob
def npy(path):return np.load(io.BytesIO(data(path)),allow_pickle=False)
def npz(path):
    with np.load(io.BytesIO(data(path)),allow_pickle=False) as z:return {k:z[k].copy() for k in z.files}
def old(path):
    rel=Path(path).relative_to(AUTHOR); p=OLD/rel; blob=p.read_bytes()
    assert hashlib.sha256(blob).hexdigest()==old_index[rel.as_posix()]
    if p.suffix=='.npy':return np.load(io.BytesIO(blob),allow_pickle=False)
    with np.load(io.BytesIO(blob),allow_pickle=False) as z:return {k:z[k].copy() for k in z.files}
def check(x,tag):
    global checks
    checks+=1
    if not x:raise AssertionError(tag)
def close(x,y,tag,atol=3e-11):
    x,y=np.asarray(x),np.asarray(y); err=float(np.max(np.abs(x-y))) if x.size else 0
    errors[tag.split(':')[0]]=max(errors.get(tag.split(':')[0],0.),err)
    check(np.allclose(x,y,atol=atol,rtol=atol),tag)
def same(x,y,tag):check(np.array_equal(x,y),tag)
def mls(points):
    u,v,z=np.asarray(points,dtype=float).T
    X=np.array([u*u,u*v,v*v,u,v,np.ones(len(u))]).T
    base=np.exp(-4*np.sum(np.asarray(points,dtype=float)**2,axis=1)); w=base.copy()
    for iteration in range(4):
        coef,_,rank,_=np.linalg.lstsq(X*np.sqrt(w[:,None]),z*np.sqrt(w),rcond=None)
        if rank<6:return np.zeros(3)
        if iteration<3:
            residual=z-X@coef; scale=max(1.4826*np.median(np.abs(residual-np.median(residual))),1e-4)
            t=residual/(4.685*scale); w=base*np.where(abs(t)<1,(1-t*t)**2,0)
    return np.array([0.,0.,coef[-1]])
# Reuse only the root reviewer's previously validated Voronoi-region equation, not its top-level execution.
tree=ast.parse((HERE.parent/'m6_shape_objective_001_review/review.py').read_text(encoding='utf-8'))
fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='nearest')
exec(compile(ast.Module(body=[fn],type_ignores=[]),'<root_verified_voronoi>','exec'),globals())
torch.set_num_threads(1);torch.set_num_interop_threads(1)
arch=B/'private/pointfilter/Pointfilter_Network_Architecture.py'
spec=importlib.util.spec_from_file_location('_review_upstream_pointfilter',arch); module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
weights=B/'private/pointfilter/model_full_ae.pth'
check(hashlib.sha256(weights.read_bytes()).hexdigest()=='86600e6d57fab7887fbda0cf54292578a52d956c36766a130d1e32a475d18cee','weight')
model=module.pointfilternet().eval();model.load_state_dict(torch.load(weights,map_location='cpu',weights_only=True)['state_dict'],strict=True)
check(sum(p.numel() for p in model.parameters())==1360899,'parameters')
inputs={r['id']:r for r in I['cases']}; outputs={r['id']:r for r in O['cases']}
sources={}; replay_x=[];replay_y=[]; summary=[]; iterations=0;surface_queries=0; surface_records=0
for case in E['cases']:
    cid=case['id']; input_row=inputs[cid]; package=npz(input_row['path']); full=package['vertices']; free_ids=package['free_source_ids']; context=package['context_source_ids']
    check(set(package)=={'vertices','free_source_ids','context_source_ids'},cid+'_input keys')
    r=case['methods']['pointfilter']; mapping=old(r['mapping_path']); graph=old(r['graph_path']); obs=old(r['observed_path']); ref=old(r['reference_path'])
    scale=r['scale_native']; folder=Path(r['observed_path']).parents[1]; sample=cid.split('/')[-1]
    if case['normal_control']: support=np.zeros(len(context),dtype=bool)
    else:support=old(folder/'labels'/(sample+'.npz'))['damaged_mask']
    inp=old(folder/'inputs'/(sample+'.npz')); origin=inp['origin_world_m']
    same(context,mapping['context_source_ids'],cid+'_mapping'); same(free_ids,np.sort(context[graph['free_mask']]),cid+'_free')
    source=case['source']
    if source not in sources:
        rel=('verification/m6_shape_train_001/private/public_data/sources/Stanford_Armadillo/snapshot.npz' if case['purpose']=='validation' else f'verification/m6_shape_data_001/private/{source}/snapshot.npz')
        sources[source]=old(AUTHOR/rel)
    rebuilt=sources[source]['vertices'].copy();rebuilt[context]=obs
    same(full,rebuilt,cid+'_full current input')
    nonfree=np.ones(len(full),dtype=bool);nonfree[free_ids]=False
    first_samples=None
    for method in ('pointfilter','robust_mls'):
        current=full.copy();rng=np.random.RandomState(1729)
        for step in outputs[cid]['methods'][method]['iterations']:
            iterations+=1; detail=npz(step['sampling_path']); candidate=npy(step['candidate_path'])
            radius=float(detail['radius']);close(radius,.05*np.linalg.norm(np.ptp(current,axis=0)),cid+'_radius')
            same(detail['query_source_ids'],free_ids,cid+'_query IDs')
            close(detail['radius_per_query'],np.full(len(free_ids),radius),cid+'_all radii')
            if step['iteration']==1:
                if first_samples is None:first_samples=detail['sampled_source_ids']
                else:same(first_samples,detail['sampled_source_ids'],cid+'_same first samples')
            for row in range(len(free_ids)):
                lo,hi=detail['neighbor_offsets'][row:row+2]; neighbors=detail['neighbor_source_ids'][lo:hi]
                chosen=rng.choice(range(len(neighbors)),500,replace=len(neighbors)<=500)
                same(neighbors[chosen],detail['sampled_source_ids'][row],cid+'_RNG')
            offsets=current[detail['sampled_source_ids']]-current[free_ids,None,:]
            normalized=np.einsum('qij,qkj->qki',np.linalg.inv(detail['pca_inverse']),offsets)/radius
            close(normalized.astype(np.float32),detail['normalized_points'],'normalized:'+cid,3e-6)
            predicted=detail['local_prediction']
            if method=='pointfilter':
                rotation=torch.from_numpy(detail['pca_inverse'].astype(np.float32))
                delta=torch.bmm(rotation,torch.from_numpy(predicted).unsqueeze(2)).squeeze(2).numpy().astype(float)*radius
            else:delta=np.einsum('qij,qj->qi',detail['pca_inverse'],predicted)*radius
            close(delta,detail['restored_displacement'],cid+'_restore')
            expected_candidate=current.copy();expected_candidate[free_ids]+=delta
            same(expected_candidate,candidate,cid+'_synchronous update');same(full[nonfree],candidate[nonfree],cid+'_held source')
            rows=[0,(len(free_ids)-1)//2,len(free_ids)-1]
            for row in rows:
                lo,hi=detail['neighbor_offsets'][row:row+2]
                exact=np.flatnonzero(np.sum((current-current[free_ids[row]])**2,axis=1)<=radius*radius)
                same(exact,np.sort(detail['neighbor_source_ids'][lo:hi]),cid+'_brute neighbors')
                if method=='pointfilter':replay_x.append(detail['normalized_points'][row]);replay_y.append(predicted[row])
                else:close(mls(detail['normalized_points'][row]),predicted[row],cid+'_independent MLS',3e-8)
            current=candidate
    masks={'A':graph['allowed_mask'],'S':support,'N':graph['allowed_mask']&~support,'N_F':graph['free_mask']&~support}
    triangles=sources[source]['triangles']; selected=np.flatnonzero(np.any(np.isin(triangles,context[masks['A']]),axis=1))
    same(np.sort(mapping['incident_source_face_ids']),selected,cid+'_full incident set')
    before_cross=np.cross(full[triangles[selected,1]]-full[triangles[selected,0]],full[triangles[selected,2]]-full[triangles[selected,0]])
    for method,r in case['methods'].items():
        full_out=full if method=='no_op' else npy(r['candidate_path']);cand=full_out[context]
        residual=np.linalg.norm(cand-ref,axis=1)
        for group,mask in masks.items():
            err=residual[mask]; saved=r['errors'][group];check(saved['count']==len(err),cid+'_denominator')
            if len(err):close([np.sqrt(np.mean(err*err)),np.quantile(err,.95),max(err)],[saved['rmse_native'],saved['p95_native'],saved['max_native']],cid+'_errors')
            else:check(saved['rmse_native'] is None,cid+'_empty S')
        same(cand[~graph['free_mask']],obs[~graph['free_mask']],cid+'_protected')
        same(full_out[nonfree],full[nonfree],cid+'_outside full')
        after=np.cross(full_out[triangles[selected,1]]-full_out[triangles[selected,0]],full_out[triangles[selected,2]]-full_out[triangles[selected,0]])
        valid=np.linalg.norm(before_cross,axis=1)>0; valid_after=np.linalg.norm(after,axis=1)>0
        flip=selected[valid&valid_after&(np.sum(before_cross*after,axis=1)<0)]
        deg=selected[valid&~valid_after]
        same(flip,r['incident_quality']['reversed_source_face_ids'],cid+'_flips');same(deg,r['incident_quality']['new_degenerate_source_face_ids'],cid+'_degeneration')
        preserve=all(r['errors'][g]['p95_native']/scale<=.02 and r['errors'][g]['max_native']/scale<=.10 for g in ('N','N_F'))
        check(preserve==r['normal_point_preservation_passed'],cid+'_normal gate')
        if case['normal_control']:
            ec=r['errors']['A'];passed=ec['rmse_native']/scale<=.01 and ec['p95_native']/scale<=.02 and ec['max_native']/scale<=.05
            check(passed==r['normal_control_passed'],cid+'_control gate')
        if support.any():
            s0=np.linalg.norm(obs[support]-ref[support],axis=1);ratio=np.sqrt(np.mean(residual[support]**2)/np.mean(s0*s0));close(ratio,r['support_rmse_ratio_to_noop'],cid+'_S ratio')
            a0=np.linalg.norm(obs[masks['A']]-ref[masks['A']],axis=1); improvement=1-np.sqrt(np.mean(residual[masks['A']]**2)/np.mean(a0*a0));close(improvement,r['allowed_improvement_to_noop'],cid+'_A improvement')
        for direction in ('candidate_to_reference','reference_to_candidate'):
            sr=r['surface'][direction]; detail=npz(sr['detail_path']);surface_records+=1
            query=(cand if direction=='candidate_to_reference' else ref)[masks['A']]
            surface=(ref if direction=='candidate_to_reference' else cand)
            query=(query-origin)/scale; surface=(surface-origin)/scale
            close(query,detail['query_normalized'],cid+'_surface query')
            ids=[0,(len(query)-1)//2,len(query)-1]
            d2,_=nearest(query[ids],surface,mapping['context_triangles']);surface_queries+=len(ids)
            close(d2,detail['distance2'][ids],'surface:'+cid,5e-11)
            d2=detail['distance2']; saved=sr['distance']
            close([np.mean(d2),np.sqrt(np.mean(d2)),np.quantile(np.sqrt(d2),.95),np.sqrt(max(d2))],[saved[k] for k in ('mean_squared_distance','RMSE','p95','max')],cid+'_surface summary')
        summary.append({'id':cid,'method':method,'normal':case['normal_control'],'source':source,'position':case['position_group'],'support_ratio':r['support_rmse_ratio_to_noop'],'A_improvement':r['allowed_improvement_to_noop'],'normal_passed':preserve,'flips':len(flip),'surface_RMSE':r['surface']['symmetric_RMSE']})
predictions=[]
with torch.inference_mode():
    for start in range(0,len(replay_x),64):predictions.append(model(torch.from_numpy(np.stack(replay_x[start:start+64])).transpose(2,1).contiguous()).numpy())
close(np.concatenate(predictions),np.asarray(replay_y),'actual forward',2e-5)
pf=[r for r in summary if r['method']=='pointfilter']; dents=[r for r in pf if not r['normal']]
ratios=[r['support_ratio'] for r in dents];aggregate={'S_ratio_median':float(np.median(ratios)),'S_ratio_p95':float(np.quantile(ratios,.95)),'S_ratio_max':float(max(ratios)),'A_improvement_median':float(np.median([r['A_improvement'] for r in dents])),'normal_protection_failed':sum(not r['normal_passed'] for r in pf),'flips_sum':sum(r['flips'] for r in pf),'normal_controls':sum(r['normal'] for r in pf)}
cost=read(B/'COSTS.json'); phases=cost['phases'];wall=sum(x['controller']['main_wall_s_including_worker_before_write'] for x in phases.values());cpu=sum(x['worker_tree']['tree_cpu_s'] for x in phases.values());peak=max(x['worker_tree']['tree_sampled_peak_working_set_bytes'] for x in phases.values())
close([wall,cpu,peak],[cost['sequential_controller_main_wall_sum_s'],cost['worker_tree_CPU_sum_s'],965095424],'cost sums')
out={'status':'passed','assertions':checks,'full_inputs':len(E['cases']),'iterations':iterations,'coordinate_and_incident_cases':len(summary),'surface_directions_summaries':surface_records,'surface_independent_min_queries':surface_queries,'actual_model_forward_queries':len(replay_x),'independent_MLS_queries':222,'max_errors':errors,'aggregate':aggregate,'checked_payload_files':len(checked),'cost_arithmetic':{'phase_wall_s':wall,'worker_CPU_s':cpu,'sampled_peak_bytes':peak},'cases':summary,'wall_s':time.perf_counter()-START,'CPU_s':time.process_time()-CPU,'not_run':['new training','new repair','full 85248-query surface minimization','formal cost benchmark','Bunny','product QA']}
(HERE/'INDEPENDENT_RESULTS.json').write_bytes((json.dumps(out,ensure_ascii=False,indent=2)+'\n').encode())
print(json.dumps({k:v for k,v in out.items() if k not in ('cases','max_errors')},ensure_ascii=False))
