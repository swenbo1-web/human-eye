"""Dispatch one frozen Yanyite slot through the actual retained owned runner."""

import argparse
import ast
from pathlib import Path
import sys


sys.path.insert(0,str(Path(__file__).resolve().parent))
from common import FORMAL, ORDER, add_paths, catalogue_for, load_retained

add_paths()
import admission
from admission import require


_source = FORMAL/'harness/run_slot.py'
_retained = load_retained('_yanyite_adopted_run_slot',_source)
require(_retained.validate_admission is admission.validate_admission, 'wrong_run_slot_admission')
_tree = ast.parse(_source.read_bytes(),filename=str(_source))
_run = next(node for node in _tree.body if isinstance(node,ast.FunctionDef) and node.name=='run')
_old = ast.parse("read(PRODUCT_BINDING.parent / 'TOOLS_SCHEMA.json')",mode='eval').body
_matches = [node for node in ast.walk(_run) if isinstance(node,ast.Call) and ast.dump(node)==ast.dump(_old)]
require(len(_matches)==1,'retained_run_slot_catalogue_anchor_changed')
_matches[0].args = [ast.Call(func=ast.Name(id='catalogue_for',ctx=ast.Load()),
                            args=[ast.Name(id='label',ctx=ast.Load())],keywords=[])]
_diagnostic_path = ast.parse("NS / 'qualification/diagnostic.py'",mode='eval').body
_diagnostics = [node for node in ast.walk(_run) if isinstance(node,ast.BinOp)
                and ast.dump(node)==ast.dump(_diagnostic_path)]
require(len(_diagnostics)==1,'retained_run_slot_diagnostic_anchor_changed')
_diagnostics[0].right = ast.Constant('runtime/diagnostic.py')
_scope = dict(vars(_retained),catalogue_for=catalogue_for)
exec(compile(ast.fix_missing_locations(ast.Module(body=[_run],type_ignores=[])),str(_source),'exec'),_scope)
run = _scope['run']


if __name__=='__main__':
    require(sys.flags.isolated and sys.dont_write_bytecode,'fixed_isolated_interpreter_flags_required')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('label',nargs='?',choices=ORDER)
    parser.add_argument('--preflight',action='store_true')
    args = parser.parse_args()
    require(bool(args.label)!=args.preflight,'choose_exactly_one_live_slot_or_offline_preflight')
    if args.preflight:
        from preflight import prove

        raise SystemExit(prove())
    raise SystemExit(run(args.label))
