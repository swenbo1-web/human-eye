"""Meter the installed production stdio entry and cap actual software image construction."""
import json
from pathlib import Path
import sys
from time import perf_counter_ns


def save(path, value):
    with path.open('x',encoding='utf8',newline='\n') as out:
        json.dump(value,out,ensure_ascii=False,allow_nan=False,separators=(',',':'))
        out.write('\n')


def main(arm, binding_path, config_path, publication):
    binding = json.loads(binding_path.read_bytes())
    config = json.loads(config_path.read_bytes())
    root = Path(binding['install_root']).resolve(strict=True)
    if arm not in ('A','B') or Path(config['project_root']) != root or config['blender']['host'] != '127.0.0.1':
        raise ValueError('isolated_stdio_binding')
    address = ('127.0.0.1',config['blender']['port'])

    def isolate(event,args):
        if event == 'socket.connect' and args[1] != address:
            raise PermissionError('isolated_stdio_connect_scope')
        if event in ('subprocess.Popen','os.system','os.startfile','os.spawn','os.exec','socket.bind'):
            raise PermissionError('isolated_stdio_must_not_launch_or_listen')
    sys.addaudithook(isolate)
    sys.path[:0] = [str(root),binding['dependency_root']]
    from human_eye_plugin import production_server
    from human_eye_plugin.active_observation_images import SceneObservationImages
    from human_eye_plugin.live_service import LiveSpatialService
    from human_eye_plugin.runtime_identity import runtime_identity

    identity = runtime_identity()
    if (identity['source_sha256'] != binding['source_sha256']
            or Path(production_server.__file__).parent.parent != root):
        raise ValueError('actual_installed_stdio_source_mismatch')
    name = '_observe_source_region' if arm == 'A' else '_observe_scoped_source_region'
    original = getattr(LiveSpatialService,name)
    results, renders = [], []
    render = SceneObservationImages.render_view

    def observed(instance,*args,**kwargs):
        t0 = perf_counter_ns()
        value = original(instance,*args,**kwargs)
        t1 = perf_counter_ns()
        if value.get('status') == 'complete':
            results.append({'sequence':len(results)+1,'service_started_ns':t0,'service_returned_ns':t1})
            save(publication/f'PRODUCER_{len(results)}.json',value)
        return value

    def bounded_render(instance,view_name):
        if len(renders) >= 2:
            raise ValueError('formal_two_constructs_per_arm_limit')
        receipt={'view':view_name,'started_ns':perf_counter_ns(),'completed':False}
        renders.append(receipt)
        try:
            value=render(instance,view_name)
            receipt['completed']=True
            return value
        finally:
            receipt['closed_ns']=perf_counter_ns()
            save(publication/f'RASTER_{len(renders)}.json',receipt)

    setattr(LiveSpatialService,name,observed)
    SceneObservationImages.render_view=bounded_render
    try:
        flags=['--config',str(config_path)]
        if arm=='B':
            flags.append('--source-region-visual')
        result=production_server.main(flags)
        save(publication/'STDIO_WORKER_EOF.json',{'actual_main_return':result,'at_ns':perf_counter_ns(),
            'producer_calls':results,'render_attempts':renders,'source_sha256':identity['source_sha256']})
        return result
    finally:
        setattr(LiveSpatialService,name,original)
        SceneObservationImages.render_view=render


if __name__ == '__main__':
    if len(sys.argv) != 5 or not sys.flags.isolated or not sys.dont_write_bytecode:
        raise ValueError('isolated_worker_required')
    raise SystemExit(main(sys.argv[1],*(Path(p).resolve(strict=True) for p in sys.argv[2:])))
