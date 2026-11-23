"""Observe the installed production child and preserve the original MCP payloads."""

import argparse
import ast
from pathlib import Path
from runpy import run_path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from host import METER, RUN, SLOTS, WORKER, assemble, load, read, require


def timed_main(main, arguments, evidence, source_sha256):
    meter = run_path(str(METER))['observe_installed']
    with meter(evidence, source_sha256):
        return main(arguments)


def observed_worker():
    source = ast.parse(WORKER.read_bytes(), filename=str(WORKER))
    worker, = (node for node in source.body if isinstance(node, ast.FunctionDef) and node.name == 'worker')
    service, = (node for node in worker.body if isinstance(node, ast.ClassDef) and node.name == 'ObservedService')
    observe, = (node for node in service.body if isinstance(node, ast.FunctionDef) and node.name == 'observe')
    text = ast.unparse(observe).replace('def observe(', 'def _measure_selective_source_region(', 1)
    require(text.count('super().observe(') == 1, 'one_known_producer_archive_delegate_required')
    service.body.append(ast.parse(text.replace('super().observe(', 'super()._measure_selective_source_region(')).body[0])
    launch, = (node for node in ast.walk(worker) if isinstance(node, ast.Call)
               and ast.unparse(node) == 'production_server.main(production_arguments)')
    launch.func = ast.Name(id='timed_main', ctx=ast.Load())
    launch.args = ast.parse('(production_server.main, production_arguments, args.evidence, SOURCE_SHA)',
                            mode='eval').body.elts
    flag, = (index for index,node in enumerate(worker.body) if isinstance(node, ast.If)
             and ast.unparse(node.test) == 'args.region_task_evidence')
    worker.body[flag+1:flag+1] = ast.parse(
        "if args.label == 'B1':\n    production_arguments.append('--source-region-measurement')").body
    implementation = load('_scoped_consumption_worker', WORKER)
    scope = dict(vars(implementation), timed_main=timed_main)
    parsed = ast.fix_missing_locations(ast.Module(body=[worker], type_ignores=[]))
    exec(compile(parsed, str(WORKER), 'exec'), scope)
    return scope['worker']


def main():
    require(sys.flags.isolated and sys.dont_write_bytecode,'fixed_isolated_worker_required')
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('binding','config','ledger','evidence','archive'):
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--phase', choices=('formal',), required=True)
    parser.add_argument('--label', choices=tuple(SLOTS), required=True)
    parser.add_argument('--region-task-evidence', action='store_true', required=True)
    args = parser.parse_args()
    folder = args.config.resolve(strict=True).parent
    root = folder.parents[1]
    preflight = root != RUN
    require((not preflight or root.is_relative_to(RUN/'preflight')) and folder==root/'slots'/args.label,
            'current_owned_MCP_slot_required')
    expected_paths = {'config': folder/'PRODUCT_CONFIG.json', 'ledger': root/'budget',
                      'evidence': folder/'mcp_io', 'archive': folder/'product_full'}
    require(all(getattr(args,k).resolve() == v for k,v in expected_paths.items()),
            'current_owned_MCP_paths_required')
    _,_,binding = assemble(root,args.label,args.binding)
    config = read(args.config)
    require(Path(config['state_file']) == folder/'product_state.json'
            and Path(config['audit_file']) == folder/'product_audit.jsonl'
            and config['project_root'] == binding['install_root']
            and config['expected_identity']['source_sha256'] == binding['source_sha256'],
            'current_MCP_install_slot_binding_required')
    replay = root/'REPLAY_READY.json'
    if replay.is_file() and preflight:
        info = read(replay)
        require(info['label']==args.label,'current_registered_replay_label_required')
        endpoint=(info['host'],info['port'])
        require(type(endpoint[1]) is int and 0 < endpoint[1] <= 65535, 'actual_replay_endpoint_required')
    elif preflight:
        endpoint=('127.0.0.1',1)
    else:
        ready=read(folder/'native/READY.json')
        endpoint=(ready['host'],ready['port'])
    require(endpoint==(config['blender']['host'],config['blender']['port'])
            and endpoint[0]=='127.0.0.1','current_owned_or_replay_loopback_endpoint_required')
    if preflight:
        def restrict(event, values):
            if event == 'socket.connect':
                require(replay.is_file() and values[1]==endpoint,'offline_unregistered_participant_connection')
            elif event in ('subprocess.Popen','os.system','os.startfile','os.spawn','os.exec','socket.bind'):
                raise PermissionError('offline_worker_cannot_launch_or_listen')
        sys.addaudithook(restrict)
    return observed_worker()(args)


if __name__ == '__main__':
    raise SystemExit(main())
