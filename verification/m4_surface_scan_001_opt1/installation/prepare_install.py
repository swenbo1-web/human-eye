"""Build and install a committed scan candidate in a fresh isolated release."""
from __future__ import annotations

import argparse
import ast
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import tarfile
import time


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PYTHON = Path('D:/hefe/.human-eye/releases/9.7.2+20261028.support.discovery.r1/.venv/Scripts/python.exe')
INSTALLER = Path('D:/hefe/verification/fixes/20261110_local_upgrade/INSTALL_CANDIDATE.py')


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def save(path, value):
    with path.open('x', encoding='utf8', newline='\n') as stream:
        json.dump(value, stream, sort_keys=True, indent=2)
        stream.write('\n')


def command(folder, label, argv):
    record = {'argv': [str(value) for value in argv],
              'started_ns': time.perf_counter_ns(),
              'started_utc': datetime.now(timezone.utc).isoformat(),
              'timeout_s': 120, 'pid': None, 'returncode': None, 'timed_out': False}
    output = error = b''
    process = None
    try:
        process = subprocess.Popen(record['argv'], cwd=HERE, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE,
                                   creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        record['pid'] = process.pid
        try:
            output, error = process.communicate(timeout=120)
        except subprocess.TimeoutExpired:
            record['timed_out'] = True
            stopped = subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                                     capture_output=True, timeout=10,
                                     creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            record['owned_tree_stop_returncode'] = stopped.returncode
            output, error = process.communicate(timeout=15)
        record['returncode'] = process.returncode
    finally:
        if process is not None and process.poll() is None:
            process.kill()
            output, error = process.communicate(timeout=15)
            record['returncode'] = process.returncode
        record.update(ended_ns=time.perf_counter_ns(), stdout_sha256=digest(output),
                      stderr_sha256=digest(error))
        (folder / (label + '.stdout.bin')).write_bytes(output)
        (folder / (label + '.stderr.txt')).write_bytes(error)
        save(folder / (label + '.PROCESS.json'), record)
    assert record['returncode'] == 0 and not record['timed_out'], label + ' failed'
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--commit', required=True)
    parser.add_argument('--source-sha256', required=True)
    parser.add_argument('--version', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    assert re.fullmatch('[0-9a-f]{40}', args.commit)
    assert re.fullmatch('[0-9a-f]{64}', args.source_sha256)
    assert re.fullmatch(r'[0-9]+(?:\.[0-9]+)*(?:\+[a-z0-9]+(?:\.[a-z0-9]+)*)?', args.version)
    started = time.perf_counter_ns()
    run = args.output.resolve()
    assert run.is_relative_to(HERE)
    run.mkdir(parents=True, exist_ok=False)
    protected_paths = [Path('C:/Users/Administrator/.codex/config.toml'),
                       Path('D:/hefe/.codex/config.toml'), ROOT / 'pyproject.toml',
                       ROOT / 'verification/m4_surface_scan_001/qualification/assembly.blend']
    protected = {str(path): digest(path.read_bytes()) if path.is_file() else None
                 for path in protected_paths}
    save(run / 'PROTECTED_BEFORE.json', protected)
    listed = command(run, '01_GIT_TREE', ['git', '-C', ROOT, 'ls-tree', '-r',
                                         '--name-only', args.commit]).decode().splitlines()
    source_identity = command(run, '02_IDENTITY_SOURCE', ['git', '-C', ROOT, 'show',
                              args.commit + ':human_eye_plugin/runtime_identity.py'])
    tree = ast.parse(source_identity)
    constants = {node.targets[0].id: ast.literal_eval(node.value) for node in tree.body
                 if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)
                 and node.targets[0].id in ('BASE_VERSION', 'IMPLEMENTATION_REVISION', '_ROOT_MODULES')}
    runtime = sorted(set(constants['_ROOT_MODULES']) | {
        name for name in listed if name.endswith('.py') and len(Path(name).parts) == 2
        and Path(name).parts[0] in ('human_eye_plugin', 'human_eye_module1_operators')})
    extras = ['README.md', 'pyproject.toml', 'human_eye_plugin/plugin.json',
              'human_eye_plugin/mcp_config.json', 'verification/build_candidate_release.py',
              'examples/agents/target_runtime_entry.py', 'examples/agents/installed_release.py']
    names = sorted(set(runtime + extras))
    raw = command(run, '03_GIT_ARCHIVE', ['git', '-C', ROOT, 'archive', '--format=tar',
                                        args.commit, '--', *names])
    source = run / ('source_' + args.commit[:8])
    source.mkdir()
    manifest = []
    with tarfile.open(fileobj=io.BytesIO(raw), mode='r:') as archive:
        for member in archive.getmembers():
            if not member.isfile():
                continue
            assert member.name in names
            value = archive.extractfile(member).read()
            target = source / member.name
            assert target.resolve().is_relative_to(source)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(value)
            assert value == (ROOT / member.name).read_bytes(), 'candidate checkout drift'
            if member.name in runtime:
                manifest.append({'path': member.name, 'sha256': digest(value)})
    manifest.sort(key=lambda row: row['path'])
    canonical = digest(json.dumps({'base_version': constants['BASE_VERSION'],
        'implementation_revision': constants['IMPLEMENTATION_REVISION'], 'files': manifest},
        sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode())
    assert len(manifest) == len(runtime) and canonical == args.source_sha256
    save(run / 'FIXED_BUILD_INPUTS.json', {'commit': args.commit, 'source_sha256': canonical,
         'source_count': len(manifest), 'manifest': manifest, 'archive_sha256': digest(raw),
         'distribution_version_external': args.version, 'source_version_constants_changed': False})
    copied = run / 'INSTALL_CANDIDATE.py'
    copied.write_bytes(INSTALLER.read_bytes())
    save(run / 'INSTALLER_PROVENANCE.json', {'original': str(INSTALLER),
         'sha256': digest(copied.read_bytes()), 'unchanged_copy': True})
    command(run, '04_BUILD', [PYTHON, '-I', '-B', '-X', 'utf8',
            source / 'verification/build_candidate_release.py', '--output', run / 'bundle',
            '--version', args.version])
    release = ROOT / '.human-eye/releases' / args.version
    installed = json.loads(command(run, '05_INSTALL', [PYTHON, '-I', '-B', '-X', 'utf8', copied,
        '--source-root', source, '--git-repository', ROOT, '--commit', args.commit,
        '--bundle', run / 'bundle', '--version', args.version, '--release-dir', release,
        '--dependency-python', PYTHON, '--evidence-dir', run / 'receipt']))
    assert installed['source_sha256'] == canonical and installed['source_count'] == len(manifest)
    assert installed['isolated_identity_passed'] and installed['source_commit_wheel_install_equal']
    assert installed['default_activation_changed'] is False
    unchanged = {name: (digest(Path(name).read_bytes()) if Path(name).is_file() else None) == before
                 for name, before in protected.items()}
    assert all(unchanged.values())
    assert all(digest((ROOT / row['path']).read_bytes()) == row['sha256'] for row in manifest)
    save(run / 'PROTECTED_AFTER.json', {'unchanged': unchanged, 'all_unchanged': True})
    ready = {'commit': args.commit, 'source_sha256': canonical, 'source_count': len(manifest),
             'version': args.version, 'entry': installed['entry'],
             'install_root': str(release / 'site-packages'), 'release': str(release),
             'dependency_python': str(PYTHON), 'wheel_sha256': installed['wheel_sha256'],
             'launcher_sha256': installed['launcher_sha256'], 'binding_sha256': installed['binding_sha256'],
             'installed_identity_passed': True, 'receipt': str(run / 'receipt/ISOLATED_INSTALL.json'),
             'fixed_inputs': str(run / 'FIXED_BUILD_INPUTS.json'), 'no_default_activation': True,
             'model_calls': 0, 'Blender_calls': 0, 'elapsed_ns': time.perf_counter_ns() - started}
    save(run / 'READY.json', ready)
    print(json.dumps(ready))


if __name__ == '__main__':
    main()
