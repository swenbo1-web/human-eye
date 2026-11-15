import os
os.environ['OMP_NUM_THREADS']='1';os.environ['OPENBLAS_NUM_THREADS']='1';os.environ['MKL_NUM_THREADS']='1'
import hashlib,heapq,importlib.util,json,re,sys,time,zipfile
from collections import Counter,defaultdict
from pathlib import Path
sys.path.insert(0,'C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_shape_pretrain_001/private/deps')
import numpy as np
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import connected_components,dijkstra
HERE=Path(__file__).resolve().parent;P=HERE/'snapshot/verification/m6_perception_data_001'
count=Counter();maxdiff=defaultdict(float)
def j(name):return json.loads((P/name).read_bytes())
def z(name):
 with np.load(P/name,allow_pickle=False) as p:return {k:p[k] for k in p.files}
def check(tag,a,b=None,exact=False):
 count[tag]+=1
 if b is None:assert bool(a),tag;return
 a=np.asarray(a);b=np.asarray(b);assert a.shape==b.shape,(tag,a.shape,b.shape)
 if exact or a.dtype.kind not in 'fc' or b.dtype.kind not in 'fc':assert np.array_equal(a,b),tag
 else:
  err=float(np.max(np.abs(a-b),initial=0));maxdiff[tag]=max(maxdiff[tag],err)
  assert np.allclose(a,b,rtol=1e-10,atol=1e-12,equal_nan=True),(tag,err)
def parse(raw):
 vertices=[];normals=[];faces=[];normal_ids=[]
 for line in raw.decode('utf-8-sig').splitlines():
  words=line.split()
  if not words:continue
  if words[0]=='v':vertices.append([float(x) for x in words[1:4]])
  elif words[0]=='vn':normals.append([float(x) for x in words[1:4]])
  elif words[0]=='f':
   assert len(words)==4
   cols=[w.split('/') for w in words[1:]]
   faces.append([int(w[0])-1 for w in cols]);normal_ids.append([int(w[2])-1 if len(w)>2 and w[2] else -1 for w in cols])
 return np.array(vertices),np.array(faces),np.array(normals),np.array(normal_ids)
def geometry(v,f):
 n=len(v);diag=np.linalg.norm(np.ptp(v,axis=0));ltol=64*np.finfo(float).eps*diag;atol=ltol*diag
 cross=np.cross(v[f[:,1]]-v[f[:,0]],v[f[:,2]]-v[f[:,0]]);length=np.linalg.norm(cross,axis=1)
 deg=(~np.isfinite(length))|(length<=atol);vc=np.zeros_like(v);area=np.zeros(n)
 for k in range(3):np.add.at(vc,f[:,k],np.where(deg[:,None],0,cross));np.add.at(area,f[:,k],np.where(deg,0,length/6))
 nl=np.linalg.norm(vc,axis=1);norm=np.divide(vc,nl[:,None],out=np.zeros_like(vc),where=nl[:,None]>atol)
 good=np.isfinite(v).all(axis=1)&np.isfinite(nl)&(nl>atol);good[np.unique(f[deg])]=False
 incidence=defaultdict(list)
 for fi,tri in enumerate(f):
  for a,b in ((tri[0],tri[1]),(tri[1],tri[2]),(tri[2],tri[0])):
   incidence[tuple(sorted((int(a),int(b))))].append((fi,1 if a<b else -1))
 edges=np.array(sorted(incidence));weights=np.linalg.norm(v[edges[:,0]]-v[edges[:,1]],axis=1)
 valid=np.isfinite(weights)&(weights>ltol);ee=edges[valid];ww=weights[valid]
 graph=csr_matrix((np.r_[ww,ww],(np.r_[ee[:,0],ee[:,1]],np.r_[ee[:,1],ee[:,0]])),shape=(n,n))
 eligible=good[ee].all(axis=1);eg=ee[eligible];ew=ww[eligible]
 eggraph=csr_matrix((np.r_[ew,ew],(np.r_[eg[:,0],eg[:,1]],np.r_[eg[:,1],eg[:,0]])),shape=(n,n))
 rows=[];cols=[];boundary=[];conflicts=0;nonmanifold=0
 for edge,items in incidence.items():
  if len(items)!=2:boundary.extend(edge)
  if len(items)>2:nonmanifold+=1
  if len(items)==2:
   if items[0][1]!=items[1][1]:rows.extend((items[0][0],items[1][0]));cols.extend((items[1][0],items[0][0]))
   else:conflicts+=1
 fg=csr_matrix((np.ones(len(rows)),(rows,cols)),shape=(len(f),len(f)))
 _,fp=connected_components(fg,directed=False);_,components=connected_components(graph,directed=False)
 return dict(v=v,f=f,diag=diag,ltol=ltol,atol=atol,cross=cross,deg=deg,norm=norm,area=area,good=good,
             graph=graph,eligible_graph=eggraph,edges=edges,boundary=np.unique(boundary).astype(int),face_patch=fp,
             components=components,incidence=incidence,conflicts=conflicts,nonmanifold=nonmanifold)
