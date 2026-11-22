"""Use the retained observed production MCP worker for either installed arm."""

import argparse
import ast
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parent))
from host import RUN, SLOTS, WORKER, assemble, load, owned_root, read, require


def call_production(main, arguments, evidence, source_sha256):
    from meter import observe_installed

    with observe_installed(evidence, source_sha256):
        return main(arguments)


def retained_worker():
    # The only extra behavior is a same-process timing observer around the
    # original installed stdio main. Keep its receipts and signed source loader.
    original = load('_m2_live_retained_worker', WORKER)
    parsed = ast.parse(WORKER.read_bytes(), filename=str(WORKER))
    worker = next(node for node in parsed.body if isinstance(node, ast.FunctionDef) and node.name == 'worker')
    expected = ast.dump(ast.parse('production_server.main(production_arguments)', mode='eval').body)
    anchors = [node for node in ast.walk(worker) if isinstance(node, ast.Call) and ast.dump(node) == expected]
    require(len(anchors) == 1, 'retained_production_entry_anchor_changed')
    call, = anchors
    call.func = ast.Name(id='call_production', ctx=ast.Load())
    call.args = ast.parse('(production_server.main, production_arguments, args.evidence, SOURCE_SHA)',
                          mode='eval').body.elts
    scope = dict(vars(original), call_production=call_production)
    ast.fix_missing_locations(worker)
    exec(compile(ast.Module(body=[worker], type_ignores=[]), str(WORKER), 'exec'), scope)
    return scope['worker']


def main():
    require(sys.flags.isolated and sys.dont_write_bytecode, 'fixed_isolated_interpreter_required')
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('binding', 'config', 'ledger', 'evidence', 'archive'):
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--label', choices=tuple(SLOTS), required=True)
    parser.add_argument('--phase', choices=('formal',), required=True)
    parser.add_argument('--region-task-evidence', action='store_true', required=True)
    args = parser.parse_args()
    folder = args.config.resolve(strict=True).parent
    root = folder.parents[1]
    preflight = root.is_relative_to(RUN.resolve()/'preflight')
    root = owned_root(root, preflight)
    require(folder == root/'slots'/args.label, 'current_owned_MCP_slot_required')
    expected = {'config': folder/'PRODUCT_CONFIG.json', 'ledger': root/'budget',
                'evidence': folder/'mcp_io', 'archive': folder/'product_full'}
    require(all(getattr(args, name).resolve() == path for name, path in expected.items()),
            'current_owned_MCP_paths_required')
    _, _, binding = assemble(root, args.label, args.binding)
    config = read(args.config)
    require(Path(config['state_file']) == folder/'product_state.json'
            and Path(config['audit_file']) == folder/'product_audit.jsonl'
            and config['project_root'] == binding['install_root']
            and config['expected_identity']['source_sha256'] == binding['source_sha256']
            and config['blender']['host'] == '127.0.0.1', 'current_MCP_host_binding_required')
    if preflight:
        def disallow_live(event, _):
            if event in ('socket.connect', 'subprocess.Popen', 'os.system', 'os.spawn', 'os.exec'):
                raise RuntimeError('preflight_MCP_cannot_connect_or_start_processes')

        sys.addaudithook(disallow_live)
    else:
        ready = read(folder/'native/READY.json')
        require((config['blender']['host'], config['blender']['port']) == (ready['host'], ready['port']),
                'current_owned_Blender_READY_endpoint_required')
    return retained_worker()(args)


if __name__ == '__main__':
    raise SystemExit(main())
