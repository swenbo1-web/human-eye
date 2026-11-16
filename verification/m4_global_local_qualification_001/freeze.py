"""Write-once source, input and independent-answer freeze before any qualification."""

import hashlib
import json
from pathlib import Path
import time


HERE = Path(__file__).resolve().parent


def main():
    for required in ('fixture/ASSET_BINDING.json', 'fixture/GEOMETRY.json', 'REQUESTS.json',
                     'oracle/STATIC_QUALIFICATION.json', 'checks/saved_frames.py'):
        if not (HERE / required).is_file():
            raise ValueError('freeze_input_missing/' + required)
    rows = []
    for path in sorted(HERE.rglob('*')):
        if not path.is_file() or '__pycache__' in path.parts or path.name == 'FROZEN.json':
            continue
        raw = path.read_bytes()
        rows.append(dict(relative=path.relative_to(HERE).as_posix(), bytes=len(raw),
                         sha256=hashlib.sha256(raw).hexdigest()))
    result = dict(schema='m4-global-local-frozen-v1', frozen_ns=time.perf_counter_ns(), files=rows,
                  actual_qualification_starts=0, actual_qualification_rasters=0, model_consumers=0,
                  scope='One fixed fixture, independent static qualification, task, public requests and saved-only checker. Fixture construction is separately recorded.')
    with (HERE / 'FROZEN.json').open('x', encoding='utf8', newline='\n') as stream:
        json.dump(result, stream, sort_keys=True, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps(dict(frozen_files=len(rows), qualification_starts=0)))


if __name__ == '__main__':
    main()