def argfar(c,d):return int(sorted(c,key=lambda x:(-d[x],x))[0])
def choose_rois(g,rng):
 ids=np.flatnonzero(g['good']);first=int(rng.choice(ids,p=g['area'][ids]/g['area'][ids].sum()));result=[]
 for slot in range(2):
  available=g['good'].copy();graph=g['eligible_graph']
  if slot==0:seed=first
  else:
   available[result[0][1]]=False
   dd=dijkstra(graph,directed=False,indices=result[0][1],min_only=True)
   remaining=np.flatnonzero(available);unreach=remaining[np.isinf(dd[remaining])]
   seed=int(unreach[0]) if len(unreach) else argfar(remaining,dd)
   coo=graph.tocoo();keep=available[coo.row]&available[coo.col]
   graph=csr_matrix((coo.data[keep],(coo.row[keep],coo.col[keep])),shape=graph.shape)
  d=dijkstra(graph,directed=False,indices=seed);c=np.flatnonzero(available&np.isfinite(d))
  result.append((seed,np.sort(c[np.lexsort((c,d[c]))[:384]])))
 return result
def main():
 start=time.perf_counter();cpu=time.process_time();data=j('DATASET_INDEX.json');sources=j('SOURCE_INDEX.json');split=j('SPLIT.json')
 orientations={r['source_id']:r for r in j('ORIENTATION_SOURCE.json')['cases']}
 reader_spec=importlib.util.spec_from_file_location('read_current_copied',P/'data_io.py');reader=importlib.util.module_from_spec(reader_spec);reader_spec.loader.exec_module(reader)
 costs=[];gd={};rng=np.random.default_rng(1729);rows_byroi=defaultdict(list);rois={r['id']:r for r in data['rois']};obs={r['id']:r for r in data['observations']}
 splitids={r['id']:r for r in split['mesh_membership']};archives={r['path'].split('/')[-1].split('-poses')[0]:r for r in sources['archives']}
 curqa={r['id']:r for r in j('CURRENT_GEOMETRY_QA.json')['cases']};failures=Counter();verified=[]
 for row in data['sources']:
  sid=row['id'];archive=archives[row['asset']]
  with zipfile.ZipFile(P/archive['path']) as pack:raw=pack.read(row['member'])
  check('archive_raw_source',raw==(P/row['obj_path']).read_bytes());v,f,vn,fn=parse(raw);saved=z(row['array_path'])
  for key,val in [('vertices',v),('faces',f),('source_normals',vn),('face_normal_ids',fn)]:check('raw_parse_'+key,saved[key],val,True)
  check('split_lineage',row['group']==splitids[sid]['group'] and row['split']==splitids[sid]['split'] and row['asset']==splitids[sid]['mesh_id'])
  g=geometry(v,f);gd[sid]=g
  expected_rois=choose_rois(g,rng)
  for slot,(seed,ids) in enumerate(expected_rois):
   roi=rois[sid+'_roi'+str(slot)];actual=np.load(P/roi['region_mapping'],allow_pickle=False)
   check('ROI_selection',actual,ids,True);check('ROI_seed',seed==roi['seed_source_id'])
   inside=np.zeros(len(v),bool);inside[ids]=True;edges=g['edges'];crossing=edges[inside[edges[:,0]]!=inside[edges[:,1]]]
   boundary=np.unique(np.r_[crossing.ravel(),g['boundary']]);boundary=boundary[inside[boundary]]
   dist=dijkstra(g['graph'],directed=False,indices=boundary,min_only=True)
   c=ids[np.isfinite(dist[ids])];c=c[(dist[c]>=.5*max(dist[c]))&(dist[c]>g['ltol'])]
   chosen=[];nearest=np.full(len(v),np.inf);first=argfar(c,dist)
   for i in range(4):
    center=first if i==0 else argfar(c,nearest);chosen.append(center)
    dc=dijkstra(g['graph'],directed=False,indices=center);nearest=np.minimum(nearest,dc);c=c[c!=center]
    saved_center=roi['centers'][i];check('center_ID',center==saved_center['source_id']);check('center_D',saved_center['D'],dist[center])
    normal=g['norm'][center] # all current orientation signs independently checked +1
    check('center_normal',saved_center['outward_normal'],normal)
    g.setdefault('center_distances',{})[(roi['id'],center)]=dc
   check('ROI_boundary_count',len(boundary)==roi['boundary_count']);check('ROI_count',len(ids)==384)
  # Closed components: independently verify signed volume; open sign is visually checked, not deduced from volume.
  o=orientations[sid];faceid=o['anchor_face'];check('orientation_anchor_position',v[f[faceid]].mean(axis=0),o['anchor_position'])
  check('orientation_anchor_normal',g['cross'][faceid]/np.linalg.norm(g['cross'][faceid]),o['raw_winding_normal']);check('orientation_sign',o['outward_sign']==1)
  if row['asset'] in ('cat','lion'):
   check('closed_manifold',all(len(x)==2 and x[0][1]!=x[1][1] for x in g['incidence'].values()))
   vv=v-v.mean(axis=0);volume=np.einsum('ij,ij->i',vv[f[:,0]],np.cross(vv[f[:,1]],vv[f[:,2]])).sum()/6
   check('closed_positive_volume',volume>256*np.finfo(float).eps*g['diag']**3)
 for o in data['observations']:
  g=gd[o['source_id']];v,f=g['v'],g['f'];roi=rois[o['roi_id']];ids=np.load(P/roi['region_mapping'],allow_pickle=False)
  current=reader.read_current(o);local=z(o['input']['current_local_positions'])['positions'];supervision=z(o['supervision'])
  check('input_fields',set(current)=={'vertices','faces','region_source_ids','mesh_id','pose_id'})
  check('reader_faces',current['faces'],f,True);check('reader_IDs',current['region_source_ids'],ids,True);check('reader_local',current['vertices'][ids],local,True)
  outside=np.ones(len(v),bool);outside[ids]=False;check('outside_F_bitwise',current['vertices'][outside].tobytes()==v[outside].tobytes())
  if o['state']=='normal':expected=v.copy();ideal=np.zeros(len(v),bool)
  else:
   center=o['center_source_id'];dc=g['center_distances'][(roi['id'],center)]
   D=roi['centers'][o['center_slot']]['D'];r=(.35,.55)[o['radius_index']]*D;a=(.05,.15,.30)[o['depth_index']]*r
   check('radius',o['radius'],r);check('depth',o['depth'],a);ideal=dc<r
   addition=-a*((1-(dc[ideal]/r)**2)**2)[:,None]*g['norm'][center];expected=v.copy();region=expected[ideal].copy();nz=addition!=0;region[nz]+=addition[nz];expected[ideal]=region
  check('formula_current',current['vertices'],expected)
  actual=current['vertices']-v;changed=np.any(actual!=0,axis=1)
  check('normal_reference_label',supervision['normal_positions'],v[ids],True);check('actual_delta_label',supervision['actual_delta'],actual[ids],True)
  check('mask_label',supervision['changed_mask'],changed[ids],True);check('norm_label',supervision['displacement_norm'],np.linalg.norm(actual[ids],axis=1))
  check('outside_ideal_bitwise',current['vertices'][~ideal].tobytes()==v[~ideal].tobytes())
  check('current_source_finite',np.isfinite(current['vertices']).all())
  rows_byroi[o['roi_id']].append(o)
  if o['state']=='normal':check('normal_zero',not changed.any());continue
  cv=current['vertices'];cc=np.cross(cv[f[:,1]]-cv[f[:,0]],cv[f[:,2]]-cv[f[:,0]])
  reverse=(np.einsum('ij,ij->i',cc,g['cross'])<=0)&~g['deg'];deg=(np.linalg.norm(cc,axis=1)<=g['atol'])&~g['deg']
  affected=np.any(changed[f],axis=1);patches=np.unique(g['face_patch'][affected]);check('affected_orientation_patches',o['affected_orientation_patches'],patches,True)
  direction=(o['mesh_id'] in ('cat','lion')) or (len(patches)>0 and np.all(patches==orientations[o['source_id']]['patch']))
  check('direction_numeric_scope',direction==o['direction_confirmed'])
  check('true_support',o['true_support_points']==int(changed.sum()));check('ideal_support',o['ideal_support_points']==int(ideal.sum()))
  check('local_face_reversal',o['reversed_faces']==int(reverse.sum()));check('new_degeneracy',o['new_degenerate_faces']==int(deg.sum()))
  check('target_area',o['target_lumped_area'],g['area'][changed].sum());check('max_displacement',o['max_true_displacement'],np.linalg.norm(actual,axis=1).max())
  expected_fail=[]
  if changed.sum()<6:expected_fail.append('support_minimum')
  if reverse.any():expected_fail.append('no_face_reversal')
  if deg.any():expected_fail.append('no_new_degeneracy')
  if not direction:expected_fail.append('direction_unknown')
  check('all_failure_reasons',set(o['failures'])==set(expected_fail));failures.update(expected_fail)
  check('numerical_valid',o['numerical_valid']==(not [x for x in expected_fail if x!='direction_unknown']))
  check('usable_pair',o['usable_for_training']==(not expected_fail))
  cq=curqa[o['id']];diag=np.linalg.norm(np.ptp(cv,axis=0));R=.05*diag;near=np.linalg.norm(cv-cv[o['center_source_id']],axis=1)<R
  for key,val in [('current_bbox_diagonal',diag),('current_encoder_radius',R),('radius_over_current_encoder_radius',o['radius']/R),('depth_over_current_encoder_radius',o['depth']/R),('current_encoder_neighborhood_points',near.sum()),('current_encoder_neighborhood_damaged_points',(near&changed).sum()),('current_encoder_neighborhood_damaged_fraction',(near&changed).sum()/near.sum())]:check('current_neighborhood_'+key,cq[key],val)
  normal_sums=np.zeros_like(cv)
  for k in range(3):np.add.at(normal_sums,f[:,k],cc)
  bad=~np.isfinite(normal_sums).all(axis=1)|(np.linalg.norm(normal_sums,axis=1)<=64*np.finfo(float).eps*diag**2)
  check('new_unavailable_normals',cq['newly_unavailable_vertex_normals']==int((bad&g['good']).sum()))
  verified.append({'id':o['id'],'split':o['split'],'usable':o['usable_for_training'],'true_support':int(changed.sum()),'reversed_faces':int(reverse.sum()),'r_over_encoder_R':float(o['radius']/R),'encoder_context_damaged_fraction':float((near&changed).sum()/near.sum())})
 for roi,rr in rows_byroi.items():
  valid_centers=sorted({x['center_source_id'] for x in rr if x['state']=='damaged' and x['usable_for_training']})
  check('ROI_valid_centers',rois[roi]['valid_centers'],valid_centers,True);check('ROI_usable',len(valid_centers)>=2 and rois[roi]['usable_for_training'])
 for pair in data['pairs']:
  normal=obs[pair['normal_observation_id']];damaged=obs[pair['damaged_observation_id']]
  check('pair_states',normal['state']=='normal' and damaged['state']=='damaged')
  for key in ('source_id','mesh_id','pose_id','group','split','roi_id'):check('pair_lineage',pair[key]==normal[key]==damaged[key])
  check('pair_eligibility',pair['usable_for_training']==damaged['usable_for_training'])
  check('pair_mapping',normal['input']['region_mapping']==damaged['input']['region_mapping']==pair['region_mapping'])
 qa=j('DATA_QA.json');check('failure_totals',dict(failures)==qa['failure_reasons'])
 groups={}
 for group in ('development','validation'):
  rr=[x for x in verified if x['split']==group];usable=[x for x in rr if x['usable']]
  groups[group]={'attempts':len(rr),'usable':len(usable),'failed':len(rr)-len(usable),'zero_external_reference_context_at_center':sum(x['encoder_context_damaged_fraction']==1 for x in usable),'r_over_R_quantiles':np.quantile([x['r_over_encoder_R'] for x in usable],[0,.5,.95,1]).tolist()}
 out={'status':'passed','assertions':sum(count.values()),'checks':dict(count),'max_differences':dict(maxdiff),'coverage':{'raw_sources':12,'ROIs':24,'centers':96,'observations':600,'dents':576,'saved_sampler_rows':'separate sampler review'},'failure_reasons':dict(failures),'groups':groups,'cases':verified,'wall_s':time.perf_counter()-start,'CPU_s':time.process_time()-cpu,'scope':['Independent raw parsing/topology/ROI/center/geometry/label reconstruction; copied data_io used as actual reader entry and compared against own geometry.','Open orientation sign checked from 8 source views; all local propagation checked numerically. Global self intersection not tested.','No model forward or training; dataset engineering does not establish learning benefit.']}
 (HERE/'GEOMETRY_RESULTS.json').write_bytes((json.dumps(out,ensure_ascii=False,indent=2)+'\n').encode());print(json.dumps({k:out[k] for k in ('status','assertions','coverage','failure_reasons','groups','wall_s','CPU_s')}))
if __name__=='__main__':main()
