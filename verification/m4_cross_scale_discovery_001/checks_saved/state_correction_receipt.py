"""Finalize the saved-only state adapter receipt from preserved source files."""

import ast
import difflib
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def pin(path):
    path = Path(path)
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
    derived = HERE/'state_adapter_r1.py'
    text,revised = original.read_text(encoding='utf8'),derived.read_text(encoding='utf8')
    if text.replace("public['schema'] == 'active-observation-brief-v2'", "public['schema'] == 'active-observation-brief-v5'") != revised:
        raise ValueError('saved_state_schema_change_scope')
    record = dict(schema='cross-scale-saved-state-correction-v1',original=pin(original),derived=pin(derived),
                  original_failure_stderr=pin(HERE/'state.stderr.txt'),
                  independent_baseline_projection_AST_equal=True,
                  AST_scope='Remove only the new region_task early dispatch. The complete established default projection is AST-identical.',
                  source_inputs=[pin(old),pin(current),pin(__file__)],
                  correction='The old default brief already upgrades to v5 with region locations and inspection. Original state checker pinned v2.',
                  diff=''.join(difflib.unified_diff(text.splitlines(True),revised.splitlines(True),fromfile='state_adapter.py',tofile='state_adapter_r1.py')),
                  receipt_preparation_failure=dict(source=pin(HERE/'derive_state_r1.py'),error_type='AttributeError',
                    error="'str' object has no attribute 'read_bytes'",at='pin(__file__) while assembling receipt, after writing the exact derived adapter',
                    retained=True,impact='No actual operation or product state. Derived adapter executed once and all 7 saved requests passed.'),
                  product_changes=0,actual_operations=0)
    with (HERE/'STATE_SAVED_CORRECTION_01.json').open('x',encoding='utf8',newline='\n') as stream:
        json.dump(record,stream,sort_keys=True,indent=2)
        stream.write('\n')
    print(json.dumps(dict(passed=True,legacy_projection_AST_equal=True,failed_receipt_source_retained=True)))


if __name__=='__main__':
    main()
