"""Read-only attention/cache acceptance against the live disposable fixture."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from human_eye_plugin.auto_router import _validated_scene
from human_eye_plugin.blender_mcp_host import BlenderMCPHost
from human_eye_plugin.live_service import LiveSpatialService
from human_eye_plugin.scene_rendering import render_scene_canvas


def run(directory):
    directory = Path(directory).resolve()
    fixture = json.loads((directory / 'live_fixture.json').read_text(encoding='utf-8'))
    destination = directory / 'attention_confirmation'
    destination.mkdir(exist_ok=False)
    host = BlenderMCPHost(ROOT)
    before = host.capture_scene()
    identities = {m['object_id'] for m in before['meshes']}
    if identities != {fixture[k] for k in ('focal_id', 'reference_id', 'obstacle_id')}:
        raise ValueError('Only the active disposable fixture is eligible for this test')
    _, meshes, fingerprint = _validated_scene(before)
    image, baseline = render_scene_canvas(meshes, 384, focal_id=fixture['focal_id'],
                                          reference_id=fixture['reference_id'])
    image.save(destination / 'default_q4.png')
    config = {'schema_version': '1.0', 'project_root': str(ROOT), 'enabled': True,
              'state_file': 'state.json', 'audit_file': 'events.jsonl', 'quad_size': 384,
              'max_sessions': 4, 'readback_atol_m': 1e-6}
    path = destination / 'connector.json'
    path.write_text(json.dumps(config), encoding='utf-8')
    service = LiveSpatialService(path, host=host)
    samples = []
    for index in range(3):
        started = time.perf_counter()
        result = service.observe('live-attention-confirmation',
            task_instruction=f'Observe measured contact detail, fixed acceptance sample {index}.',
            focal_id=fixture['focal_id'], reference_id=fixture['reference_id'])
        elapsed = (time.perf_counter() - started) * 1000
        route = result['routing']
        facts = json.loads(route['context_text'])
        if route['image']:
            (destination / f'attended_{index + 1}.png').write_bytes(base64.b64decode(route['image']['data']))
        samples.append({'index': index + 1, 'full_observe_ms_including_blender_and_persistence': elapsed,
            'scene_fingerprint': route['scene_fingerprint'], 'implementation_revision': result['implementation_revision'],
            'attention': facts['attention'], 'measurement_cache': facts['measurement_cache'],
            'scene_memory': facts['scene_memory'], 'canvas': facts['canvas'],
            'measurement': facts['measurement'], 'native_image_present': route['image'] is not None})
    after = host.capture_scene()
    checks = {'scene_unchanged_by_observation': before == after,
        'all_fresh_snapshots_match': all(s['scene_fingerprint'] == fingerprint for s in samples),
        'initial_attention_applied': samples[0]['attention']['decision'] == 'applied',
        'subsequent_attention_retained': all(s['attention']['decision'] == 'retained' for s in samples[1:]),
        'all_visible_and_positive_gain': all(s['attention'].get('net_gain_px', -1) >= 2 and
             s['attention'].get('raster_witness_supported') == [True, True] for s in samples),
        'all_native_images_present': all(s['native_image_present'] for s in samples),
        'subsequent_exact_measurement_hits': all(s['measurement_cache']['hits'] == 2 for s in samples[1:]),
        'static_snapshot_deduplicated': all(s['scene_memory']['duplicate_frame'] for s in samples[1:])}
    report = {'kind': 'read_only_live_blender_attention_cache_acceptance', 'checks': checks,
        'passed': all(checks.values()), 'test_count': len(checks), 'samples': samples,
        'model_api_calls': 0, 'double_blind': False,
        'benefit_scope': 'measured_known_geometry_visual_sampling_and_exact_measurement_reuse',
        'model_quality_gain_proven': False, 'baseline_canvas': baseline,
        'source_sha256': {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in
          ('human_eye_plugin/auto_router.py', 'human_eye_plugin/attention_policy.py',
           'human_eye_plugin/attention_rendering.py', 'human_eye_plugin/attention_raster.py',
           'human_eye_plugin/scene_cache.py', 'human_eye_plugin/live_service.py')}}
    (destination / 'report.json').write_text(json.dumps(report, indent=2, ensure_ascii=False,
                                                      allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps({'passed': report['passed'], 'checks': checks, 'report': str(destination / 'report.json')}))
    return report['passed']


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--fixture-dir', required=True)
    args = parser.parse_args()
    raise SystemExit(0 if run(args.fixture_dir) else 1)
