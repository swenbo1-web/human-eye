"""Keep the original installed stdio entry and observe public measurement stdio and stage timing."""

import argparse
import ast
import json
from runpy import run_path
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from host import (
    LABELS, OLD, REPLAY, RUN, WORKER, assemble, entry_root, load, owned_replay_endpoint, read, require,
)


def call_production(main, arguments, evidence, source_sha256):
    from human_eye_plugin import live_service

    scoped = '--source-region-measurement' in arguments
    method = '_measure_selective_source_region' if scoped else '_observe_source_region'
    service = live_service.LiveSpatialService
    original = getattr(service, method)
    sequence = 0

    def observed(instance, *args, **kwargs):
        value = original(instance, *args, **kwargs)
        if value.get('status') in ('complete', 'completed') and value.get('frames') == []:
            nonlocal sequence
            sequence += 1
            with (evidence/f'PRODUCER_RESULT_{sequence}.json').open('x', encoding='utf8') as out:
                json.dump(value, out, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(',', ':'))
                out.write('\n')
        return value

    meter = run_path(str(OLD/'meter.py'))
    setattr(service, method, observed)
    try:
        with meter['observe_installed'](evidence, source_sha256):
            return main(arguments)
    finally:
        setattr(service, method, original)


def observed_production_worker():
    original = load('_scoped_retained_held_entry', WORKER)
    program = ast.parse(WORKER.read_bytes(), filename=str(WORKER))
    worker, = [node for node in program.body if isinstance(node, ast.FunctionDef) and node.name == 'worker']
    calls = [node for node in ast.walk(worker) if isinstance(node, ast.Call)
             and ast.unparse(node) == 'production_server.main(production_arguments)']
    require(len(calls) == 1,'retained_production_entry_anchor_changed')
    call, = calls
    call.func = ast.Name(id='call_production',ctx=ast.Load())
    call.args = ast.parse('(production_server.main, production_arguments, args.evidence, SOURCE_SHA)',
                           mode='eval').body.elts
    anchors = [index for index,node in enumerate(worker.body) if isinstance(node, ast.Assign)
               and [ast.unparse(target) for target in node.targets] == ['production_arguments']]
    require(len(anchors)==1,'retained_launcher_arguments_anchor_changed')
    worker.body[anchors[0]+1:anchors[0]+1] = ast.parse(
        "if args.source_region_measurement:\n    production_arguments.append('--source-region-measurement')").body
    scope = dict(vars(original),call_production=call_production)
    invoke = ast.fix_missing_locations(ast.Module(body=[worker],type_ignores=[]))
    exec(compile(invoke,str(WORKER),'exec'),scope)
    return scope['worker']


def main():
    require(sys.flags.isolated and sys.dont_write_bytecode,'fixed_isolated_worker_required')
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('binding','config','ledger','evidence','archive'):
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--phase',choices=('formal',),required=True)
    parser.add_argument('--label',choices=tuple(LABELS),required=True)
    args = parser.parse_args()
    args.region_task_evidence = False
    args.source_region_measurement = LABELS[args.label][1] == 'B'
    slot = args.config.resolve(strict=True).parent
    root = slot.parents[1]
    replay = root == REPLAY/args.label
    startup = root == entry_root(args.label)
    require((root == RUN or replay or startup) and slot == root/'slots'/args.label,
            'owned_or_registered_replay_worker_required')
    paths = {'config':slot/'PRODUCT_CONFIG.json','ledger':root/'budget','evidence':slot/'mcp_io',
             'archive':slot/'product_full'}
    require(all(getattr(args,key).resolve() == path for key,path in paths.items()),'owned_worker_paths_changed')
    _,_,binding = assemble(root,args.label,args.binding)
    config = read(args.config)
    require(Path(config['state_file']) == slot/'product_state.json'
            and Path(config['audit_file']) == slot/'product_audit.jsonl'
            and config['project_root'] == binding['install_root']
            and config['expected_identity']['source_sha256']==binding['source_sha256'],'owned_installed_worker_binding')
    if replay:
        endpoint = owned_replay_endpoint(root,args.label)
        expected = (endpoint.host,endpoint.port)
    elif startup:
        expected = ('127.0.0.1',1)
    else:
        ready = read(slot/'native/READY.json')
        expected = (ready['host'],ready['port'])
    require(expected==(config['blender']['host'],config['blender']['port']) and expected[0]=='127.0.0.1',
            'registered_readonly_loopback_endpoint_required')
    if startup or replay:
        def restrict(event,event_args):
            if event == 'socket.connect':
                require(replay and event_args[1]==expected,'offline_socket_not_registered')
            elif event in ('subprocess.Popen','os.system','os.startfile','os.spawn','os.exec','socket.bind'):
                raise PermissionError('offline_worker_cannot_launch_or_listen')
        sys.addaudithook(restrict)

    return observed_production_worker()(args)


if __name__ == '__main__':
    raise SystemExit(main())
