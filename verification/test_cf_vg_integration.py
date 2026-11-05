"""Native regression of the CF direction-order hook against accepted VG.

This is integration validation, not a new VG optimization round. Run in a fresh
background Blender: --python this-file -- NEW_OUTPUT_DIRECTORY.
"""
from copy import deepcopy
from dataclasses import replace
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
from time import perf_counter_ns

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True
BASELINE = ROOT / 'verification/baselines/vg_before_cf.py'
RUNTIME = ROOT / 'human_eye_fast/raycast_saccade_gpu.py'
OLD_SHA = '5349300f26c38f6e0ccbdf4a08109969df190b74328dabcdef3eded72a5f0528'
WARMUPS, SAMPLES = 5, 31
TAIL_LIMIT = 1.05


def sha(data):
    return hashlib.sha256(data).hexdigest()


def metadata(observation):
    result = deepcopy(observation.metadata)
    for view in result['views'].values():
        view['rna'].pop('name', None)
    return result


def load_baseline():
    spec = importlib.util.spec_from_file_location('_vg_before_cf', BASELINE)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class Rays:
    def __init__(self, native):
        self.native, self.count = native, 0

    def ray_cast(self, *args):
        self.count += 1
        return self.native.ray_cast(*args)


def observe(renderer, prepared, fixture, **kwargs):
    return renderer.observe(prepared, fixture.witness, target_ids=fixture.target_ids,
                            frame_id=fixture.frame_id, scale_length=fixture.scale_length,
                            mode=fixture.mode, **kwargs)


