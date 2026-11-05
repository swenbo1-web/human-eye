"""Root review: replay a fixed cross-family subset without fitting or selecting models."""

from argparse import ArgumentParser
from hashlib import sha256, file_digest
import json
import os
from pathlib import Path
import subprocess
import sys
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SEEDS = (20261105, 79463, 310519)
VIEW_ORDINALS = (0, 1, 20, 21, 40, 41)
ACTION_ORDINALS = (0, 2, 20, 22, 40, 42)


def identity(path):
    with path.open('rb') as stream:
        return {'sha256': file_digest(stream, 'sha256').hexdigest(), 'bytes': path.stat().st_size}


def write(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def native(out, controls=False):
    import bpy
    from human_eye_fast.raycast_saccade_gpu import VGRenderer
    from verification.cf_experiment import (Inputs, ViewAuditEpisode, _action_data, _env, evidence,
                                            _control_view, _prequential, _visual_negatives)
    from verification.cf_fixtures import build_fixture
    from verification.cf_native import ViewEpisode, materialize
    from verification.cf_visual_acceptance import PillowWorker

    assert bpy.app.background
    inputs = Inputs(out)
    results = []
    renderer = VGRenderer()
    try:
        with PillowWorker(Path(r'D:\human eye\venv\Scripts\python.exe')) as scorer, evidence(out) as (media, raw):
            for seed in SEEDS:
                base = ROOT / 'artifacts/cf/formal_001' / str(seed)
                specs = inputs.specs(base / 'specs/manifest-evaluation.json', seed, 'evaluation')
                frozen = inputs.frozen(base / 'seal/frozen.npz')
                summary_path = base / 'evaluation/summary.json'
                if not summary_path.exists():
                    summary_path = base / 'evaluation-completion/summary.json'
                original = json.loads(inputs.track(summary_path))
                session, shuffled = frozen.session(), frozen.session(view='shuffle', action='shuffle')
                model_before = (session.view_head.weights.copy(), session.action_head.weights.copy())
                if controls:
                    control = inputs.specs(base / 'specs/manifest-control.json', seed, 'control')
                    diagnostic = inputs.specs(base / 'specs/manifest-diagnostic.json', seed, 'diagnostic')
                    control_rows = [_control_view(spec, renderer, scorer, media, raw) for spec in control['V']]
                    control_rows += [_action_data(spec, renderer, media, raw, constant=frozen.reference)[0]
                                     for spec in control['A']]
                    diagnostic_rows = [_action_data(spec, renderer, media, raw, model=session,
                                                     constant=frozen.reference)[0] for spec in diagnostic['A']]

                    def comparable(item):
                        if isinstance(item, dict):
                            return {key: comparable(value) for key, value in item.items()
                                    if key not in ('score_ns', 'elapsed_ns')}
                        if isinstance(item, (list, tuple)):
                            return [comparable(value) for value in item]
                        return item

                    assert comparable(control_rows) == comparable(original['controls'])
                    assert comparable(diagnostic_rows) == comparable(original['diagnostic'])
                    for row in control_rows + diagnostic_rows:
                        assert row['success']
                    seq = out / f'{seed}-prequential'
                    seq.mkdir()
                    sequential = _prequential(specs['V'], specs['A'], renderer, scorer, seq, frozen)
                    assert comparable(sequential) == comparable(original['prequential'])
                    negatives = _visual_negatives(renderer, scorer, out / f'{seed}-visual-negatives')
                    assert len(negatives) == 9
                    for name, item in negatives.items():
                        if name in ('missing_direction', 'duplicate_direction', 'out_of_range_direction'):
                            assert item == {'rejected': True}
                        else:
                            assert not item['passed']
                    results.append({'seed': seed, 'controls': len(control_rows), 'diagnostics': len(diagnostic_rows),
                                    'prequential': len(sequential), 'visual_negatives': len(negatives), 'passed': True})
                    session.close()
                    shuffled.close()
                    print(f'Root continuation review seed {seed}: all controls/diagnostics/prequential exact', flush=True)
                    continue
                with ZipFile(base / 'evaluation/media.zip') as previous:
                    for index in VIEW_ORDINALS:
                        spec = specs['V'][index]
                        with materialize(build_fixture(spec)) as host, host.context():
                            episode = ViewAuditEpisode(ViewEpisode(host), renderer)
                            for arm in ('F', 'R', 'L'):
                                row, image, _ = episode.arm(arm, None if arm == 'F' else session, scorer, media, raw)
                                old = original['views'][arm][index]
                                assert row['id'] == old['id']
                                for field in ('rays', 'success', 'safe', 'candidate', 'selected_rays',
                                              'native_stop', 'png_sha256', 'frame_id', 'targets', 'witness'):
                                    assert row[field] == old[field], (seed, index, arm, field)
                                assert row['success']
                                assert image.png == previous.read(f'{spec.episode_id}/{arm}.png')
                                results.append({'seed': seed, 'head': 'V', 'ordinal': index, 'arm': arm,
                                                'id': row['id'], 'rays': row['rays'], 'passed': True})
                    for index in ACTION_ORDINALS:
                        spec = specs['A'][index]
                        row, result = _action_data(spec, renderer, media, raw, model=session,
                                                   constant=frozen.reference, shuffle=shuffled,
                                                   negatives=(index == 0))
                        old = original['actions'][index]
                        for field in ('id', 'measured_delta_m', 'delta_budget_m', 'comparison', 'contact',
                                      'control_before', 'control_after', 'distance_before_m',
                                      'distance_after_m', 'feature_scale_m', 'success'):
                            assert row[field] == old[field], (seed, index, field, row[field], old[field])
                        for name, payload in (('before.json', result.before_payload), ('after.json', result.after_payload),
                                              ('before.png', result.before_png.png), ('after.png', result.after_png.png)):
                            assert payload == previous.read(f'{spec.episode_id}/{name}'), (seed, index, name)
                        results.append({'seed': seed, 'head': 'A', 'ordinal': index, 'id': row['id'],
                                        'predicted_delta_m': result.prediction,
                                        'actual_delta_m': row['measured_delta_m'], 'passed': True})
                assert session.views.writes == session.actions.writes == 240
                assert all((old == head.weights).all() for old, head in zip(
                    model_before, (session.view_head, session.action_head)))
                session.close()
                shuffled.close()
                print(f'Root replay seed {seed}: 18 view arms + 6 actions exact', flush=True)
    finally:
        renderer.close()
    write(out / 'result.json', {'status': 'PASS', 'environment': _env(), 'cases': results,
                              'view_ordinals': VIEW_ORDINALS, 'action_ordinals': ACTION_ORDINALS,
                              'scope': 'All controls/diagnostics/prequential replay' if controls else
                                       'Fixed subset replay, no learning or performance inference'})


def launch(out, controls=False):
    from verification.benchmark_cerebellar_flash import BLENDER, THREADS, _contents, _check_frozen
    out.mkdir(parents=True, exist_ok=False)
    sources = _contents()
    sources[Path(__file__).relative_to(ROOT).as_posix()] = Path(__file__).read_bytes()
    _check_frozen(sources)
    source_ids = {name: {'sha256': sha256(data).hexdigest(), 'bytes': len(data)} for name, data in sources.items()}
    write(out / 'source.json', source_ids)
    with ZipFile(out / 'source.zip', 'w', compression=ZIP_DEFLATED) as archive:
        for name, data in sources.items():
            archive.writestr(name, data)
    input_paths = []
    for seed in SEEDS:
        base = ROOT / 'artifacts/cf/formal_001' / str(seed)
        input_paths += [base / 'specs/manifest-evaluation.json', base / 'seal/frozen.npz',
                        base / 'seal/frozen.json', base / 'evaluation/media.zip']
        summary = base / 'evaluation/summary.json'
        input_paths.append(summary if summary.exists() else base / 'evaluation-completion/summary.json')
        if controls:
            input_paths += [base / 'specs/manifest-control.json', base / 'specs/manifest-diagnostic.json']
    input_ids = {str(path): identity(path) for path in input_paths}
    cmd = [str(BLENDER), '--background', '--factory-startup', '--disable-autoexec', '--threads', '1',
           '--python-exit-code', '10', '--python', str(Path(__file__).resolve()), '--', '--native', '--out', str(out)]
    if controls:
        cmd.append('--controls')
    write(out / 'launch.json', {'argv': cmd, 'sources': source_ids, 'inputs': input_ids,
                              'view_ordinals': VIEW_ORDINALS, 'action_ordinals': ACTION_ORDINALS})
    with (out / 'worker.log').open('wb') as log:
        proc = subprocess.run(cmd, cwd=ROOT, env={**os.environ, **THREADS}, stdout=log, stderr=subprocess.STDOUT,
                              creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    stable_source = all(identity(ROOT / name) == expected for name, expected in source_ids.items())
    stable_inputs = all(identity(Path(path)) == expected for path, expected in input_ids.items())
    write(out / 'process.json', {'exit_code': proc.returncode, 'sources_stable': stable_source,
                                'inputs_stable': stable_inputs,
                                'outputs': {p.relative_to(out).as_posix(): identity(p) for p in out.rglob('*') if p.is_file()}})
    assert proc.returncode == 0 and stable_source and stable_inputs
    print((out / 'worker.log').read_text(encoding='utf-8'))
    print('ROOT CF REPLAY PASS', out)


if __name__ == '__main__':
    parser = ArgumentParser()
    parser.add_argument('--native', action='store_true')
    parser.add_argument('--controls', action='store_true')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else None)
    (native if args.native else launch)(args.out.resolve(), args.controls)
