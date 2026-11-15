"""Prepare pinned official source for the unchanged preflight; no model execution."""
import hashlib
import json
from pathlib import Path
import urllib.request

HERE = Path(__file__).resolve().parent
tree = json.loads((HERE / 'UPSTREAM_TREE.json').read_bytes())
report = json.loads((HERE / 'PREFLIGHT.json').read_bytes())
index = {item['path']: item for item in tree['files']}
payload, checked = [], []
for record in report['source_files']:
    path = record['path']
    local = HERE / 'private' / 'pointfilter' / path
    if local.exists():
        data = local.read_bytes()
        acquisition = 'existing_local_bytes'
    else:
        url = f"https://raw.githubusercontent.com/{tree['repository']}/{tree['commit']}/{path}"
        with urllib.request.urlopen(url, timeout=45) as response:
            data = response.read(index[path]['size'] + 1)
        acquisition = url
    blob = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
    digest = hashlib.sha256(data).hexdigest()
    assert len(data) == index[path]['size'] == record['bytes']
    assert blob == index[path]['sha'] == record['git_blob']
    assert digest == record['sha256']
    payload.append({'path': path, 'content': data.decode('utf-8')})
    checked.append({'path': path, 'bytes': len(data), 'sha256': digest, 'git_blob': blob, 'acquisition': acquisition})
(HERE / 'source_payload.json').write_bytes((json.dumps({'files': payload}, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))
result = {'repository': tree['repository'], 'commit': tree['commit'], 'checked': checked,
          'model_executions': 0, 'quality_cases': 0, 'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
          'frozen_preflight_script_sha256': hashlib.sha256((HERE / 'preflight.py').read_bytes()).hexdigest()}
(HERE / 'SOURCE_CHECK.json').write_bytes((json.dumps(result, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))
print(json.dumps({'source_files_checked': len(checked), 'network_downloads': sum(x['acquisition'] != 'existing_local_bytes' for x in checked), 'model_executions': 0}))
