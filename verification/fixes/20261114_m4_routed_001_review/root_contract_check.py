"""Offline, stdlib-only checks of the preregistered task and public tool contract."""
import ast
import hashlib
import json
from pathlib import Path

AUTHOR = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
BASE = AUTHOR / 'verification/m4_routed_task_benefit_001'
OUT = Path(__file__).resolve().parent
ROOT_PLAN = Path('D:/hefe/docs/M4_ROUTED_TASK_BENEFIT_001_PLAN.md')
checks = []
inputs = []


def read(path):
    raw = path.read_bytes()
    inputs.append({'path': str(path), 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()})
    return raw


def check(name, value):
    checks.append({'name': name, 'pass': bool(value)})


plan_raw = read(ROOT_PLAN)
check('root_preregistration_hash', hashlib.sha256(plan_raw).hexdigest() ==
      '44f73d0ed19d8c41ffa692bced8505d716353f430c1bb06916f96253465eba67')
plan = json.loads(read(BASE / 'PLAN.json'))
suffix = read(BASE / 'inputs/PROMPT_SUFFIX.txt')
check('original_common_task_hash', hashlib.sha256(suffix).hexdigest() ==
      '3f848a42070580ad479e3de6507b9ffe09c59b9651c784c17608f0d752c1205a')
shared = (b'Reuse current-session evidence and computed facts; obtain additional evidence only when it is '
          b'missing or inconsistent. Complete the task below within this turn.')
prefixes = {
    'N': b'For this comparison, begin with whichever available native entry is most efficient. ' + shared,
    'P': b'For this comparison, begin with active_observation(include_images=true). ' + shared,
}
for group, expected in prefixes.items():
    actual = read(BASE / ('inputs/PREFIX_' + group + '.txt'))
    prompt = read(BASE / ('inputs/PROMPT_' + group + '.txt'))
    check(group + '_registered_prefix_exact', actual == expected)
    check(group + '_common_suffix_exact', prompt == expected + b'\n\n' + suffix)
    check(group + '_declared_prompt_hash', hashlib.sha256(prompt).hexdigest() == plan['expected_prompt_sha256'][group])

bridge_raw = read(BASE / 'bridge.py')
bridge_tree = ast.parse(bridge_raw.decode('utf-8-sig'))
names = ('GENERIC', 'SCENE_DATA', 'RENDER_VIEWS', 'READ_IMAGES', 'ACTIVE')
definitions = {}
for node in bridge_tree.body:
    if isinstance(node, ast.Assign):
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id in names:
                definitions[target.id] = {ast.literal_eval(key): ast.literal_eval(value)
                    for key, value in zip(node.value.keys, node.value.values)
                    if isinstance(key, ast.Constant) and key.value in ('name', 'description')}
check('five_public_tool_definitions', set(definitions) == set(names))
check('generic_documents_persistent_raw_access', all(value in definitions['GENERIC']['description']
      for value in ('persistent Python', 'np and Fraction', 'Raw inputs are returned only when requested or printed',
                    'Existing buffers and image refs can be reused directly')))
check('scene_data_already_available_without_dump', 'already in execute_python' in definitions['SCENE_DATA']['description'])
check('old_fresh_contract_preserved', 'Every requested view is a fresh actual construction, including repeats.' in
      definitions['GENERIC']['description'])
check('product_shared_json_documented', 'json.loads(last_observation_json)' in definitions['ACTIVE']['description'])
public_tools = next(node for node in bridge_tree.body if isinstance(node, ast.FunctionDef) and node.name == 'public_tools')
public_tools_source = ast.get_source_segment(bridge_raw.decode('utf-8-sig'), public_tools)
check('common_tools_plus_only_P_active',
      '[GENERIC, SCENE_DATA, RENDER_VIEWS, READ_IMAGES] + ([ACTIVE] if group == "P" else [])' in public_tools_source)

launcher_raw = read(BASE / 'launcher.py')
launcher_tree = ast.parse(launcher_raw.decode('utf-8-sig'))
run_slot = next(node for node in launcher_tree.body if isinstance(node, ast.FunctionDef) and node.name == 'run_slot')
source = ast.get_source_segment(launcher_raw.decode('utf-8-sig'), run_slot)
check('one_shared_slot_wrapper', source.count('record = route(slot, group, plan, runtime)') == 1)
check('slot_start_precedes_checks', source.index('started = time.perf_counter_ns()') < source.index('verify_frozen(sources)'))
check('slot_end_follows_result_publication', source.index("save(metadata / 'SLOT_RESULT.json'") <
      source.index('closed = time.perf_counter_ns()'))
check('timing_publication_outside_end', source.index('closed = time.perf_counter_ns()') <
      source.index("save(metadata / 'SLOT_TIMING.json'"))

result = {'method': 'Root independent static AST/text and byte checks; product modules not imported',
          'new_product_model_blender_raster_calls': 0,
          'passed': sum(c['pass'] for c in checks), 'failed': sum(not c['pass'] for c in checks),
          'checks': checks, 'inputs': inputs,
          'interpretation': 'Same task and common primitive contract, with the registered route difference only. '
          'Does not prove best possible native implementation, actual provider backend equality, or new frame-reuse behavior.'}
(OUT / 'ROOT_CONTRACT_RESULT.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'passed': result['passed'], 'failed': result['failed']}))
if result['failed']:
    print(json.dumps([c for c in checks if not c['pass']]))
    raise SystemExit(1)
