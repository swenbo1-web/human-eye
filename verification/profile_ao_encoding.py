"""Untimed acceptance-wise: locate AO encoding work on actual native facts.

Run in an independent factory-startup Blender process. Profiling changes
execution cost; none of its durations are acceptance benefit measurements.
"""

import argparse
import cProfile
from hashlib import sha256
import io
import json
from pathlib import Path
import pstats
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output-dir', required=True, type=Path)
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
    args.output_dir.mkdir(parents=True, exist_ok=False)
    from human_eye_fast.fast_affordance_out import AffordancePackage, encode, _project, _row, _CANDIDATE
    from verification.ao_fixtures import build_state
    public = args.output_dir / 'state-0'
    public.mkdir()
    packages, tasks, oracle, costs, environment = build_state(0, public)
    def work():
        for i, package in enumerate(packages):
            if i in (18, 19):
                encode(AffordancePackage((package.observations[0],)))
            encode(package)
    profiler = cProfile.Profile()
    profiler.enable()
    for _ in range(100):
        work()
    profiler.disable()
    profiler.dump_stats(str(args.output_dir / 'encoding.prof'))
    stream = io.StringIO()
    pstats.Stats(profiler, stream=stream).strip_dirs().sort_stats('cumtime').print_stats(30)
    (args.output_dir / 'profile.txt').write_text(stream.getvalue(), encoding='utf-8')
    count = {'containers': 0, 'floats': 0, 'integers': 0, 'strings': 0, 'nulls': 0}
    def walk(value):
        if isinstance(value, (list, tuple, dict)):
            count['containers'] += 1
            for item in (value.values() if isinstance(value, dict) else value):
                walk(item)
        elif isinstance(value, str): count['strings'] += 1
        elif isinstance(value, float): count['floats'] += 1
        elif isinstance(value, int): count['integers'] += 1
        elif value is None: count['nulls'] += 1
    for i, package in enumerate(packages):
        if i in (18, 19):
            walk(_project(AffordancePackage((package.observations[0],)), _row, _CANDIDATE))
        walk(_project(package, _row, _CANDIDATE))
    record = {'scope': '100 profiled full 20-task / 22-publication batches; not timing acceptance',
              'environment': environment, 'one_batch_projected_structure': count,
              'source_sha256': {name: sha256((ROOT / name).read_bytes()).hexdigest()
                               for name in ('human_eye_fast/fast_affordance_out.py', 'verification/profile_ao_encoding.py')}}
    (args.output_dir / 'profile.json').write_text(json.dumps(record, indent=2)+'\n', encoding='utf-8')
    print(stream.getvalue())


if __name__ == '__main__':
    main()
