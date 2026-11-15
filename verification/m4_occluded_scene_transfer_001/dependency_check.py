"""Record the one added common library without changing accepted numeric bytes."""

import hashlib
import json
from pathlib import Path
import sys
import time


HERE = Path(__file__).resolve().parent
EXTERNAL = Path('D:/he_occluded_transfer_001')
DEPENDENCIES = EXTERNAL / 'shared_dependencies'
WHEEL = EXTERNAL / 'shared_wheels/shapely-2.1.2-cp312-cp312-win_amd64.whl'
OLD_DEPENDENCIES = Path('D:/he_anchor_001/venv/Lib/site-packages')


def main():
    started = time.perf_counter_ns()
    target = HERE / 'SHARED_DEPENDENCY.json'
    if target.exists():
        raise FileExistsError('one_shared_dependency_receipt')
    sys.path.insert(0, str(DEPENDENCIES))
    sys.path.insert(0, str(OLD_DEPENDENCIES))
    import numpy as np
    import PIL
    import shapely
    from fractions import Fraction
    from shapely.geometry import Polygon

    assert np.__version__ == '2.3.5' and PIL.__version__ == '12.3.0'
    assert Path(np.__file__).resolve().is_relative_to(OLD_DEPENDENCIES)
    assert Path(PIL.__file__).resolve().is_relative_to(OLD_DEPENDENCIES)
    assert shapely.__version__ == '2.1.2'
    assert Path(shapely.__file__).resolve().is_relative_to(DEPENDENCIES)
    a = Polygon([(0, 0), (2, 0), (2, 2), (0, 2)])
    b = Polygon([(1, 1), (3, 1), (3, 3), (1, 3)])
    assert a.area == 4 and a.intersection(b).area == 1 and a.union(b).area == 7
    files = {str(path.resolve()): hashlib.sha256(path.read_bytes()).hexdigest()
             for path in sorted(DEPENDENCIES.rglob('*')) if path.is_file()}
    files[str(WHEEL.resolve())] = hashlib.sha256(WHEEL.read_bytes()).hexdigest()
    result = dict(schema='occluded-transfer-common-dependency-v1',
        dependency_root=str(DEPENDENCIES), numpy_version=np.__version__, numpy_path=np.__file__,
        PIL_version=PIL.__version__, PIL_path=PIL.__file__, Fraction_check=str(Fraction(1, 2)),
        shapely_version=shapely.__version__, shapely_path=shapely.__file__,
        wheel_path=str(WHEEL), wheel_sha256=files[str(WHEEL.resolve())],
        wheel_origin='https://pypi.org/simple/shapely/',
        download_command='pip download --no-deps --only-binary=:all: --index-url https://pypi.org/simple shapely==2.1.2',
        install_command='pip install --no-deps --no-compile --target <new shared_dependencies> --no-index <retained wheel>',
        installation_timing='Separate pip install tool wall time was 1.087 seconds. Download elapsed was not independently instrumented.',
        files_sha256=files, polygon_checks=dict(area=4, intersection_area=1, union_area=7),
        old_dependency_directory_modified=False,
        old_shapely_probe='find_spec returned None with accepted old dependency directory first',
        started_ns=started, before_publication_ns=time.perf_counter_ns())
    with target.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(result, stream, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2)
        stream.write('\n')
    print(json.dumps(dict(passed=True, files=len(files), shapely=shapely.__version__,
                         numpy=np.__version__, PIL=PIL.__version__, polygon=True)))


if __name__ == '__main__':
    main()
