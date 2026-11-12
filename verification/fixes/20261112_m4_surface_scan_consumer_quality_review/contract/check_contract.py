"""Independent static and byte-level contract review; no formal answers/cost opened."""
from pathlib import Path
import ast
import hashlib
import json
import subprocess

ROOT = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
BATCH = ROOT/'verification/m4_surface_scan_consumption_001'
OUT = Path(__file__).resolve().parent
PREP = 'bedcc827ec548e3afab816c0986db0c99eb42bb8'
DELIVERY = 'e5c8afafbcd7cf55307be9e640a3e2ad61e25fd3'
CHECKS = []
SOURCES = {}

def check(name, condition):
    CHECKS.append({'name': name, 'passed': bool(condition)})
    assert condition, name

def data(path):
    path = Path(path)
    raw = path.read_bytes()
    SOURCES[str(path)] = {'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}
    return raw

def read(path):
    return json.loads(data(path))

def git_bytes(commit, path):
    return subprocess.check_output(['git', 'show', commit+':'+Path(path).relative_to(ROOT).as_posix()], cwd=ROOT)

def node(path, name):
    return next(n for n in ast.parse(data(path).decode('utf-8-sig')).body if isinstance(n, ast.FunctionDef) and n.name==name)

def main():
    root_plan = Path('D:/hefe/docs/M4_SURFACE_SCAN_CONSUMPTION_001_PLAN.md')
    plan_bytes = data(root_plan)
    check('root_plan_original_sha', hashlib.sha256(plan_bytes).hexdigest() == '8c2baa7394f12d003291dbc643aa1c5ed6aba38e6215240d4e1f0148943f1989')
    check('copied_root_plan_exact', data(BATCH/'ROOT_PLAN.md') == plan_bytes)
    expected_prompt = next(line[2:] for line in plan_bytes.decode().splitlines() if line.startswith('> 检查'))+'\n'
    check('common_prompt_exact_root', data(BATCH/'input/PROMPT.txt') == expected_prompt.encode())
    selected = ['ROOT_PLAN.md','PLAN.json','GO.json','FREEZE.json','input/PROMPT.txt',
        'scoring/SCORING_CONTRACT.json','scoring/score_answer.py','scoring/test_score_answer.py',
        'scoring/history_before_presentation_contract/SCORING_CONTRACT.json',
        'preflight/CONTRACT_CORRECTION.json','preflight/PLAN_PREPARED_02.json','preflight/PLAN_01.json',
        'runtime/actor.py','runtime/consumer_transport.py','runtime/driver.py','runtime/run_formal.py',
        'runtime/prepare_plan.py','runtime/freeze_plan.py','runtime/pack_quality.py',
        'runtime/test_bridge_contract.py','runtime/test_runtime_contract.py',
        'schemas/COMMON_NATIVE.json','schemas/N_CONSUMER_TOOLS.json','schemas/P_CONSUMER_TOOLS.json','schemas/P_PUBLIC_TOOLS.json']
    for rel in selected:
        raw = data(BATCH/rel)
        check('prepared_git_bytes:'+rel, raw == git_bytes(PREP,BATCH/rel))
        check('delivered_git_bytes:'+rel, raw == git_bytes(DELIVERY,BATCH/rel))
    check('preparation_ancestor_delivery',subprocess.run(['git','merge-base','--is-ancestor',PREP,DELIVERY],cwd=ROOT).returncode == 0)
    prep_names = subprocess.check_output(['git','ls-tree','-r','--name-only',PREP,'--','verification/m4_surface_scan_consumption_001'],cwd=ROOT,text=True).splitlines()
    prefix='verification/m4_surface_scan_consumption_001/'
    check('no_actual_cells_in_preparation_commit',not any(n.startswith(prefix+'cells/') for n in prep_names))
    check('no_started_or_run_result_in_preparation_commit',not any(n in {prefix+'STARTED.json',prefix+'RUN_RESULT.json',prefix+'FORMAL_PROCESS.json'} for n in prep_names))
    # PLAN contains only the anonymous-map hash, not its mapping; no private file is read.
    plan = read(BATCH/'PLAN.json')
    check('final_plan_sha',SOURCES[str(BATCH/'PLAN.json')]['sha256']=='7e3567f1ea8b528c13d36078abe2a659ba7ff74d02342cca86c1bff3dfedcb3f')
    check('go_binds_final_plan',read(BATCH/'GO.json')['plan_sha256']==SOURCES[str(BATCH/'PLAN.json')]['sha256'])
    check('freeze_binds_final_plan',read(BATCH/'FREEZE.json')['plan_sha256']==SOURCES[str(BATCH/'PLAN.json')]['sha256'])
    check('root_plan_binding',plan['root_plan_sha256']==hashlib.sha256(plan_bytes).hexdigest())
    budgets={'logical_denominator':6,'per_arm':3,'max_session_seconds':450,'total_cell_seconds':570,
        'actor_startup_seconds':40,'tool_attempts':32,'physical_RPC_limit':128,'tool_timeout_s':30,
        'tool_response_bytes':1048576,'code_bytes':262144,'image_count':0,'new_images':0}
    for k,v in budgets.items():check('plan_budget:'+k,plan[k]==v)
    check('fixed_order',[r['cell'] for r in plan['sequence']]==['N1','P1','P2','N2','N3','P3'])
    check('requested_model',plan['model']=='gpt-6.1-sol' and plan['requested_effort']=='medium')
    check('resolved_model_remains_unknown',plan['resolved_model'] is None and plan['resolved_effort'] is None)
    correction = read(BATCH/'preflight/CONTRACT_CORRECTION.json')
    check('correction_no_started_or_freeze',correction['consumers_started']==0 and correction['Blender_sessions_started']==0 and correction['FREEZE_exists'] is False and correction['GO_exists'] is False)
    check('prior_plan_preserved',hashlib.sha256(data(BATCH/'preflight/PLAN_01.json')).hexdigest()==correction['prior_plan_sha256'])
    old_contract = read(BATCH/'scoring/history_before_presentation_contract/SCORING_CONTRACT.json')
    contract = read(BATCH/'scoring/SCORING_CONTRACT.json')
    for k in ['input_materials','primary_fixed_denominators','completeness_policy','evidence_policy','fixed_sample_policy']:
        check('unchanged_contract:'+k,old_contract[k]==contract[k])
    check('unchanged_tolerance',old_contract['distance_policy']['absolute_error_mm']==contract['distance_policy']['absolute_error_mm']=='0.000500001')
    check('public_scoring_contract_exact',data(BATCH/'runtime/handoff_01/public/scoring/SCORING_CONTRACT.json')==data(BATCH/'scoring/SCORING_CONTRACT.json'))
    native_source=ROOT/'verification/native_plugin_complex_003/actor.py'
    native_ast=ast.parse(data(native_source).decode())
    native=ast.literal_eval(next(n.value for n in native_ast.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='NATIVE' for t in n.targets)))
    check('native_schema_original_literal',native==read(BATCH/'schemas/COMMON_NATIVE.json'))
    tools_path=ROOT/'verification/m4_surface_scan_001_opt1/engineering/run_01/pair_01/B/TOOLS.json'
    tools_bytes=data(tools_path)
    check('ordinary_schema_prior_delivery_git',tools_bytes==git_bytes('860b87138d40de9cc08b01c947dd864d58da9295',tools_path))
    observe=[t for t in json.loads(tools_bytes)['result']['tools'] if t['name']=='human_eye_scene_observe']
    check('ordinary_observe_exact_previous',observe==read(BATCH/'schemas/P_PUBLIC_TOOLS.json') and len(observe)==1)
    check('N_only_original_native',read(BATCH/'schemas/N_CONSUMER_TOOLS.json')==[native])
    check('P_same_native_plus_full_observe',read(BATCH/'schemas/P_CONSUMER_TOOLS.json')==[native,observe[0]])
    old_transport=ROOT/'verification/m4_grooved_rail_consumption_001/runtime/consumer_transport.py'
    for name in ['settings','safe_environment','wait_bridge_closed','kill_owned_tree']:
        check('unchanged_transport_function:'+name,ast.dump(node(old_transport,name))==ast.dump(node(BATCH/'runtime/consumer_transport.py',name)))
    # Compare the adapter's effective include_image expression to the product request trace.
    actor_tree=ast.parse(data(BATCH/'runtime/actor.py').decode())
    product=ROOT/'human_eye_plugin/live_spatial_mcp.py'
    product_raw=data(product)
    check('product_fixed_git',product_raw==git_bytes('c1cb2da32034e056a270384e691a2cde8dddbc0d',product))
    product_tree=ast.parse(product_raw.decode())
    def default_expr(tree):
        return [ast.dump(n) for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute)
            and isinstance(n.func.value,ast.Name) and n.func.value.id=='args' and n.func.attr=='get' and len(n.args)==2
            and isinstance(n.args[0],ast.Constant) and n.args[0].value=='include_image' and isinstance(n.args[1],ast.UnaryOp)]
    check('image_guard_same_product_effective_default',default_expr(actor_tree)==default_expr(product_tree))
    text=product_raw.decode()
    check('product_scan_setdefault_false',"args.setdefault('include_image', False)" in text)
    actor=data(BATCH/'runtime/actor.py').decode()
    check('adapter_forwards_original_request',"answer=self.peer.call(req," in actor)
    check('native_forwards_original_code',"self.native.run(args['code'],timeout_s=30)" in actor)
    check('N_plugin_not_started',"if config['group']!='N':" in actor)
    packer=data(BATCH/'runtime/pack_quality.py').decode()
    check('packer_not_importing_score_answer',not any(isinstance(n,(ast.Import,ast.ImportFrom)) and 'score_answer' in ast.dump(n) for n in ast.walk(ast.parse(packer))))
    summary={'checks':len(CHECKS),'all_passed':all(c['passed'] for c in CHECKS),'preparation_commit':PREP,'delivery_commit':DELIVERY,
        'answers_read':0,'private_mapping_read':False,'actual_cost_or_usage_read':False,'new_Blender_or_consumers':0,
        'chronology_limit':'Prepared commit contains final plan/GO/contracts and no actual run records; actual launch timestamp ordering is left to sealed provenance review.',
        'scope':'Static contract, schema and Git bytes; formal answer adjudication remains independent.'}
    (OUT/'CHECKS.json').write_text(json.dumps(CHECKS,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (OUT/'SOURCES.json').write_text(json.dumps(SOURCES,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (OUT/'RESULTS.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False))

if __name__=='__main__':
    try:main()
    except Exception as error:
        (OUT/'FAILED.json').write_text(json.dumps({'error':repr(error),'checks':CHECKS},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        raise
