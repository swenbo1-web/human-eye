"""Pin the accepted product, consumption wiring and quality contract."""

import argparse
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import time


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase', choices=('preparation', 'formal'), required=True)
    args = parser.parse_args()
    output = HERE / ('PREP_FROZEN.json' if args.phase == 'preparation' else 'FROZEN.json')
    if output.exists():
        raise FileExistsError('freeze already exists')
    spec = importlib.util.spec_from_file_location('_localization_static_source_list', HERE / 'launcher.py')
    launcher = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(launcher)
    plan = launcher.read(HERE / 'PLAN.json')
    sources = launcher.source_file_list(plan)
    included = [path for path in HERE.rglob('*') if path.is_file()
                and path.name not in {'FROZEN.json', 'CONTENT_MANIFEST.json'}]
    for path in included:
        if path.suffix == '.py':
            ast.parse(path.read_text(encoding='utf8'), filename=str(path))
        sources[str(path.resolve())] = sha(path)
    anchors = ROOT / 'verification/m4_active_observation_region_anchors_001'
    accepted = launcher.read(anchors / 'build/RUN_BINDING.json')
    for row in accepted['source_manifest']:
        path = ROOT / row['path']
        assert sha(path) == row['sha256']
        sources[str(path.resolve())] = row['sha256']
    rules = launcher.read(HERE / 'admin/FROZEN_SCORING.json')
    for path, wanted in rules['files_sha256'].items():
        assert sha(path) == wanted, path
        sources[path] = wanted
    if args.phase == 'formal':
        qualification = launcher.require_preparation(plan)
    else:
        qualification = None
    result = {'schema': 'region-localization-consumption-source-freeze-v1',
              'task': plan['task'], 'phase': args.phase,
              'baseline_git': plan['baseline_commit'],
              'product_source_sha256': accepted['source_sha256'],
              'files_sha256': dict(sorted(sources.items())),
              'prompt_sha256': sha(Path(plan['inputs']['prompt'])),
              'scoring_sha256': sha(HERE / 'admin/FROZEN_SCORING.json'),
              'preparation_qualification': qualification,
              'formal_sequence': plan['sequence'],
              'fixed_limits': {'slot_seconds': 450, 'tools_per_slot': 12,
                               'raster_per_slot': 6, 'preparation_raster': 8,
                               'formal_raster': 36, 'whole_raster': 44},
              'frozen_before_publication_ns': time.perf_counter_ns(),
              'scope': 'File reads, hashes and AST only. This freeze starts no actor, renderer or model.'}
    with output.open('x', encoding='utf8', newline='\n') as stream:
        json.dump(result, stream, sort_keys=True, indent=2)
        stream.write('\n')
    print(json.dumps({'phase': args.phase, 'files': len(sources), 'freeze_sha256': sha(output)}))


if __name__ == '__main__':
    main()
