from fractions import Fraction as F
import pathlib,json,hashlib
root=pathlib.Path('verification/m4_local_relation_evidence_001').resolve(); run=root/'entry/run_01'
frozen_path=root.parent/'m4_observation_baseline_001/scoring/source/qual001/admin/world_geometry.json'
sha=lambda raw:hashlib.sha256(raw).hexdigest()
enc=lambda value:json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf8')
inputs={}; issues=[]; checks=[]; outputs=[]; proofs={}
def load(path):
 raw=path.read_bytes(); inputs[str(path)]=sha(raw); return json.loads(raw)
def check(value,label):
 checks.append(label)
 if not value:issues.append(label)
def qpoint(p):return tuple(F.from_float(float(x)) for x in p)
def add(a,b):return tuple(x+y for x,y in zip(a,b))
def sub(a,b):return tuple(x-y for x,y in zip(a,b))
def mul(a,t):return tuple(x*t for x in a)
def dot(a,b):return sum((x*y for x,y in zip(a,b)),F(0))
def cross(a,b):return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])
def rational(value):
 if isinstance(value,F):return str(value)
 if isinstance(value,(tuple,list)):return [rational(x) for x in value]
 if isinstance(value,dict):return {k:rational(v) for k,v in value.items()}
 return value
def analytic_crossing(triangles):
 # Solve both plane equations with one coordinate fixed to zero. Bound the
 # resulting line using affine barycentric inequalities, not product predicates.
 a,b=triangles; normals=[cross(sub(t[1],t[0]),sub(t[2],t[0])) for t in triangles]
 direction=cross(*normals); assert any(direction),'parallel planes'
 k=max(range(3),key=lambda axis:abs(direction[axis])); u,v=[i for i in range(3) if i!=k]
 na,nb=normals; da,db=dot(na,a[0]),dot(nb,b[0]);det=na[u]*nb[v]-na[v]*nb[u];assert det
 origin=[F(0)]*3;origin[u]=(da*nb[v]-na[v]*db)/det;origin[v]=(na[u]*db-da*nb[u])/det;origin=tuple(origin)
 slope=tuple(x/direction[k] for x in direction);assert slope[k]==1
 assert dot(na,origin)==da and dot(nb,origin)==db and dot(na,slope)==dot(nb,slope)==0
 bounds=[];affines=[]
 for triangle in triangles:
  e,f=sub(triangle[1],triangle[0]),sub(triangle[2],triangle[0]);w=sub(origin,triangle[0])
  ee,ef,ff=dot(e,e),dot(e,f),dot(f,f);g=ee*ff-ef*ef;assert g>0
  b0=(dot(w,e)*ff-dot(w,f)*ef)/g;c0=(dot(w,f)*ee-dot(w,e)*ef)/g
  b1=(dot(slope,e)*ff-dot(slope,f)*ef)/g;c1=(dot(slope,f)*ee-dot(slope,e)*ef)/g
  initial=(1-b0-c0,b0,c0);rates=(-b1-c1,b1,c1);affines.append((initial,rates))
  for x,y in zip(initial,rates):
   if y:bounds.append(('low' if y>0 else 'high',-x/y))
   else:assert x>=0,'line outside triangle'
 low=max(x for kind,x in bounds if kind=='low');high=min(x for kind,x in bounds if kind=='high');assert low<high,'no transverse segment'
 parameter=(low+high)/2;middle=add(origin,mul(slope,parameter));barycentric=[]
 for triangle,normal,(initial,rates) in zip(triangles,normals,affines):
  bary=tuple(x+y*parameter for x,y in zip(initial,rates));assert all(x>0 for x in bary) and sum(bary)==1
  assert dot(normal,sub(middle,triangle[0]))==0;barycentric.append(bary)
 return {'segment_world_m':[add(origin,mul(slope,low)),add(origin,mul(slope,high))], 'exact_midpoint_world_m':middle,'strict_triangle_barycentric':barycentric,'nonparallel_normal_cross':direction,'point_parameter_axis':k}
