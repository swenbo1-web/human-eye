"""Preserve the first state-checker failure and correct its legacy schema lookup."""

import ast
import difflib
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def pin(path):
    raw = path.read_bytes()
    return dict(path=str(path.resolve()),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())


def main():
    old = Path('D:/he_m5_observe_measure_001/B/product/human_eye_plugin/live_spatial_mcp.py')
    current = ROOT/'human_eye_plugin/live_spatial_mcp.py'
    functions = []
    for path in (old,current):
        tree = ast.parse(path.read_bytes())
        function = next(node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name=='project_active_observation_brief')
        if path == current:
            dispatch = function.body[1]
            if not (isinstance(dispatch,ast.If) and ast.unparse(dispatch.test)=="'region_task' in value.get('facts', {})"):
                raise ValueError('new_region_dispatch_identity')
            function.body.pop(1)
        functions.append(ast.dump(function))
    if functions[0]!=functions[1]:
        raise ValueError('legacy_brief_projection_changed')
    original = HERE/'state_adapter.py'
    text = original.read_text(encoding='utf8')
    before,after = "public['schema'] == 'active-observation-brief-v2'", "public['schema'] == 'active-observation-brief-v5'"
    if text.count(before)!=1:
        raise ValueError('original_state_schema_expression')
    revised = text.replace(before,after)
    target = HERE/'state_adapter_r1.py'
    with target.open('x',encoding='utf8',newline='\n') as stream:
        stream.write(revised)
    record = dict(schema='cross-scale-saved-state-correction-v1',original=pin(original),derived=pin(target),
                  original_failure_stderr=pin(HERE/'state.stderr.txt'),
                  independent_baseline_projection_AST_equal=True,AST_scope='Remove only the new region_task early dispatch. The entire preexisting default projection function is AST-identical.',
                  source_inputs=[pin(old),pin(current),pin(__file__)],
                  correction='The established non-region task brief already upgrades through v3/v4/v5 when locations and inspection are present. The original state checker incorrectly pinned v2.',
                  diff=''.join(difflib.unified_diff(text.splitlines(True),revised.splitlines(True),fromfile='state_adapter.py',tofile='state_adapter_r1.py')),
                  product_changes=0,actual_operations=0)
    with (HERE/'STATE_SAVED_CORRECTION_01.json').open('x',encoding='utf8',newline='\n') as stream:
        json.dump(record,stream,sort_keys=True,indent=2)
        stream.write('\n')
    print(json.dumps(dict(derived=True,legacy_default_AST_equal=True)))


if __name__=='__main__':
    main()
