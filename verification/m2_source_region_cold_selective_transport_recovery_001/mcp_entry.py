"""Keep the original installed stdio entry and permit only registered replay sockets."""

import argparse
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from host import ENTRY, LABELS, OLD, PREVIOUS, REPLAY, RUN, assemble, load, owned_replay_endpoint, read, require


def main():
    require(sys.flags.isolated and sys.dont_write_bytecode,'fixed_isolated_worker_required')
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('binding','config','ledger','evidence','archive'):
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--phase',choices=('formal',),required=True)
    parser.add_argument('--label',choices=tuple(LABELS),required=True)
    args = parser.parse_args()
    args.region_task_evidence = False
    slot = args.config.resolve(strict=True).parent
    root = slot.parents[1]
    replay = root == REPLAY/args.label
    startup = root == ENTRY/args.label
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

    sys.path.append(str(OLD))
    installed = load('_recovery_original_selective_entry',OLD/'mcp_entry.py')
    held = load('_recovery_original_held_entry',PREVIOUS/'mcp_entry.py')
    held.call_production = installed.call_production
    return held.retained_worker()(args)


if __name__ == '__main__':
    raise SystemExit(main())
