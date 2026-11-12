"""Recompute both canonical identities from committed bytes and installed sources."""
import hashlib
import io
import json
from pathlib import Path
import subprocess
import zipfile


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def main():
    binding = json.loads((HERE/'engineering/run_01/INPUT_BINDINGS.json').read_bytes())
    records = {}
    for version,ready in binding['readies'].items():
        relative = ('verification/m4_surface_scan_001/CANDIDATE_SOURCE.json' if version == 'A'
                    else 'verification/m4_surface_scan_001_opt1/CANDIDATE_SOURCE.json')
        committed = subprocess.check_output(['git','show',ready['commit']+':'+relative],cwd=ROOT)
        assert committed == (ROOT/relative).read_bytes()
        identity = json.loads(committed)['identity']
        manifest = identity['source_files']
        assert len(manifest) == 138
        canonical = json.dumps(dict(base_version=identity['base_version'],
            implementation_revision=identity['implementation_revision'],files=manifest),
            sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()
        assert sha(canonical) == ready['source_sha256'] == identity['source_sha256']
        references = ''.join(ready['commit']+':'+row['path']+'\n' for row in manifest).encode()
        result = subprocess.run(['git','cat-file','--batch'],input=references,
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,cwd=ROOT,check=True)
        blobs = io.BytesIO(result.stdout)
        fixed_path = Path(ready['fixed_inputs'])
        fixed = json.loads(fixed_path.read_bytes())
        assert fixed['manifest'] == manifest
        wheels = list(fixed_path.parent.glob('bundle/*.whl'))
        assert len(wheels) == 1 and sha(wheels[0].read_bytes()) == ready['wheel_sha256']
        with zipfile.ZipFile(wheels[0]) as wheel:
            for row in manifest:
                header = blobs.readline().split()
                assert len(header) == 3 and header[1] == b'blob'
                raw = blobs.read(int(header[2]))
                assert blobs.read(1) == b'\n'
                assert sha(raw) == row['sha256']
                assert wheel.read(row['path']) == raw
                assert (Path(ready['install_root'])/row['path']).read_bytes() == raw
                if version == 'B':
                    assert (ROOT/row['path']).read_bytes() == raw
        assert blobs.read() == b''
        records[version] = dict(commit=ready['commit'],source_sha256=sha(canonical),
            runtime_files_verified=138,wheel_sha256=ready['wheel_sha256'],
            committed_candidate_record_sha256=sha(committed),commit_wheel_install_equal=True)
    assert subprocess.check_output(['git','diff','--name-only','--',
        'verification/m4_surface_scan_001','human_eye_plugin'],cwd=ROOT).strip() == b''
    result = dict(passed=True,versions=records,new_source_changes_after_freeze=False,
        original_qualification_and_initial_evidence_changed=False,
        runtime_imports=0,Blender_runs=0,business_API_calls=0)
    with (HERE/'ROOT_SOURCE_AUDIT.json').open('x',encoding='utf8',newline='\n') as stream:
        json.dump(result,stream,ensure_ascii=False,indent=2)
        stream.write('\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