frozen=load(frozen_path);check(inputs[str(frozen_path)]=='daa66107b5b6787dd0083ba5794cb9507218ab8717ee57eb593b749616fd65ab','frozen.source_pin')
check(frozen['unit']=='m' and frozen['coordinate_frame']=='world','frozen.world_m_contract')
old={row['name']:row for row in frozen['objects']}; summary=load(run/'RESULTS.json')
check(summary['passed'] is True and summary['owned_scene_attempts']==4 and summary['model_consumers']==0,'saved_entry.four_passed_zero_consumers')
profile_bindings={}
for profile in ('C','S'):
 folder=run/('candidate_'+profile); initial=load(folder/'owner/INITIAL.json'); final=load(folder/'owner/FINAL.json'); identity=load(folder/'owner/IDENTITY.json');rpc=load(folder/'owner/plugin/RPC.json');config=load(folder/'ACTOR_CONFIG.json')
 check(initial==final,profile+'.recorded_initial_final_equal')
 check(identity['runtime_identity']['source_sha256']=='53db41976085ce5f361d026196f4da5faf80d639af33dfced35ba58e328ef732' and identity['runtime_identity']['source_kind']=='installed_distribution',profile+'.actual_installed_candidate_pin')
 check(config['asset_sha256']=='91129d2e82749162bd0c9f4b232be10bd74d422be53c73e248325c0894b14a85',profile+'.original_asset_pin')
 current={row['name']:row for row in initial['objects']}; scale=initial['unit_scale_m'];source_rows={}
 for name in ('N16','N13'):
  old_mesh=old[name];current_mesh=current[name]
  check(current_mesh['vertices_local']==old_mesh['local_vertices'],profile+'.'+name+'.complete_local_vertices_exact')
  check(current_mesh['matrix_world']==old_mesh['matrix_world'],profile+'.'+name+'.matrix_exact')
  check(current_mesh['faces']==old_mesh['polygons'],profile+'.'+name+'.raw_polygon_topology_exact')
  matrix=current_mesh['matrix_world'];world=[[(sum(matrix[r][c]*p[c] for c in range(3))+matrix[r][3])*scale for r in range(3)] for p in current_mesh['vertices_local']]
  check(world==old_mesh['world_vertices'],profile+'.'+name+'.complete_saved_affine_world_binary64_exact')
  source_rows[name]={'vertex_count':len(world),'raw_polygon_count':len(current_mesh['faces']),'frozen_triangle_count':len(old_mesh['triangles']),'full_world_vertices_sha256':sha(enc(world))}
 profile_bindings[profile]={'source_meshes':source_rows,'initial_sha256':inputs[str(folder/'owner/INITIAL.json')],'final_sha256':inputs[str(folder/'owner/FINAL.json')],'source_kind':identity['runtime_identity']['source_kind']}
 for index in range(1,7):
  label=profile+'.request_'+str(index);tool=folder/'owner'/('tool_'+str(index).zfill(2)); measurement=load(tool/'ENTRY_MEASUREMENT.json'); response=load(tool/'RESPONSE.json');request=load(tool/'REQUEST.json'); body=measurement['original_body']
  check(json.loads(response['result']['content'][0]['text'])==body,label+'.owner_original_body_exact')
  rpc_matches=[(i+1,row) for i,row in enumerate(rpc['requests']) if row.get('request_id')==request['id']]
  check(len(rpc_matches)==1,label+'.single_saved_product_rpc_receipt')
  offset,receipt=rpc_matches[0];wire_path=folder/'owner/plugin'/str(offset).zfill(3)/'RX.bin';wire=load(wire_path)
  check(json.loads(wire['result']['content'][0]['text'])==body,label+'.actual_stdio_body_exact')
  context=body['binding'] if profile=='C' else body['context']
  check(context['runtime_source_sha256']=='53db41976085ce5f361d026196f4da5faf80d639af33dfced35ba58e328ef732',label+'.body_source_pin')
  if profile=='C':
   names=[x['name'] for x in body['binding']['objects']];closed_fact=body['pairs'][0]['facts']['closed_solid_relation'];pair_order=body['pair_order']
   check(names==['N16','N13','N08','N28'],label+'.actual_binding_object_order')
  else:
   closed_fact=body['candidates'][0]['closed_solid_relation'];pair_order=context['pair_order']
   check(body['target']['name']=='N16' and [x['name'] for x in body['candidates']]==['N13','N08','N28'] and body['candidates'][0]['candidate_index']==0,label+'.actual_binding_object_order')
  check(pair_order=='target_to_candidate',label+'.target_to_candidate_contract')
  check(closed_fact==measurement['facts'][0]['closed'] if profile=='C' else closed_fact['local_evidence']==measurement['facts'][0]['closed']['local_evidence'],label+'.retained_fact_consistent')
  check(closed_fact['status']=='measured' and closed_fact['value']=='penetrating' and closed_fact['certificate']=='transverse_boundary_interiors',label+'.original_relation_certificate')
  evidence=closed_fact['local_evidence'];check(evidence['type']=='transverse_triangle_crossing',label+'.typed_transverse_evidence')
  check(evidence['triangle_scope']=='current_capture_zero_based_triangles_target_then_candidate_not_polygon_ids',label+'.triangle_index_scope')
  check(evidence['point_scope']=='boundary_crossing_localization_not_volume_interior_or_penetration_depth',label+'.boundary_not_volume_semantics')
  check(len(evidence['triangle_indices'])==len(evidence['triangle_vertices_world_m'])==2,label+'.exactly_two_ordered_surfaces')
  triangles=[];vertex_indices=[]
  for side,name in enumerate(('N16','N13')):
   ordinal=evidence['triangle_indices'][side]; mesh=old[name]
   check(type(ordinal) is int and 0<=ordinal<len(mesh['triangles']),label+'.'+name+'.valid_frozen_triangle_ordinal')
   ids=mesh['triangles'][ordinal];expected=[mesh['world_vertices'][i] for i in ids]
   check(evidence['triangle_vertices_world_m'][side]==expected,label+'.'+name+'.same_ordinal_exact_source_vertices')
   triangles.append(tuple(qpoint(p) for p in expected));vertex_indices.append(ids)
  proof_key=sha(enc(evidence))
  if proof_key not in proofs:
   proof=analytic_crossing(triangles);middle=proof['exact_midpoint_world_m'];point=qpoint(evidence['point_world_m'])
   error_squared=sum(((a-b)**2 for a,b in zip(point,middle)),F(0));tolerance=F.from_float(evidence['publication_tolerance_m'])
   check(len(evidence['point_world_m'])==3 and evidence['point_status']=='approximate' and 'point_reason' not in evidence,label+'.published_point_status')
   check(evidence['publication_tolerance_m']==1e-9 and error_squared<=tolerance*tolerance,label+'.independent_exact_publication_error_bound')
   proofs[proof_key]={'triangle_indices':evidence['triangle_indices'],'ordered_objects':['N16','N13'],'frozen_triangle_vertex_indices':vertex_indices,'independent_analytic_proof':rational(proof),'published_point_world_m':evidence['point_world_m'],'exact_publication_error_squared_m2':str(error_squared),'tolerance_m':evidence['publication_tolerance_m'],'exact_midpoint_on_both_boundaries':True,'exact_midpoint_strict_relative_triangle_interior':True,'shared_volume_interior_or_penetration_depth_claimed':False}
  outputs.append({'profile':profile,'request_index':index,'proof_sha256':proof_key,'ENTRY_MEASUREMENT_sha256':inputs[str(tool/'ENTRY_MEASUREMENT.json')],'actual_product_RX_sha256':inputs[str(wire_path)],'source_pair_order_verified':True,'same_index_source_vertices_verified':True})
