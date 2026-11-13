"""Independent import/AST wiring audit. Does not invoke any task function."""
import ast
import builtins
import dis
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import types

SOURCE = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
CANDIDATE = SOURCE / 'verification/m4_consumer_error_contract_001'
LEGACY = SOURCE / 'verification/m4_active_coverage_consumption_001'
OUT = Path(__file__).resolve().parent
events = []
phase = 'import'

def audit(event, args):
    blocked = event in {'subprocess.Popen', 'os.system', 'socket.connect', 'socket.bind'}
    if event == 'open' and phase == 'import':
        mode = args[1]
        flags = args[2]
        blocked = ((isinstance(mode, str) and any(c in mode for c in 'wax+')) or
                   (isinstance(flags, int) and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)))
    if phase == 'import' and event in {'os.mkdir', 'os.remove', 'os.rename', 'os.rmdir'}:
        blocked = True
    if blocked:
        events.append(event)
        raise RuntimeError('audit_blocked:' + event)

sys.addaudithook(audit)
spec = importlib.util.spec_from_file_location('_independent_error_contract_driver', CANDIDATE / 'driver.py')
driver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(driver)
phase = 'inspect'
consumer = driver.consumer
checks = {}
details = {}

def check(name, value):
    checks[name] = bool(value)

def inspect_clone(name, new, old, expected):
    check(name + '.code_identical', new.__code__ is old.__code__)
    check(name + '.defaults_identical', new.__defaults__ is old.__defaults__)
    check(name + '.closure_identical', new.__closure__ is old.__closure__)
    check(name + '.kwdefaults_equal', new.__kwdefaults__ == old.__kwdefaults__)
    check(name + '.private_globals', new.__globals__ is not old.__globals__)
    changed = sorted(key for key in set(new.__globals__) | set(old.__globals__)
                     if key not in new.__globals__ or key not in old.__globals__
                     or new.__globals__[key] is not old.__globals__[key])
    check(name + '.exact_globals_replacements', changed == sorted(expected))
    names = set()
    def visit(code):
        for instruction in dis.get_instructions(code):
            if instruction.opname in {'LOAD_GLOBAL', 'LOAD_NAME'}:
                names.add(instruction.argval)
        for constant in code.co_consts:
            if isinstance(constant, types.CodeType):
                visit(constant)
    visit(new.__code__)
    unresolved = sorted(names - set(new.__globals__) - set(vars(builtins)))
    check(name + '.global_names_resolve', not unresolved)
    details[name] = {'global_replacements': changed, 'unresolved_globals': unresolved,
                     'source_file': old.__code__.co_filename,
                     'source_first_line': old.__code__.co_firstlineno}

inspect_clone('consume_turn', consumer.consume_turn, consumer.legacy.consume_turn, {'archive_turn'})
inspect_clone('run_route', driver.run_route, driver.legacy.run_route, {'consumer', 'common_image_faults'})
inspect_clone('run_batch', driver.run_batch, driver.legacy.run_batch, {'run_route'})
check('path.batch_to_route', driver.run_batch.__globals__['run_route'] is driver.run_route)
check('path.route_to_consumer', driver.run_route.__globals__['consumer'] is consumer)
check('path.route_to_common', driver.run_route.__globals__['common_image_faults'] is driver.common_image_faults)
check('path.consume_to_archive', consumer.consume_turn.__globals__['archive_turn'] is consumer.archive_turn)
check('path.archive_to_contract', consumer.archive_turn.__globals__['result_contract'] is consumer.result_contract)
check('path.common_to_contract', driver.common_image_faults.__globals__['consumer'].result_contract is consumer.result_contract)
check('legacy.archive_unmutated', consumer.legacy.consume_turn.__globals__['archive_turn'] is consumer.legacy.archive_turn)
check('legacy.route_consumer_unmutated', driver.legacy.run_route.__globals__['consumer'] is driver.legacy.consumer)
check('legacy.route_common_unmutated', driver.legacy.run_route.__globals__['common_image_faults'] is driver.legacy.common_image_faults)
check('legacy.batch_route_unmutated', driver.legacy.run_batch.__globals__['run_route'] is driver.legacy.run_route)
check('alias.safe_environment', consumer.safe_environment is consumer.legacy.safe_environment)
for name in ('outer_accepted', 'terminal_service_faults', 'publish_route'):
    check('alias.' + name, getattr(driver, name) is getattr(driver.legacy, name))
