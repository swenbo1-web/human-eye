"""Freeze the accepted runtime from Git, never from another mutable checkout."""
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
COMMIT = '081252633cdf49b5b35c4dfa33845c7d05438870'

def main():
    identity = json.loads((ROOT/'verification/arch_integration_001/common_identity.json').read_text(encoding='utf8'))
    folder = HERE/'baseline_sources'
    folder.mkdir(exist_ok=False)
    members = identity['source_files']
    assert len(members) == 133
    rows = []
    with zipfile.ZipFile(HERE/'baseline_sources.zip', 'x', compression=zipfile.ZIP_DEFLATED) as archive:
        for name in [row['path'] for row in members] + ['pyproject.toml']:
            data = subprocess.check_output(['git','show',COMMIT+':'+name], cwd=ROOT)
            sha = hashlib.sha256(data).hexdigest()
            match = next((row for row in members if row['path']==name), None)
            if match is not None: assert sha == match['sha256'], name
            path = folder/name
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_bytes(data)
            archive.writestr(name,data)
            rows.append({'path':name,'sha256':sha,'bytes':len(data)})
    record = {'product_commit':COMMIT,'runtime_identity':identity,'source_kind':'git blobs',
        'member_count':len(rows),'members':rows,
        'archive_sha256':hashlib.sha256((HERE/'baseline_sources.zip').read_bytes()).hexdigest()}
    (HERE/'baseline_freeze.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf8')
    print(json.dumps({'members':len(rows),'runtime_source_sha256':identity['source_sha256'],
                      'archive_sha256':record['archive_sha256']}))

if __name__=='__main__': main()
