"""Remove only this batch's generated test bytecode after checking its Git copies."""

import hashlib
import json
from pathlib import Path
import subprocess

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]


def main():
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    records=[]
    for path in sorted(HERE.rglob('*.pyc')):
        resolved=path.resolve()
        resolved.relative_to(HERE.resolve())
        raw=resolved.read_bytes()
        relative=resolved.relative_to(ROOT).as_posix()
        prior=subprocess.run(['git','show',head+':'+relative],cwd=ROOT,capture_output=True)
        records.append(dict(path=str(resolved),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest(),
            prior_git=head,prior_git_path=relative,prior_git_bytes_equal=prior.returncode==0 and prior.stdout==raw))
        resolved.unlink()
    result=dict(schema='source-region-final-generated-cache-cleanup-v1',files=records,
        scope='Only generated test bytecode below this batch namespace. Runtime originals remain preserved.',actual_operations_added=0)
    with (HERE/'FINAL_CACHE_CLEANUP.json').open('x',encoding='utf8',newline='\n') as stream:
        json.dump(result,stream,sort_keys=True,indent=2)
        stream.write('\n')
    print(json.dumps(dict(removed=len(records),git_copies_equal=all(row['prior_git_bytes_equal'] for row in records))))


if __name__=='__main__':
    main()
