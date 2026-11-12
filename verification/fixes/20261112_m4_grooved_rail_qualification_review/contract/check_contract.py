"""Read-only independent frozen-contract audit. No Blender/product imports."""
from pathlib import Path
from fractions import Fraction as F
import hashlib
import json
import struct
from datetime import datetime

B = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_grooved_rail_transfer_001')
OUT = Path(__file__).resolve().parent
def rd(p): return json.loads(p.read_bytes())
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def f32(x): return struct.unpack('<f', struct.pack('<f', float(x)))[0]
checks = []
def check(name, condition, detail=None):
    checks.append({'check': name, 'passed': bool(condition), 'detail': detail})
def det(a,b,c):
    return a[0]*(b[1]*c[2]-b[2]*c[1])-a[1]*(b[0]*c[2]-b[2]*c[0])+a[2]*(b[0]*c[1]-b[1]*c[0])
def sub(a,b): return [x-y for x,y in zip(a,b)]
def tetra_faces(v):
    d=det(*[sub(v[i],v[0]) for i in (1,2,3)])
    faces=[[0,2,1],[0,1,3],[0,3,2],[1,2,3]]
    return faces if d>0 else [t[::-1] for t in faces]

# Fresh transcription from the frozen DESIGN, not BUILD_RESULT or author oracle.
poly=[[F(x),F(z)] for x,z in [('0','0'),('40','0'),('22.4','13.2'),('14','2'),('1.2','11.6'),('9.6','22.8'),('0','30')]]
target=[[x,F(y),z] for y in (-20,20) for x,z in poly]
caps=[[0,1,3],[1,2,3],[0,3,4],[0,4,6],[4,5,6]]
tf=caps+[[k+7 for k in t[::-1]] for t in caps]
for i in range(7):
    j=(i+1)%7
    tf.extend([[i,i+7,j+7],[i,j+7,j]])
av=[]
for s,y,h in [('2','2','15.25'),('0','-2','20.25'),('4','-2','20.25'),('2','8','20.25')]:
    s,y,h=F(s),F(y),F(h)
    av.append([(4*s+3*h)/5,y,(-3*s+4*h)/5])
n=[F(-3,5),F(0),F(-4,5)]; t=[F(4,5),F(0),F(-3,5)]
q=[F(0)+F('2.75')*n[0],F(5),F('2.75')*n[2]]
bv=[[q[i]+sgn*6*t[i] for i in range(3)] for sgn in (1,-1)]
bv.extend([[q[i]+8*n[i]+(sgn*6 if i==1 else 0) for i in range(3)] for sgn in (1,-1)])
cv=[[F(x) for x in v] for v in [(10,'28.5',2),(16,'36.5',-2),(4,'36.5',-2),(10,'36.5',10)]]
expected={'Target':(target,tf),'Part_A':(av,tetra_faces(av)),'Part_B':(bv,tetra_faces(bv)),'Part_C':(cv,tetra_faces(cv))}
snapshot=rd(B/'asset/ACTUAL_SNAPSHOT.json')
build=rd(B/'asset/BUILD_RESULT.json')
freeze=rd(B/'FREEZE.json')
check('root_plan_exact_copy',(B/'spec/PLAN.md').read_bytes()==Path('D:/hefe/docs/M4_GROOVED_RAIL_TRANSFER_001_PLAN.md').read_bytes())
check('root_design_exact_copy',(B/'spec/DESIGN.md').read_bytes()==Path('D:/hefe/verification/fixes/20261112_m4_spatial_fact_cost_review/design/REVIEW.md').read_bytes())
objects={o['name']:o for o in snapshot['objects']}
check('exact_four_object_names',set(objects)==set(expected))
check('actual_counts',snapshot['counts']=={'objects':4,'vertices':26,'triangles':36} and sum(len(o['vertices_local']) for o in objects.values())==26 and sum(len(o['triangles']) for o in objects.values())==36)
R=[[-10,2,11],[10,-5,10],[5,14,2]]; T=[120,-80,240]
ideal=[[F(x,15000) for x in row]+[F(T[i],1000)] for i,row in enumerate(R)]+[[F(0),F(0),F(0),F(1)]]
input_matrix=[[f32(x) for x in row] for row in ideal]
check('matrix_input_is_frozen_R_T',build['matrix_world_input_binary32']==input_matrix)
check('units',snapshot['unit']=='m' and snapshot['coordinate_frame']=='world' and snapshot['local_coordinate_unit']=='mm' and snapshot['scale_length']==snapshot['unit_scale_m']==1 and snapshot['unit_system']=='METRIC' and snapshot['unit_length']=='METERS')
check('scene_properties_empty',not snapshot['scene_custom_properties'])
max_world_nominal_error=0.0; max_matrix_error=0.0
default_attrs={'.select_vert','position','.corner_vert','.corner_edge','.select_poly','sharp_face','.edge_verts','.select_edge'}
for name,(v,faces) in expected.items():
    o=objects[name]
    check(name+'_78_total_local_components_binary32',o['vertices_local']==[[f32(c) for c in p] for p in v])
    check(name+'_exact_triangle_indices',o['triangles']==o['faces']==faces)
    check(name+'_no_answer_metadata',o['mesh_name']==name and not o['object_custom_properties'] and not o['mesh_custom_properties'] and not o['material_names'] and all(a['name'] in default_attrs for a in o['mesh_attributes']))
    check(name+'_static_explicit_mesh',o['type']=='MESH' and o['parent'] is None and not o['modifiers'] and not o['constraints'] and not o['animation_present'] and not o['shape_keys_present'])
    check(name+'_matrix_identity_across_objects',o['matrix_world']==objects['Target']['matrix_world']==o['matrix_local']==o['matrix_basis'])
    world=[[[((o['matrix_world'][a][0]*p[0]+o['matrix_world'][a][1]*p[1])+o['matrix_world'][a][2]*p[2])+o['matrix_world'][a][3] for a in range(3)] for p in o['vertices_local']]][0]
    check(name+'_world_binary64_recomputed',world==o['vertices_world'])
    for vi,p in enumerate(v):
        for a in range(3):
            nominal=sum(F(R[a][k],15000)*p[k] for k in range(3))+F(T[a],1000)
            max_world_nominal_error=max(max_world_nominal_error,abs(float(nominal)-world[vi][a]))
    max_matrix_error=max(max_matrix_error,max(abs(o['matrix_world'][a][c]-input_matrix[a][c]) for a in range(4) for c in range(4)))
    edges={}
    for fi,face in enumerate(faces):
        for a,b in zip(face,face[1:]+face[:1]): edges.setdefault(tuple(sorted((a,b))),[]).append((a,b,fi))
    check(name+'_all_edges_two_opposite_uses',all(len(e)==2 and e[0][:2]==e[1][:2][::-1] for e in edges.values()),len(edges))
    reached={0}
    while True:
        extra={e[2] for uses in edges.values() if any(e[2] in reached for e in uses) for e in uses}
        if extra<=reached: break
        reached|=extra
    check(name+'_connected_faces',len(reached)==len(faces))