for name in ('read', 'save', 'sha', 'packer'):
    check('consumer_alias.' + name, getattr(consumer, name) is getattr(consumer.legacy, name))

tree = ast.parse((LEGACY / 'driver.py').read_text(encoding='utf8'))
route_ast = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'run_route')
attributes = sorted({node.attr for node in ast.walk(route_ast)
                     if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)
                     and node.value.id == 'consumer'})
check('route.consumer_exports_complete', all(hasattr(consumer, name) for name in attributes))
check('route.consumer_callable_exports', callable(consumer.safe_environment) and callable(consumer.consume_turn)
      and callable(consumer.packer.capture_cell))
check('candidate.entry_exports', callable(driver.run_route) and callable(driver.run_batch))
check('candidate.import_no_forbidden_operations', not events)
check('route.legacy_actor_root_preserved', driver.run_route.__globals__['HERE'] == LEGACY)
check('route.original_input_checks_preserved', driver.run_route.__globals__['input_checks'] is driver.legacy.input_checks)
check('route.original_publish_preserved', driver.run_route.__globals__['publish_route'] is driver.legacy.publish_route)
check('route.original_terminal_preserved', driver.run_route.__globals__['terminal_service_faults'] is driver.legacy.terminal_service_faults)
details['run_route_consumer_attributes'] = attributes
details['candidate_nonexported_helpers'] = [name for name in ('source_files', 'check_frozen', 'input_checks', 'main') if not hasattr(driver, name)]
details['source_guard_note'] = 'Original source_files/check_frozen are in legacy module, use old HERE and cover old source graph. A fresh online launcher must explicitly freeze candidate result_contract.py, consumer.py, driver.py plus actual launcher/plan and inherited dependency closure, then invoke candidate.run_batch with a fresh runtime root.'
details['fixture_note'] = 'Original fake_cli.py intentionally kills P thin process to exercise missing EXIT. For fresh positive normalized-error wiring smoke, use a new fixture that closes normally. Do not modify historical fixture.'

paths = [CANDIDATE / name for name in ('consumer.py', 'driver.py', 'result_contract.py', 'CONNECTIONS.json', 'DEPENDENCIES.json')]
paths += [LEGACY / name for name in ('consumer.py', 'driver.py', 'fake_cli.py', 'FROZEN.json')]
inputs = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths if path.exists()}
result = {'schema': 'independent-candidate-wiring-review-v1',
          'candidate_commit': 'cb5c33a158a9dea06c8151248cc42d2b87c5697b',
          'scope': 'Pure offline import, identity and bytecode/AST checks; no candidate business function invoked.',
          'checks': checks, 'passed': sum(checks.values()), 'total': len(checks), 'all_passed': all(checks.values()),
          'details': details, 'blocked_operation_attempts': events,
          'invocations': {'matcher': 0, 'archive_turn': 0, 'consume_turn': 0, 'run_route': 0,
                          'run_batch': 0, 'CLI': 0, 'actor': 0, 'model': 0, 'renderer': 0},
          'online_validated': False}
(OUT / 'INPUTS.json').write_text(json.dumps(inputs, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
(OUT / 'RESULTS.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
print(json.dumps({'all_passed': result['all_passed'], 'passed': result['passed'], 'total': result['total'],
                  'consumer_attributes': attributes, 'blocked_operation_attempts': events}, ensure_ascii=False))
raise SystemExit(0 if result['all_passed'] else 1)
