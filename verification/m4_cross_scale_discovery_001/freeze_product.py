"""Freeze committed runtime sources, direct assets and this generation's caller."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]


def pin(path):
    raw=path.read_bytes()
    return dict(path=str(path),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--version',choices=('R0','R1'),required=True)
    args=parser.parse_args()
    old=json.loads((HERE.with_name('m4_global_local_qualification_001')/'B_RUN_BINDING.json').read_bytes())
    names=sorted({row['path'] for row in old['source_manifest']}|{'human_eye_plugin/active_observation_region_task.py'})
    manifest=[dict(path=name,sha256=hashlib.sha256((ROOT/name).read_bytes()).hexdigest()) for name in names]
    value=dict(schema='m4-cross-scale-source-freeze-v1',version=args.version,frozen_ns=time.perf_counter_ns(),
        preparation_git=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        runtime_manifest=manifest,harness_pins=[pin(path) for path in sorted((HERE/'harness').rglob('*.py'))],
        oracle_pins=[pin(path) for path in sorted((HERE/'oracle').rglob('*')) if path.is_file() and '__pycache__' not in path.parts],
        task=pin(HERE/'REQUESTS.json'),oracle=pin(HERE/'oracle/EXPECTATIONS.json'),
        asset=pin(Path('D:/he_m4_global_local_001/fixture/main.blend')),
        runtime_source_count=len(manifest),new_model_consumers=0,new_paid_API_calls=0)
    with (HERE/('SOURCE_FREEZE_'+args.version+'.json')).open('x',encoding='utf8',newline='\n') as stream:
        json.dump(value,stream,sort_keys=True,indent=2)
        stream.write('\n')
    print(json.dumps(dict(version=args.version,sources=len(manifest))))


if __name__=='__main__':
    main()
