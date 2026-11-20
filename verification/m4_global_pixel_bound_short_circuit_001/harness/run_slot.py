"""Reuse the proven one-cold-call dense runner with explicit arm binding."""

import argparse
import ast
import json
from pathlib import Path
import sys
from textwrap import dedent


sys.path.insert(0, str(Path(__file__).resolve().parent))
import admission  # Bind the new admission before the retained runner prepends its directory.
import common
from common import ARMS, BINDINGS, BLOCKER, DENSE, ORDER, REQUEST, load, read


def prepare_runner(label):
    common.PRODUCT_BINDING = BINDINGS[ARMS[label]]
    common.SOURCE_SHA = read(common.PRODUCT_BINDING)['source_sha256']
    source = DENSE / 'harness/run_slot.py'
    current_path = sys.path[:]
    try:
        retained = load('_pixel_bound_retained_dense_slot', source)
    finally:
        sys.path[:] = current_path
    original = source.read_text(encoding='utf-8')
    tree = ast.parse(original, filename=str(source))
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'run')
    code = dedent('\n'.join(original.splitlines()[function.lineno - 1:function.end_lineno]))
    replacements = {
        "'phase': phase, 'arm': group,": "'phase': phase, 'arm': ARMS[label],",
        "'product_source_sha256': binding['source_sha256'],": (
            "'product_git': binding['preparation_git'], 'product_source_sha256': binding['source_sha256'],"),
        "path = NS / 'inputs/REQUEST.json'": "path = REQUEST",
        "runtime = runtime_module.Runtime(folder, label, task_deadline, owned_deadline)": (
            "runtime_module.Runtime._start_public_mcp.__globals__['NS'] = BLOCKER\n"
            "        runtime = runtime_module.Runtime(folder, label, task_deadline, owned_deadline)"),
    }
    for before, after in replacements.items():
        if code.count(before) != 1:
            raise ValueError('retained_dense_runner_anchor_changed/' + before)
        code = code.replace(before, after)
    scope = dict(vars(retained), ARMS=ARMS, REQUEST=REQUEST, BLOCKER=BLOCKER)
    if scope['admit'] is not admission.admit:
        raise ValueError('retained_runner_did_not_bind_current_admission')
    exec(compile(code, str(source), 'exec'), scope)
    return scope['run']


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('slot', choices=ORDER)
    parser.add_argument('--dispatch-smoke', action='store_true')
    args = parser.parse_args()
    runner = prepare_runner(args.slot)
    if args.dispatch_smoke:
        if not sys.flags.isolated or not sys.dont_write_bytecode:
            raise ValueError('pinned_interpreter_I_B_required')
        print(json.dumps({'slot': args.slot, 'arm': ARMS[args.slot],
                          'admission': str(Path(admission.__file__).resolve()),
                          'binding': str(runner.__globals__['PRODUCT_BINDING'].resolve()),
                          'product_source_sha256': common.SOURCE_SHA,
                          'fresh_process_prepared_only': True}))
    else:
        raise SystemExit(runner(args.slot))