check('world_nominal_error_below_1e_6m',max_world_nominal_error<1e-6,max_world_nominal_error)
check('matrix_decomposition_difference_bound',max_matrix_error<=2.3283064365386963e-10,max_matrix_error)
# Correct cap indices above prevent the forbidden central fan. The cap and polygon
# signed areas also agree exactly using actual binary32 x/z, without snapping.
ap=[[F(p[0]),F(p[2])] for p in objects['Target']['vertices_local'][:7]]
area2=sum(ap[i][0]*ap[(i+1)%7][1]-ap[(i+1)%7][0]*ap[i][1] for i in range(7))
tri_area2=sum((ap[j][0]-ap[i][0])*(ap[k][1]-ap[i][1])-(ap[j][1]-ap[i][1])*(ap[k][0]-ap[i][0]) for i,j,k in caps)
check('actual_cap_area_equals_actual_concave_polygon',area2==tri_area2,{'polygon_area_mm2':str(area2/2),'cap_area_mm2':str(tri_area2/2)})

started=rd(B/'worker/PREPARATION_STARTED.json'); prep=rd(B/'worker/PREPARATION.json')
builder_start=rd(B/'worker/BUILDER_STARTED.json'); builder=rd(B/'worker/BUILDER_CLOSED.json')
session=rd(B/'worker/qa/SESSION.json'); closed=rd(B/'worker/qa/WORKER_CLOSED.json'); close=rd(B/'worker/QA_CLOSE.json')
receipt=rd(B/'worker/EXPORT_RECEIPT.json'); ledger=rd(B/'PREPARATION_LEDGER.json')
helper=B.parents[1]/'verification/native_plugin_complex_003/reused/accepted_native.py'
for field,path in [('controller_sha256',B/'worker/prepare_asset.py'),('build_script_sha256',B/'asset/build_assets.py'),('export_script_sha256',B/'asset/export_snapshot.py'),('freeze_sha256',B/'FREEZE.json'),('helper_sha256',helper)]:
    check(field+'_source_binding',started[field]==sha(path))
