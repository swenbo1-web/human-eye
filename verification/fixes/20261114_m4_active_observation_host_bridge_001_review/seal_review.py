"""Seal root review and one bounded delivery repair plan, without runtime calls."""
from pathlib import Path
import hashlib,json,subprocess
ROOT=Path('D:/hefe');OUT=Path(__file__).resolve().parent
AUTHOR=Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
COMMIT='32a1c6eb47cfa84133d92199387339d407a33cb5'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_bytes())
def save(p,v):
    with Path(p).open('x',encoding='utf8',newline='\n') as f:f.write(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert subprocess.check_output(['git','-C',str(AUTHOR),'rev-parse','HEAD'],text=True).strip()==COMMIT
assert not subprocess.check_output(['git','-C',str(AUTHOR),'status','--porcelain','--untracked-files=all'])
counts={}
for name,path,count in [('identity','IDENTITY.json',3453),('semantics','semantics/RESULTS.json',112),('transport','transport/RESULTS.json',980),('cost','cost/RESULTS.json',901)]:
    v=read(OUT/path);assert v['passed'] and v['check_count']==count
    counts[name]={'checks':count,'path':path,'sha256':sha(OUT/path)}
review=ROOT/'docs/M4_ACTIVE_OBSERVATION_HOST_BRIDGE_001_INDEPENDENT_REVIEW.md'
plan=ROOT/'docs/M4_ACTIVE_OBSERVATION_BRIEF_DELIVERY_001_PLAN.md'
decision={'schema':'root-host-bridge-001-independent-decision-v1','author_commit':COMMIT,
 'decision':'accept_functional_host_connection_keep_short_fact_delivery_P2_open',
 'author_audits_and_root_review_separate':True,'checks':counts,'check_total':sum(v['checks'] for v in counts.values()),
 'checks_meaning':'Overlapping evidence properties; positive check counts include confirming the output defect, not full acceptance.',
 'accepted':['actual complete Blender capture and installed core integration','same-source reuse and name-only invalidation','finite ROI/unknown scope and local image feedback','actual native PNG stdio consumer readback','source/package identity and retained execution/cost/failure denominators'],
 'open_findings':[{'priority':'P2','file':'human_eye_plugin/live_spatial_mcp.py','line':870,'finding':'Active early return ignores response_detail=brief and defaults to repeated object facts/internal diagnostic metadata.','ordinary_text_bytes':24549,'all_five_active_text_bytes':101824}],
 'independent_new_product_model_Blender_raster_benchmark_calls':0,
 'author_actual_counts':{'active_requests':5,'capture_calls':5,'product_prepare_calls':4,'extra_DIRECT_prepare_calls':4,'new_rasters':6,'consumer_image_blocks':8,'stdio_requests':12,'tools_calls':7,'expected_bad_tools_call':1,'controller_runs':2,'failed_controller_runs':1},
 'retained_limits':['whole-object exact planar rectangle ROI domain','22 of 28 fixture objects are occluders without supported ROI','local protocol consumption does not prove model image understanding','four normal held acceptance actors do not erase separate forced audit-helper cleanup','RSS/complete publication and audit time unknown'],
 'next_priority_basis':{'readability_share_of_three_cold_requests':0.0088959,'delivery_gap_is_actual':True,'offline_brief_size_estimate_bytes':5658,'estimate_not_product_or_model_test':True},
 'author_manifest_sha256':sha(AUTHOR/'verification/m4_active_observation_host_bridge_001/CONTENT_MANIFEST.json'),
 'runtime_source_sha256':'b12db7282381df800fbd0d44d2f921e332a6b85c2fb3ac77aba51b5cc462b278',
 'review_doc':str(review),'review_doc_sha256':sha(review),'next_cycle':'M4-ACTIVE-OBSERVATION-BRIEF-DELIVERY-001','next_plan':str(plan),'next_plan_sha256':sha(plan)}
save(OUT/'DECISION.json',decision)
files=sorted([p for p in OUT.rglob('*') if p.is_file()]+[review,plan],key=lambda p:p.as_posix())
assert not any(p.suffix=='.pyc' for p in files)
save(OUT/'MANIFEST.json',{'schema':'root-host-bridge-001-review-manifest-v1','author_commit':COMMIT,'scope':'Root independent evidence and retained audit corrections, decision and next plan; excludes this manifest itself.','files':[{'path':p.relative_to(ROOT).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p)} for p in files]})
print(json.dumps({'checks':decision['check_total'],'files':len(files)+1,'decision_sha256':sha(OUT/'DECISION.json'),'manifest_sha256':sha(OUT/'MANIFEST.json'),'next_plan_sha256':sha(plan)}))