def main(out):
    import bpy
    import gpu
    import numpy as np
    from human_eye_fast import raycast_saccade_gpu as current
    from verification.vg_fixtures import build_fixture, build_no_gap_fixture

    assert bpy.app.background and not out.exists()
    assert sha(BASELINE.read_bytes()) == OLD_SHA
    out.mkdir(parents=True)
    source_paths = (BASELINE, RUNTIME, Path(__file__), ROOT / 'verification/vg_fixtures.py',
                    ROOT / 'human_eye_fast/fast_bvh_clearance.py')
    sources = {}
    for path in source_paths:
        name = path.relative_to(ROOT).as_posix()
        data = path.read_bytes()
        saved = out / 'source' / name
        saved.parent.mkdir(parents=True, exist_ok=True)
        saved.write_bytes(data)
        sources[name] = sha(data)
    original = load_baseline()
    renderers = {'A': original.VGRenderer(), 'R': current.VGRenderer()}
    fixtures, prepared, quality, warmups, samples = [], [], [], [], []
    controls = []
    try:
        for scene in range(24):
            fixture = build_fixture(scene)
            fixtures.append(fixture)
            resources = {m: renderer.prepare(fixture.meshes) for m, renderer in renderers.items()}
            prepared.append(resources)
            a = observe(renderers['A'], resources['A'], fixture)
            r = observe(renderers['R'], resources['R'], fixture)
            ident = observe(renderers['R'], resources['R'], fixture,
                            rank_directions=lambda canonical: range(len(canonical)))
            assert a.png == r.png == ident.png
            assert metadata(a) == metadata(r) == metadata(ident)
            folder = out / f'case-{scene:02}'
            folder.mkdir()
            for method, value in (('A', a), ('R', r), ('identity', ident)):
                (folder / f'{method}.png').write_bytes(value.png)
            rays = Rays(resources['R'].rays)
            callback_calls, canonical_rows = [], []

            def reverse(canonical):
                assert rays.count == 0
                assert len(canonical) == 16
                rows = [list(d) for d in canonical]
                assert len(set(map(tuple, rows))) == 16
                callback_calls.append(1)
                canonical_rows.extend(rows)
                return range(15, -1, -1)

            reverse_observation = observe(renderers['R'], replace(resources['R'], rays=rays),
                                          fixture, rank_directions=reverse)
            selection = reverse_observation.metadata['selection']
            probes = selection['probes']
            assert len(callback_calls) == 1
            assert rays.count == selection['ray_count'] == sum(p['ray_count'] for p in probes)
            assert [p['direction'] for p in probes] == list(reversed(canonical_rows))[:len(probes)]
            success = [p for p in probes if p['target_support'] == 2]
            if success:
                assert len(success) == 1 and success[0] is probes[-1]
                expected = success[0]
            else:
                assert len(probes) == 16
                expected = max(probes, key=lambda p: (p['target_support'], p['aperture_taps']))
            assert selection['direction'] == expected['direction']
            (folder / 'reverse.png').write_bytes(reverse_observation.png)
            quality.append({'scene': scene, 'family': fixture.family, 'mode': fixture.mode,
                            'same_png_bytes': True, 'same_metadata_except_camera_name': True,
                            'old_new_identity_sha256': sha(a.png), 'canonical': canonical_rows,
                            'default_selection': a.metadata['selection'],
                            'reverse_selection': selection, 'actual_reverse_rays': rays.count,
                            'rank_called_once_before_first_ray': True})
        # Timers cover complete observe through GPU readback/PNG bytes; no trace,
        # audit image, comparisons or hashes are inside the measured interval.
        for sequence in range(WARMUPS + SAMPLES):
            order = ('A', 'R') if sequence % 2 == 0 else ('R', 'A')
            result, elapsed = {}, {}
            for method in order:
                start = perf_counter_ns()
                result[method] = [observe(renderers[method], resources[method], fixture)
                                  for fixture, resources in zip(fixtures, prepared)]
                elapsed[method] = perf_counter_ns() - start
            hashes = []
            for a, r in zip(result['A'], result['R']):
                assert a.png == r.png and metadata(a) == metadata(r)
                hashes.append(sha(a.png))
            row = {'sequence': sequence, 'order': order, 'elapsed_ns': elapsed,
                   'A_R_equal_png_sha256': hashes, 'metadata_equal': True}
            (warmups if sequence < WARMUPS else samples).append(row)
        for kind in ('CONTACT', 'INTERSECTION'):
            fixture = build_no_gap_fixture(kind)
            try:
                resources = {m: renderer.prepare(fixture.meshes) for m, renderer in renderers.items()}

                def forbidden(_):
                    raise AssertionError('Zero-gap observation must not invoke positive-gap ranker')

                a = observe(renderers['A'], resources['A'], fixture, relation=kind)
                r = observe(renderers['R'], resources['R'], fixture, relation=kind, rank_directions=forbidden)
                assert a.png == r.png and metadata(a) == metadata(r)
                controls.append({'kind': kind, 'same_png_sha256': sha(a.png),
                                 'metadata_equal': True, 'callback_bypassed': True})
            finally:
                fixture.close()
        values = {m: [r['elapsed_ns'][m] for r in samples] for m in ('A', 'R')}
        stats = {m: {'median_ns': float(np.median(v)), 'p95_ns': float(np.quantile(v, .95, method='linear'))}
                 for m, v in values.items()}
        median_ratio = stats['R']['median_ns'] / stats['A']['median_ns']
        tail_ratio = stats['R']['p95_ns'] / stats['A']['p95_ns']
        source_after = {name: sha((ROOT / name).read_bytes()) for name in sources}
        assert sources == source_after
        report = {'scope': 'One-process CF hook integration regression, not new VG optimization or CF benefit proof',
                  'pid': os.getpid(), 'blender': bpy.app.version_string, 'python': sys.version,
                  'gpu': {'vendor': gpu.platform.vendor_get(), 'renderer': gpu.platform.renderer_get(),
                          'version': gpu.platform.version_get()},
                  'source_before': sources, 'source_after': source_after,
                  'warmup_count': WARMUPS, 'paired_count': SAMPLES, 'scenes_per_batch': 24,
                  'timing_boundary': 'Ready captured geometry and independent GPU preparations to completed 24 PNG observations; scene build/capture/prepare/trace/audit/hash/I/O excluded equally',
                  'warmups': warmups, 'samples': samples, 'quality': quality, 'controls': controls,
                  'statistics': stats, 'R_A_median_ratio': median_ratio, 'R_A_p95_ratio': tail_ratio,
                  'predeclared_median_and_p95_ratio_limit': TAIL_LIMIT,
                  'passed': median_ratio <= TAIL_LIMIT and tail_ratio <= TAIL_LIMIT}
        (out / 'result.json').write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
        print(json.dumps({k: report[k] for k in ('passed', 'statistics', 'R_A_median_ratio', 'R_A_p95_ratio')}))
        return int(not report['passed'])
    finally:
        prepared.clear()
        for renderer in renderers.values():
            renderer.close()
        for fixture in reversed(fixtures):
            fixture.close()


if __name__ == '__main__':
    output = Path(sys.argv[sys.argv.index('--') + 1]).resolve()
    try:
        raise SystemExit(main(output))
    except Exception:
        import traceback
        if output.exists():
            (output / 'exception.txt').write_text(traceback.format_exc(), encoding='utf-8')
        raise