check('helper_source_session_binding',session['helper_sha256']==sha(helper))
check('builder_pid_exit_reap',builder['pid']==builder_start['pid']==build['pid'] and builder['exit_code']==0 and builder['process_reaped'])
check('builder_output_hashes',builder['stdout_sha256']==sha(B/'worker/builder_stdout.bin') and builder['stderr_sha256']==sha(B/'worker/builder_stderr.bin'))
check('qa_pid_exit_reap',close['pid']==closed['pid']==session['pid']==snapshot['pid'] and close['exit_code']==0 and close['process_reaped'] and close['error'] is None and close['response']['status']=='closed')
check('qa_closed_identity',not closed['poisoned'] and closed['initial_geometry_fingerprint']==closed['final_geometry_fingerprint'] and close['source_file_unchanged'] and close['protected_files_unchanged'])
check('same_asset_bytes',sha(B/'asset/grooved_rail.blend')==sha(B/'worker/qa/input.blend')==build['asset_sha256']==session['asset_sha256'])
check('raw_receipt_same_snapshot',receipt['response']['status']=='success' and receipt['response']['result']['executed'] is True and json.loads(receipt['response']['result']['result'])==snapshot)
check('qa_script_same_export',(B/'worker/qa/call_1/SCRIPT.py').read_text(encoding='utf8')==(B/'asset/export_snapshot.py').read_text(encoding='utf8'))
check('stdout_same_snapshot',rd(B/'worker/qa/call_1/stdout.txt')==snapshot)
events=[json.loads(line) for line in (B/'worker/qa/WORKER_EVENTS.jsonl').read_text().splitlines()]
check('qa_one_execute_and_one_close',len(events)==2 and events[0]['sequence']==1 and events[0]['status']=='completed' and events[0]['script_error'] is None and events[0]['script_sha256']==sha(B/'asset/export_snapshot.py') and events[1]['sequence']==2 and events[1]['status']=='unknown')
check('no_failure_files_or_logged_errors',not prep['errors'] and not list((B/'worker').rglob('*FAILURE*')) and (B/'worker/builder_stderr.bin').stat().st_size==0 and (B/'worker/qa/worker_stderr.txt').stat().st_size==0 and (B/'worker/qa/call_1/stderr.txt').stat().st_size==0)
check('controller_exact_ns',prep['ended_ns']-prep['started_ns']==prep['elapsed_ns'] and prep['elapsed_ns']/1e9==ledger['asset_controller_wall_s'] and builder['elapsed_ns']/1e9==ledger['builder_wall_s_nested_in_controller'] and close['elapsed_ns']/1e9==ledger['QA_close_wall_s_nested_in_controller'])
oracle_runs=[json.loads(l) for l in (B/'oracle/RUNS.jsonl').read_text().splitlines()]
check('oracle_run_cost_errors',len(oracle_runs)==ledger['oracle_runs']==1 and oracle_runs[0]['exception'] is None and oracle_runs[0]['traceback'] is None and (oracle_runs[0]['analysis_ended_ns']-oracle_runs[0]['started_ns'])/1e9==ledger['oracle_analysis_wall_s'] and oracle_runs[0]['elapsed_through_publication_ns']/1e9==ledger['oracle_with_publication_wall_s'])
check('freeze_window_cost',(datetime.fromisoformat(ledger['finalizer_input_checks_ended_utc'])-datetime.fromisoformat(ledger['frozen_utc'])).total_seconds()==ledger['recorded_freeze_to_finalizer_input_checks_window_s'])
check('reported_product_consumer_images_zero',ledger['evaluation_consumers']==ledger['product_pretests']==ledger['images']==prep['models']==prep['product_processes']==prep['images']==0)
check('only_two_recorded_blender_processes',prep['Blender_sessions_started_or_attempted']==ledger['owned_Blender_processes']==2 and ledger['geometric_candidates']==1 and ledger['construction_failures']==0)
check('fees_honestly_unmeasured',ledger['coordinator_and_review_resource_cost'] is None and ledger['monetary_fee_status']=='unmeasured')
check('no_image_files',not [p for p in B.rglob('*') if p.suffix.lower() in ('.png','.jpg','.jpeg','.webp')])
result={'status':'passed' if all(c['passed'] for c in checks) else 'failed','checks':checks,'check_count':len(checks),'failed':[c for c in checks if not c['passed']], 'snapshot_sha256':sha(B/'asset/ACTUAL_SNAPSHOT.json'),'asset_sha256':sha(B/'asset/grooved_rail.blend'),'denominator':{'objects':4,'local_coordinate_components':78,'world_coordinate_components':78,'triangles':36,'object_edges':54,'owned_process_receipts':2,'QA_execution_events':1,'QA_close_events':1},'scope':'Offline contract/source/receipt audit only. No independent process launch, full distance/containment audit, Git audit or universal negative proof of unrecorded activity.'}
(OUT/'RESULTS.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(json.dumps({k:v for k,v in result.items() if k!='checks'},ensure_ascii=False))
raise SystemExit(0 if result['status']=='passed' else 1)
