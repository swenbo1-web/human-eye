"""Build one exact candidate and compare the installed public tool directories."""

import argparse
import ast
from functools import partial
import json
from pathlib import Path
import runpy
import subprocess
import sys


HERE = Path(__file__).resolve().parent
NS = HERE.parent
ROOT = NS.parents[1]
RETAINED = NS.parent / 'm1_target_observation_first_image_path_windows_001/install/build_install.py'
RUN = Path('D:/he_m1_pair_distance_entry_001')
PYTHON = Path('D:/he_anchor_001/venv/Scripts/python.exe')
BASE = '95fd44bb8c4b6b992d8849f38ffbe5d778b0ac5a'
BASE_SOURCE = 'eaccba2ec88abc035c62841a765f99ecae5f50e34dd8e7867b09dc17cb6d9dc9'
BASE_WHEEL = 'e0f603f2279df4d9e08c844ad3b191449b69799c54737f2b0c178f6ef22f4fbe'
WINDOWS = 'm1_target_observation_first_image_path_windows_001'
BASE_TOOLS = RETAINED.with_name('TOOLS_SCHEMA.json')
VERSION = '9.7.2+m1.pair.distance.entry.001'
MODULE = 'human_eye_plugin/live_spatial_mcp.py'
TOOL = 'human_eye_scene_observe'


def description(tree):
    schema = next(item.value for item in tree.body if isinstance(item, ast.Assign)
                  and any(isinstance(target, ast.Name) and target.id == 'LIVE_MCP_TOOLS_SCHEMA'
                          for target in item.targets))
    for item in schema.elts:
        fields = {key.value: value for key, value in zip(item.keys, item.values, strict=True)}
        if fields['name'].value == TOOL:
            return fields['description']
    raise ValueError('observable_tool_missing_from_exact_source')


def exact_description(repo, candidate):
    def module(commit):
        return ast.parse(subprocess.check_output(['git', 'show', f'{commit}:{MODULE}'], cwd=repo))

    previous, current = module(BASE), module(candidate)
    before, after = description(previous), description(current)
    changed = after.value
    if before.value == changed or len(before.value.encode()) != 3255 or len(changed.encode()) > 3255:
        raise ValueError('whole_pair_description_must_fit_old_UTF8_budget')
    after.value = before.value
    if ast.dump(previous) != ast.dump(current):
        raise ValueError('candidate_AST_diff_outside_observation_description')
    sample_start = changed.index('{"include_image":false')
    example = json.JSONDecoder().raw_decode(changed[sample_start:])[0]
    if (sample_start >= changed.index('target/candidates')
            or example != {'include_image': False, 'query': {'mode': 'task', 'objects': [
                {'name': 'A'}, {'name': 'B'}], 'requested_facts': ['surface_proximity']}}):
        raise ValueError('first_example_is_not_the_existing_ordered_whole_pair')
    return changed


def check_catalogue(repo, previous, actual, candidate):
    if len(previous) != 5 or candidate == BASE and previous != actual:
        raise ValueError('fixed_baseline_tools_list_differed')
    if candidate == BASE:
        return
    changed = exact_description(repo, candidate)
    expected = [{**tool, 'description': changed} if tool['name'] == TOOL else tool for tool in previous]
    if sum(tool['name'] == TOOL for tool in previous) != 1 or expected != actual:
        raise ValueError('installed_tools_list_diff_outside_expected_description')


def probe(command_python, root, run, binding, label):
    command = [str(command_python), '-I', '-B', str(Path(__file__).resolve()), '--inspect', str(binding)]
    result = subprocess.run(command, cwd=root, capture_output=True, timeout=60)
    for name, raw in (('STDOUT', result.stdout), ('STDERR', result.stderr)):
        with (run / f'{label}_{name}.bin').open('xb') as sink:
            sink.write(raw)
    result.check_returncode()
    return command, json.loads(result.stdout)


def configure():
    old = runpy.run_path(str(RETAINED))
    old['verify_lineage'].__globals__.update(BASE=BASE)
    dependencies = {name: sha for name, sha in old['DEPENDENCIES'].items()
                    if not name.endswith('/PRODUCT_RUN_BINDING.json')}
    dependencies[WINDOWS + '/install/PRODUCT_RUN_BINDING.json'] = (
        'e6fd29d88ab8b88bd7830aa4d2ea2b49ba853bb981d1acae15b25e20b129578b')
    # The retained binder unpacks source, binding, wheel builder and bootstrap in order.
    bindings_first = {list(dependencies)[0]: next(iter(dependencies.values())),
                      WINDOWS + '/install/PRODUCT_RUN_BINDING.json':
                          dependencies[WINDOWS + '/install/PRODUCT_RUN_BINDING.json']}
    bindings_first.update(dependencies)
    globals_ = old['load_helper'].__globals__
    globals_.update(RUN=RUN, EXTERNAL=RUN / 'candidate_install', EVIDENCE='0cc8afa5082f27a3aff607bebf7793d0d4072bc9',
                    BASE=BASE, BASE_SOURCE=BASE_SOURCE, BASE_WHEEL=BASE_WHEEL, BASE_TOOLS=BASE_TOOLS,
                    BASE_TOOLS_SHA=old['digest'](BASE_TOOLS.read_bytes()), VERSION=VERSION,
                    DEPENDENCIES=bindings_first)
    helper, wheel_builder = old['load_helper'](ROOT, HERE)
    helper.probe = partial(probe, PYTHON, ROOT, helper.EXTERNAL)
    replacement = partial(check_catalogue, ROOT)
    source = Path(helper.__file__).read_text(encoding='utf8')
    functions = {node.name: ast.get_source_segment(source, node) for node in ast.parse(source).body
                 if isinstance(node, ast.FunctionDef) and node.name in ('inspect', 'build')}
    edits = {
        'inspect': [("if tools != json.loads(read(BASE_TOOLS)):\n        raise ValueError('actual installed tools/list differs from the historical arm')",
                     "check_catalogue(json.loads(read(BASE_TOOLS)), tools, binding['preparation_git'])")],
        'build': [("if baseline_actual['tools'] != tools:\n        raise ValueError('candidate and baseline installed tools differ')",
                   "check_catalogue(baseline_actual['tools'], tools, candidate)"),
                  ("'tool_schema_matches_historical_actual_directory': True,",
                   "'tool_schema_matches_historical_actual_directory': False,\n"
                   "               'tool_schema_delta': ['human_eye_scene_observe.description'],")],
    }
    helper.check_catalogue = replacement
    for name, values in edits.items():
        code = functions[name]
        for before, after in values:
            if code.count(before) != 1:
                raise ValueError('retained_build_probe_changed/' + name)
            code = code.replace(before, after)
        exec(compile(code, str(helper.__file__), 'exec'), vars(helper))
    return old, helper, wheel_builder


def main():
    if not sys.flags.isolated or not sys.dont_write_bytecode or Path(sys.executable).resolve() != PYTHON.resolve():
        raise ValueError('fixed_interpreter_with_I_B_required')
    p = argparse.ArgumentParser(description=__doc__)
    action = p.add_mutually_exclusive_group(required=True)
    action.add_argument('--candidate')
    action.add_argument('--inspect', type=Path)
    args = p.parse_args()
    retained, helper, _ = configure()
    if args.inspect is not None:
        helper.inspect(args.inspect)
        return
    retained['verify_lineage'](ROOT, args.candidate)
    exact_description(ROOT, args.candidate)
    helper.build(args.candidate)


if __name__ == '__main__':
    main()
