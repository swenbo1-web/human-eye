from pathlib import Path
import hashlib,json
R=Path('D:/hefe'); O=Path(__file__).parent
reports=['IDENTITY.json','world/RESULTS.json','pixel/RESULTS.json','cost/RESULTS.json','cost/TRACE.json']
summary={}
for name in reports:
    p=O/name; raw=p.read_bytes(); obj=json.loads(raw); assert obj['passed'],name
    if name=='cost/RESULTS.json': assert not obj['failed']
    elif 'failures' in obj: assert not obj['failures']
    summary[name]={'sha256':hashlib.sha256(raw).hexdigest(),'checks':obj['checks'],'passed':True}
plan=R/'docs/M4_REGION_LOCALIZATION_CONSUMPTION_001_PLAN.md'
review=R/'docs/M4_ACTIVE_OBSERVATION_REGION_ANCHORS_001_INDEPENDENT_REVIEW.md'
decision={'cycle':'M4-ACTIVE-OBSERVATION-REGION-ANCHORS-001','candidate':'7d42bb939c7881a98fe322c10c216398f6c7aecc','status':'engineering_accepted','model_benefit_measured':False,'root_new_product_model_Blender_raster_benchmark_calls':0,'independent_checks':summary,'author_unit_methods':86,'root_product_unit_tests_run':0,'next_cycle':'M4-REGION-LOCALIZATION-CONSUMPTION-001','next_plan_sha256':hashlib.sha256(plan.read_bytes()).hexdigest(),'review_sha256':hashlib.sha256(review.read_bytes()).hexdigest(),'limits':['Benchmark optimized outputs not archived per call; reference and equality checks retained.','Console execution and independently held server process handle receipt unmeasured.','Brief unsupported remainder lacks world coordinates; exact point-to-index claims need native evidence.'],'root_preparation_errors':['Read-only nonexistent source filenames and Windows glob lookup errors; corrected paths without product execution.','Single-line JSON preview was truncated; structured fields and complete offline scripts used for verification.','Pixel first audit expected historical runtime instance equality; original failure retained and only binding comparison corrected.']}
(O/'DECISION.json').write_text(json.dumps(decision,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
files=sorted(p for p in O.rglob('*') if p.is_file() and p.name!='MANIFEST.json' and '__pycache__' not in p.parts)
files += [plan,review,R/'verification/fixes/20261114_f_history_duplicate/REVIEW.md']
rows=[{'path':p.relative_to(R).as_posix(),'bytes':len(p.read_bytes()),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(files)]
result={'scope':'Independent root review and next plan; author source not modified','files':rows,'files_excluding_manifest':len(rows)}
(O/'MANIFEST.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'files':len(rows),'plan_sha256':decision['next_plan_sha256'],'decision_sha256':hashlib.sha256((O/'DECISION.json').read_bytes()).hexdigest(),'manifest_sha256':hashlib.sha256((O/'MANIFEST.json').read_bytes()).hexdigest()}))
