"""Replay the retained installed MCP request and confirm exact hot reuse."""

import argparse
import importlib.util
import json
from pathlib import Path
import sys
import tempfile


HERE = Path(__file__).resolve().parent
PREVIOUS = HERE.parents[1] / 'm4_cross_scale_global_index_reuse_001/checks/index_controls.py'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binding', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location('_cold_frustum_original_replay', PREVIOUS)
    previous = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(previous)
    history = previous.previous.History()
    for path in (Path(__file__), Path(sys.executable), PREVIOUS, previous.PREVIOUS):
        history.pin(path)
    binding = json.loads(history.pin(args.binding))
    root = Path(binding['install_root']).resolve()
    sys.path[:0] = [str(root), binding['dependency_root']]
    manifest = {row['path']: row['sha256'] for row in binding['source_manifest']}
    for name in ('active_observation', 'active_observation_host', 'active_observation_images',
                 'active_observation_region_task', 'blender_host', 'live_service', 'live_spatial_mcp', 'read_context'):
        module = __import__('human_eye_plugin.' + name, fromlist=[name])
        source = Path(module.__file__).resolve()
        relative = 'human_eye_plugin/' + name + '.py'
        assert source == root / relative and previous.previous.sha(history.pin(source)) == manifest[relative]
    producer, terminal, registered = history.inputs()
    capture = previous.previous.reconstruct_capture(producer, terminal)
    observed = dict(registered, response_detail='brief')
    predict = dict(observed, response_detail='full', include_image=False)
    with tempfile.TemporaryDirectory(prefix='m4-frustum-hot-replay-') as temporary:
        folder = Path(temporary) / 'replay'
        with previous.Replay(capture, producer, folder) as replay:
            cold, original = previous.operation(replay.call(observed), 'observation', baseline=False, built=1)
            cold_resource = replay.resources()[previous.RESOURCE]
            prediction, _ = previous.operation(replay.call(predict), 'prediction', baseline=False, built=0)
            hot, repeated = previous.operation(replay.call(observed), 'observation', baseline=False, built=0,
                                               cache_hit=True)
            assert replay.resources()[previous.RESOURCE] is cold_resource and replay.host.captures == 3
            assert len(cold['public_png_sha256']) == 3
            assert cold['public_png_sha256'] == hot['public_png_sha256'] == [
                frame['image_sha256'] for frame in producer['frames']]
            assert cold['witnesses'] == hot['witnesses']
            assert original['frames'] == repeated['frames'] and not hot['replayed_frames']
            assert cold['work']['frustum_certified_views'] == 6 and not cold['work']['frustum_shadow_legacy']
            assert prediction['work']['global_index_cache_hit'] and prediction['work']['frustum_proof_ns'] == 0
    result = {'schema': 'm4-cold-frustum-offline-hot-replay-v1', 'passed': True,
              'product_root': binding['install_root'], 'runtime_source_sha256': binding['source_sha256'],
              'models': 0, 'owned_Blender': 0, 'actual_new_rasters': 0,
              'cold': cold, 'prediction': prediction, 'hot': hot, 'source_pins': list(history.pins.values())}
    with args.output.open('x', encoding='utf8', newline='\n') as out:
        json.dump(result, out, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2)
        out.write('\n')
    print('Offline installed same-request hot replay passed.')


if __name__ == '__main__':
    main()
