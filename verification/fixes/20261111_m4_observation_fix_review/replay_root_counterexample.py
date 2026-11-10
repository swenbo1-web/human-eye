from pathlib import Path
import hashlib, importlib.util, json

OUT=Path('D:/hefe/verification/fixes/20261111_m4_observation_fix_review')
OLD=Path('D:/hefe/verification/fixes/20261111_m4_observation_prep_review/ROOT_PROJECTION_REPRODUCTION.json')
SCRIPT=Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_observation_baseline_001/quality_handoff/pack_quality.py')
assert hashlib.sha256(SCRIPT.read_bytes()).hexdigest()=='afa802bdb085ad9e174f04c4ba91ff05bdacdbc7b0bb892162a7b7e14d580cbc'
spec=importlib.util.spec_from_file_location('_root_fixed_projection',SCRIPT)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
original=json.loads(OLD.read_bytes())['input']
raw=json.dumps(original,ensure_ascii=False).encode();removals=[]
projection=module.audit_projection(module.without_rpc_envelope(original,raw,removals),raw,removals)
assert projection['result']==original['result']
assert projection['result']['content'][0]['text']==original['result']['content'][0]['text']
assert {r['pointer'] for r in removals}=={'$/id','$/jsonrpc'}
record={'passed':True,'scope':'root independently replays identical prior counterexample against pinned fix; pure functions only',
 'original_evidence_sha256':hashlib.sha256(OLD.read_bytes()).hexdigest(),
 'new_script_sha256':hashlib.sha256(SCRIPT.read_bytes()).hexdigest(),
 'semantic_payload_unchanged':True,'json_text_unchanged':True,
 'projection':projection,'removals':removals,'models':0,'Blender':0,'product_processes':0}
(OUT/'ROOT_COUNTEREXAMPLE_FIXED.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(json.dumps({'passed':True,'semantic_payload_unchanged':True,'only_transport_fields_removed':True}))
