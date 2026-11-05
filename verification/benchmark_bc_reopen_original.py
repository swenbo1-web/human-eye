"""Run the unchanged original BC benefit protocol against an isolated candidate.

Both methods use the candidate narrow phase; the full-pair baseline preserves
the original bounded batching and exact-zero exit. Production is not replaced.
"""

import argparse
from hashlib import sha256
import importlib.util
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from verification import benchmark_fast_bvh_clearance as original


def main():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--candidate', type=Path)
    args, remaining = parser.parse_known_args()
    # Children inherit the selected path; there is no alternate runtime route.
    path = args.candidate or Path(os.environ['BC_REOPEN_CANDIDATE_PATH'])
    path = path.resolve()
    os.environ['BC_REOPEN_CANDIDATE_PATH'] = str(path)
    spec = importlib.util.spec_from_file_location('_bc_original_protocol_candidate', path)
    api = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = api
    spec.loader.exec_module(api)
    original_source = Path(original.__file__).resolve()
    for name in ('SurfaceDistance', 'SurfaceIndex', '_closest_pairs',
                 '_prepare_triangles', 'surface_distance'):
        setattr(original, name, getattr(api, name))
    def sources():
        return {str(item.relative_to(ROOT)): sha256(item.read_bytes()).hexdigest()
                for item in (Path(__file__).resolve(), original_source, path)}
    original._source_digests = sources
    # The original launcher starts this same adapter in each fresh process.
    original.__file__ = __file__
    sys.argv = [__file__, *remaining]
    return original.main()


if __name__ == '__main__':
    raise SystemExit(main())
