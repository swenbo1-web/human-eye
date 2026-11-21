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
RETAINED = NS.parent / 'm1_sampled_image_path_producer_reuse_001/install/build_install.py'
RUN = Path('D:/he_m1_source_region_default_measurement_entry_001')
PYTHON = Path('D:/he_anchor_001/venv/Scripts/python.exe')
BASE = '8e3129c09e147bd996da2b6f45126be36ba5fcde'
BASE_SOURCE = '9d1644804c13e30b05a81f5186c5b51e51b06dd6bef4d23ee8a08f57c77c0529'
BASE_WHEEL = '1bcfc3e8b26bf8026e5b894bf37d87c3508ae8176ccf73a86513022e16a2ae38'
PREVIOUS = 'm1_sampled_image_path_producer_reuse_001'
BASE_TOOLS = RETAINED.with_name('TOOLS_SCHEMA.json')
VERSION = '9.7.2+m1.source.region.default.measurement.entry.001'
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
    old_sentence = 'Brief and full return the source scope, display participation, distance, witness and native image references.'
    new_sentence = ('Default brief includes distance, nearest points with source faces, and region_ref. '
                    'Use response_detail=full for face mappings and diagnostics.')
    if before.value.count(old_sentence) != 1 or changed != before.value.replace(old_sentence, new_sentence):
        raise ValueError('only_the_registered_source_region_sentence_may_change')
    after.value = before.value
    if ast.dump(previous) != ast.dump(current):
        raise ValueError('candidate_AST_diff_outside_observation_description')
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
    old['verify_lineage'].__globals__.update(BASE=BASE, CHANGED=(MODULE,))
    dependencies = {name: sha for name, sha in old['DEPENDENCIES'].items()
                    if not name.endswith('/PRODUCT_RUN_BINDING.json')}
    dependencies[PREVIOUS + '/install/PRODUCT_RUN_BINDING.json'] = (
        'cd5c812711109af05abc209c0d7229cd31782f6ab43076c970a64ee3d94fb50f')
    # The retained binder unpacks source, binding, wheel builder and bootstrap in order.
    bindings_first = {list(dependencies)[0]: next(iter(dependencies.values())),
                      PREVIOUS + '/install/PRODUCT_RUN_BINDING.json':
                          dependencies[PREVIOUS + '/install/PRODUCT_RUN_BINDING.json']}
    bindings_first.update(dependencies)
    globals_ = old['load_helper'].__globals__
    globals_.update(RUN=RUN, EXTERNAL=RUN / 'candidate_install', EVIDENCE='e352135dffdd88dd1fccbfa475d18e352e9c3e93',
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
