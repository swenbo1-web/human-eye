"""Build and verify the single task-entry wheel without replacing any default install."""

import argparse
import ast
from functools import partial
import json
from pathlib import Path
from runpy import run_path
import subprocess
import sys


HERE = Path(__file__).resolve().parent
V = HERE.parents[1]
ROOT = V.parent
RETAINED = V/'m4_source_region_blocker_frame_list_001/install'
RUN = Path('D:/he_m1_source_region_task_entry_001_install')
PYTHON = Path('D:/he_anchor_001/venv/Scripts/python.exe')
BASE = '8cf3fabc1a735b7ff5849b3c63c49cf932df4b6b'
BASE_SOURCE = '65bd1ec8009f8024e85ef1cd30c1229957cceb1c1766c8e5b62f2ef2489ce48c'
BASE_WHEEL = '97053290d96270fefeff95d681efaf5222a64ef136a084267be5d7c707d6813d'
SOURCE = ('human_eye_plugin/live_spatial_mcp.py',)
TOOL = 'human_eye_source_region_measure'


def check_catalogue(original, actual, commit):
    if commit==BASE:
        if original!=actual:
            raise ValueError('baseline_tools_changed')
        return
    if (len(actual)!=len(original)+1 or actual[:-1]!=original or actual[-1]['name']!=TOOL
            or not actual[-1]['annotations']['readOnlyHint']
            or set(actual[-1]['inputSchema']['properties'])!={
                'region','region_ref','reference','include_image','session_id','task_context'}):
        raise ValueError('normal_catalogue_delta_must_be_the_single_readonly_tool')


def probe(binding,label):
    command = [str(PYTHON),'-I','-B',str(Path(__file__).resolve()),'--inspect',str(binding)]
    result = subprocess.run(command,cwd=ROOT,capture_output=True,timeout=60)
    for stream,raw in (('STDOUT',result.stdout),('STDERR',result.stderr)):
        with (RUN/'candidate_install'/f'{label}_{stream}.bin').open('xb') as sink:
            sink.write(raw)
    result.check_returncode()
    return command,json.loads(result.stdout)


def configure():
    old = run_path(str(RETAINED/'build_install.py'))
    globals_ = old['load_helper'].__globals__
    original_dependencies = old['DEPENDENCIES']
    names = list(original_dependencies)
    retained_binding = RETAINED/'PRODUCT_RUN_BINDING.json'
    dependencies = {
        names[0]:original_dependencies[names[0]],
        retained_binding.relative_to(V).as_posix():old['digest'](retained_binding.read_bytes()),
        names[2]:original_dependencies[names[2]],
        names[3]:original_dependencies[names[3]],
    }
    tools = RETAINED/'TOOLS_SCHEMA.json'
    globals_.update(RUN=RUN,EXTERNAL=RUN/'candidate_install',EVIDENCE='9a46968545a6226cb9d44c27e669ab197fd063d3',
                    BASE=BASE,BASE_SOURCE=BASE_SOURCE,BASE_WHEEL=BASE_WHEEL,BASE_TOOLS=tools,
                    BASE_TOOLS_SHA=old['digest'](tools.read_bytes()),VERSION='9.7.2+m1.source.region.task.entry.001',
                    DEPENDENCIES=dependencies,CHANGED=SOURCE)
    helper,_ = old['load_helper'](ROOT,HERE)
    helper.probe = probe
    helper.check_catalogue = check_catalogue
    source = Path(helper.__file__).read_text(encoding='utf8')
    functions = {node.name:ast.get_source_segment(source,node) for node in ast.parse(source).body
                 if isinstance(node,ast.FunctionDef) and node.name in ('inspect','build')}
    edits = {
        'inspect': [('if tools != json.loads(read(BASE_TOOLS)):\n        raise ValueError(\'actual installed tools/list differs from the historical arm\')',
                     'check_catalogue(json.loads(read(BASE_TOOLS)),tools,binding[\'preparation_git\'])')],
        'build': [("if baseline_actual['tools'] != tools:\n        raise ValueError('candidate and baseline installed tools differ')",
                   "check_catalogue(baseline_actual['tools'],tools,candidate)"),
                  ("'tool_schema_matches_historical_actual_directory': True,",
                   "'tool_schema_matches_historical_actual_directory': False,\n"
                   "               'tool_schema_added': ['human_eye_source_region_measure'],")],
    }
    for name,replacements in edits.items():
        code = functions[name]
        for before,after in replacements:
            if code.count(before)!=1:
                raise ValueError('retained_build_anchor_changed/' + name)
            code = code.replace(before,after)
        exec(compile(code,str(helper.__file__),'exec'),vars(helper))
    return old,helper


def main():
    if not sys.flags.isolated or not sys.dont_write_bytecode or Path(sys.executable).resolve()!=PYTHON.resolve():
        raise ValueError('fixed_interpreter_required')
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--candidate')
    mode.add_argument('--inspect',type=Path)
    args = parser.parse_args()
    retained,helper = configure()
    if args.inspect is not None:
        helper.inspect(args.inspect)
        return
    retained['verify_lineage'](ROOT,args.candidate)
    helper.build(args.candidate)


if __name__=='__main__':
    main()
