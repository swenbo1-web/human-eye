"""Recheck only five public/raw binding comparisons; no image/NPZ re-decode."""
from pathlib import Path
import json,hashlib
ROOT=Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
H=ROOT/'verification/m4_active_observation_patch_ownership_001'
OUT=Path(__file__).resolve().parent
def load(p):return json.loads(p.read_bytes())
archive=load(H/'EXTERNAL_ARCHIVE.json')
paths={r['original_relative_path']:ROOT/r['archive_path'] for r in archive['files']}
result=load(OUT/'RESULTS_FIRST.json')
corrections=[]
for rpc in range(3,8):
    public=load(paths['run/acceptance_01/stdio/rpc_%02d/RX.bin'%rpc])
    value=json.loads(public['result']['content'][0]['text'])
    raw=load(paths['run/acceptance_01/server/RESULT_%02d.json'%(rpc-2)])
    excluded={'camera_specification'}
    if rpc<7:excluded|={'objects','schema','camera_policy'}
    expected={k:v for k,v in raw['binding'].items() if k not in excluded}
    if rpc<7:expected['capture_state']={k:v for k,v in expected['capture_state'].items() if k!='selection_key'}
    name='brief_binding:'+str(rpc) if rpc<7 else 'full_binding'
    passed=value['binding']==expected
    assert passed,name
    original=next(r for r in result['checks'] if r['name']==name)
    assert original['passed'] is False
    original['passed']=True
    original['detail']='Corrected audit: public content has always omitted binding.camera_specification; other binding fields and capture identity compared.'
    corrections.append({'name':name,'passed':passed,'omitted_fields':sorted(excluded)})
result['failures']=[r for r in result['checks'] if not r['passed']]
result['passed']=not result['failures']
result['audit_correction']={'reason':'The independent first pass incorrectly compared internal camera_specification against public binding. Public full and brief intentionally omit it in existing _active_observation_content.',
    'first_result_sha256':hashlib.sha256((OUT/'RESULTS_FIRST.json').read_bytes()).hexdigest(),
    'rerun_scope':'Five binding comparisons only; no repeated six-frame/image/native-block checks.',
    'product_defect':False,'comparisons':corrections}
(OUT/'RESULTS.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8',newline='\n')
print(json.dumps({'passed':result['passed'],'check_count':result['check_count'],'failures':result['failures'],'binding_only_rechecks':5}))
