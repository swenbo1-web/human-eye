"""Seal root review artifacts only; no implementation or experiment execution."""
from pathlib import Path
import hashlib
import json
import subprocess

ROOT=Path('D:/hefe')
OUT=Path(__file__).resolve().parent
AUTHOR=Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
COMMIT='cd863183b18e35d2ca38f75c0756e1c46e1a1ccb'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_bytes())
def save(p,v):
    with Path(p).open('x',encoding='utf8',newline='\n') as f:
        f.write(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert subprocess.check_output(['git','-C',str(AUTHOR),'rev-parse','HEAD'],text=True).strip()==COMMIT
assert not subprocess.check_output(['git','-C',str(AUTHOR),'status','--porcelain','--untracked-files=all'])
counts={}
for name, path, count in [('identity','IDENTITY.json',4534),('semantics','semantics/RESULTS.json',280),('images','images/RESULTS.json',819),('cost','cost/RESULTS.json',498)]:
    v=read(OUT/path)
    assert v['passed'] and v['check_count']==count
    counts[name]={'checks':count,'result':path,'sha256':sha(OUT/path)}
review=ROOT/'docs/M4_ACTIVE_OBSERVATION_CORE_INTEGRATION_001_INDEPENDENT_REVIEW.md'
plan=ROOT/'docs/M4_ACTIVE_OBSERVATION_HOST_BRIDGE_001_PLAN.md'
decision={'schema':'root-core-integration-001-review-v1','author_commit':COMMIT,
 'status':'accepted_with_stated_domain_and_measurement_limits','author_review_separate':True,
 'checks':counts,'check_total':sum(x['checks'] for x in counts.values()),
 'counts_meaning':'Overlapping evidence properties, not independent scenarios.',
 'author_content_manifest_sha256':sha(AUTHOR/'verification/m4_active_observation_core_integration_001/CONTENT_MANIFEST.json'),
 'runtime_source_sha256':'29c3f2a1a312d2d5eda1d688619846ae4137832576f9ff3ddf078c42d1a866c3',
 'wheel_sha256':'27f649e96728f84b72638ccce49575f21d71c15cbc3824a6c3f1b6e30d6c93d8',
 'median_product_over_old':read(OUT/'cost/RESULTS.json')['median_new_over_old'],
 'total_product_over_old':read(OUT/'cost/RESULTS.json')['total_new_over_old'],
 'retained_first_pair_regression':True,
 'scope':'Installable finite rectangular ROI observation core and actual local RGB/depth/owner feedback.',
 'independent_product_model_raster_Blender_performance_calls':0,
 'dynamic_behavior_basis':'Sealed author execution plus independent static/byte/data review; no root runtime rerun claimed.',
 'unrun':['host/MCP integration','default activation','new model consumption','general curved or multi-patch surface understanding','RSS and complete final publishing wall time'],
 'known_limits':['finite coherent supplied camera pool','exact rectangle domain','one ROI per object','host binding must include ordered instances and metadata','local core validation is not model image delivery'],
 'retained_failures':['first isolated numpy.version source check','six author postrun reading/interpretation corrections','document class-name correction preserves frozen original','host Bad Request recovery without repeat experiments','root identity exact-diff auditor first mismatch','core AST auditor matching correction'],
 'next_cycle':'M4-ACTIVE-OBSERVATION-HOST-BRIDGE-001',
 'next_plan':str(plan),'next_plan_sha256':sha(plan),
 'review_doc':str(review),'review_doc_sha256':sha(review)}
save(OUT/'DECISION.json',decision)
files=sorted([p for p in OUT.rglob('*') if p.is_file()]+[review,plan],key=lambda p:p.as_posix())
assert not any(p.suffix=='.pyc' for p in files)
manifest={'schema':'root-core-integration-001-review-manifest-v1','author_commit':COMMIT,
 'scope':'Root independent evidence, first auditor error retained, decision and next plan; excludes this manifest itself.',
 'files':[{'path':p.relative_to(ROOT).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p)} for p in files]}
save(OUT/'MANIFEST.json',manifest)
print(json.dumps({'passed':True,'checks':decision['check_total'],'files':len(files)+1,'decision_sha256':sha(OUT/'DECISION.json'),'manifest_sha256':sha(OUT/'MANIFEST.json'),'next_plan_sha256':sha(plan)},ensure_ascii=False))