check(len(outputs)==12,'all_twelve_candidate_C_S_requests_reviewed')
check(len(proofs)==1,'cold_and_repeated_C_S_local_payload_equal')
for path,digest in inputs.items():check(sha(pathlib.Path(path).read_bytes())==digest,'unchanged.'+path)
report={'cycle_id':'M4-LOCAL-RELATION-EVIDENCE-001','review':'saved_installed_entry_local_proof','status':'PASS' if not issues else 'FAIL','issues':issues,'checks_total':len(checks),'checks_passed':len(checks)-len(issues),'candidate_source_sha256':'53db41976085ce5f361d026196f4da5faf80d639af33dfced35ba58e328ef732','reviewed_candidate_requests':len(outputs),'distinct_local_payloads':len(proofs),'profiles':profile_bindings,'requests':outputs,'independent_proofs':proofs,'input_sha256':inputs,'method':'Pure saved-coordinate Fraction analysis: solve the two plane equations, parameterize their common line, intersect six affine barycentric nonnegativity bounds, and check midpoint strictly relative-interior to both triangles. Published-point squared error is exact rational arithmetic. No product or QA module import.','source_mapping_scope':'Returned zero-based ordinals and all six world vertices exactly match the SHA-frozen triangle list at the same indices. Actual saved complete local vertices, matrices and raw polygons equal that frozen source; re-evaluated saved affine world binary64 vertices also equal it. No new full capture/tessellation, polygon-ID inference or Blender call was performed.','boundary_semantics':'Exact line midpoint lies on both boundary surfaces, with nonparallel planes. A rounded published coordinate is localization only. This review does not construct or claim a shared volume-interior point, penetration depth or new independent closed-shell qualification.','lifecycle_scope':'Saved initial/final equality and installed producer identity are checked as existing records; this does not prove absence of all transient changes. Independent lifecycle audit belongs to root.','product_or_QA_imports':0,'production_geometry_solves':0,'new_Blender_or_product_sessions':0,'new_model_consumers':0,'new_capture_requests':0,'original_materials_modified':False}
output=root/'ENTRY_LOCAL_PROOF_REVIEW.json'
with output.open('x',encoding='utf8',newline='\n') as f:json.dump(report,f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n')
print(json.dumps({'status':report['status'],'issues':issues,'checks_total':len(checks),'reviewed_requests':len(outputs),'distinct_proofs':len(proofs),'triangle_indices':next(iter(proofs.values()))['triangle_indices'],'point_error_squared_m2':next(iter(proofs.values()))['exact_publication_error_squared_m2'],'report':str(output)},ensure_ascii=False))
