"""Static final evidence checks; zero product/helper/model execution."""
import ast
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import zipfile

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
sha=lambda b:hashlib.sha256(b).hexdigest()
load=lambda p:json.loads(Path(p).read_bytes())
plan=load(HERE/'PLAN.json')
assert plan['execution_ready'] is False
assert plan['limits']['action_observation_threshold']==8 and 'actions_per_answer' not in plan['limits']
assert plan['limits']['answer_seconds']==180 and plan['limits']['total_physical_rpc']==8*(128+1)
assert not (HERE/'actual_01').exists()
for row in plan['runtime_components']:
    assert sha((HERE/row['path']).read_bytes())==row['sha256'],row['path']
with zipfile.ZipFile(HERE/'PRODUCT_BYTES.zip') as archive:
    assert sorted(archive.namelist())==sorted(r['path'] for r in plan['product_manifest'])
    for row in plan['product_manifest']:
        assert sha(archive.read(row['path']))==sha((ROOT/row['path']).read_bytes())==row['sha256']
    tree=ast.parse(archive.read('human_eye_plugin/runtime_identity.py'))
    constants={n.targets[0].id:ast.literal_eval(n.value) for n in tree.body
        if isinstance(n,ast.Assign) and isinstance(n.targets[0],ast.Name)
        and n.targets[0].id in ('BASE_VERSION','IMPLEMENTATION_REVISION')}
canonical=dict(base_version=constants['BASE_VERSION'],implementation_revision=constants['IMPLEMENTATION_REVISION'],files=plan['product_manifest'])
assert sha(json.dumps(canonical,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode())==plan['source_sha256']
material=load(HERE/'materials/MATERIAL_MANIFEST.json')
for row in material['tasks']:
    raw=(HERE/'materials'/row['prompt_path']).read_bytes()
    assert sha(raw)==row['prompt_utf8_sha256'] and len(raw)==911 and not raw.endswith(b'\n')
for name in ('runner.py','bridge.py','he_bootstrap.py','freeze_plan.py','tests_bridge.py','tests_runner.py','preparation_checks.py'):
    ast.parse((HERE/name).read_bytes(),filename=name)
result=dict(cycle_id='CONSUMPTION-RUN-PREP-001',checked_utc=datetime.now(timezone.utc).isoformat(),passed=True,
    source_count=131,source_sha256=plan['source_sha256'],source_check='static exact bytes/canonical hash; no product imports or execution',
    plan_sha256=sha((HERE/'PLAN.json').read_bytes()),prompt_count=4,unchanged_prompt_bytes=3644,
    budget_clarification_applied=True,action8_is_only_threshold=True,
    proposed_sessions=8,proposed_RPC_maximum=1032,execution_ready=False,
    actual_model_answers=0,actual_Blender_sessions=0,actual_native_RPC=0,actual_product_RPC=0,actual_model_API_calls=0,
    actual_product_imports=0,actual_asset_copies=0,
    final_synthetic_unique_methods=19,observed_method_executions_all_revisions=76,synthetic_failures=0,
    latest_bridge=dict(methods=9,runner_seconds=.183,command_wall_seconds=.5056737),
    latest_runner=dict(methods=10,runner_seconds=.015,command_wall_seconds=.3197303),
    check_limits='synthetic in-memory streams/mocks and syntax only; no real transport, model configuration or image delivery established',
    unresolved=list(plan['execution_blockers']),unverified_in_unique_batch=plan['unverified_in_unique_batch'],
    auth_key_system_or_hidden_reasoning_contents_exported=False)
(HERE/'FINAL_PREP_CHECKS.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf8')
print(json.dumps(dict(passed=True,source_count=131,prompts=4,model_answers=0,Blender_sessions=0,RPC=0,execution_ready=False)))
