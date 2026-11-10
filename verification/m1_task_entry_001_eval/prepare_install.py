"""Build and install only the fixed evaluation candidate, without activation."""
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import time

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
COMMIT = '7411ac7aa9338f17355ffe5cdf4df113ce862aed'
CANONICAL = '0005ab437c8f330ed277bd49133348389fe7222bda3087f16450dce55ec9c05a'
VERSION = '9.7.2+20261110.m1.eval.r1'
PYTHON = Path('D:/hefe/.human-eye/releases/9.7.2+20261028.support.discovery.r1/.venv/Scripts/python.exe')
INSTALLER = Path('D:/hefe/verification/fixes/20261110_local_upgrade/INSTALL_CANDIDATE.py')
sha = lambda raw: hashlib.sha256(raw).hexdigest()


def save(path, value):
    with path.open('x', encoding='utf8', newline='\n') as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False)
        stream.write('\n')


def command(folder, label, argv):
    start = time.perf_counter_ns()
    result = subprocess.run([str(v) for v in argv], cwd=HERE, capture_output=True,
        timeout=90, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    (folder/(label+'.stdout.json')).write_bytes(result.stdout)
    (folder/(label+'.stderr.txt')).write_bytes(result.stderr)
    save(folder/(label+'.COMMAND.json'), {'argv': [str(v) for v in argv],
        'started_ns': start, 'elapsed_ns': time.perf_counter_ns()-start,
        'exit_code': result.returncode, 'stdout_sha256': sha(result.stdout),
        'stderr_sha256': sha(result.stderr)})
    if result.returncode:
        raise RuntimeError(label+' failed; original outputs retained')
    return json.loads(result.stdout)


def main():
    folder = HERE/'installation'
    folder.mkdir(exist_ok=False)
    binding = json.loads((ROOT/'verification/m1_task_entry_001_optimize/REGRESSION_RUNNER_BINDING.json').read_bytes())
    assert binding['candidate_source_sha256'] == CANONICAL
    names = sorted({r['path'] for r in binding['files']} | {
        'README.md', 'pyproject.toml', 'human_eye_plugin/plugin.json',
        'human_eye_plugin/mcp_config.json', 'verification/build_candidate_release.py',
        'examples/agents/target_runtime_entry.py', 'examples/agents/installed_release.py'})
    raw = subprocess.check_output(['git', '-C', str(ROOT), 'archive', '--format=tar', COMMIT, '--', *names])
    source = folder/'source_7411'
    source.mkdir()
    members = []
    with tarfile.open(fileobj=io.BytesIO(raw), mode='r:') as archive:
        for member in archive.getmembers():
            if not member.isfile():
                continue
            assert member.name in names
            value = archive.extractfile(member).read()
            target = source/member.name
            assert target.resolve().is_relative_to(source.resolve())
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(value)
            assert target.read_bytes() == (ROOT/member.name).read_bytes()
            members.append({'path': member.name, 'sha256': sha(value), 'bytes': len(value)})
    assert {m['path'] for m in members} == set(names)
    save(folder/'FIXED_BUILD_INPUTS.json', {'commit': COMMIT, 'files': members,
        'source_sha256': CANONICAL, 'source_count': 137, 'default_activation_changed': False})
    installer_raw = INSTALLER.read_bytes()
    copied = folder/'INSTALL_CANDIDATE.py'
    copied.write_bytes(installer_raw)
    save(folder/'INSTALLER_PROVENANCE.json', {'original': str(INSTALLER),
        'sha256': sha(installer_raw), 'bytes_unchanged': True,
        'purpose': 'Existing isolated installer only; no default configuration or owned-reference activation'})
    bundle = folder/'bundle'
    build = command(folder, 'BUILD', [PYTHON, '-I', '-B', source/'verification/build_candidate_release.py',
        '--output', bundle, '--version', VERSION])
    release = ROOT/'.human-eye/releases'/VERSION
    installed = command(folder, 'INSTALL', [PYTHON, '-I', '-B', copied,
        '--source-root', source, '--git-repository', ROOT, '--commit', COMMIT,
        '--bundle', bundle, '--version', VERSION, '--release-dir', release,
        '--dependency-python', PYTHON, '--evidence-dir', folder/'receipt'])
    assert installed['source_sha256'] == CANONICAL and installed['source_count'] == 137
    assert installed['source_commit_wheel_install_equal'] and not installed['default_activation_changed']
    save(folder/'READY.json', {'status': 'isolated installation ready for local no-model preflight',
        'commit': COMMIT, 'source_sha256': CANONICAL, 'source_count': 137,
        'entry': installed['entry'], 'install_root': str(release/'site-packages'),
        'dependency_python': str(PYTHON), 'release': str(release),
        'version': VERSION, 'wheel_sha256': installed['wheel_sha256'],
        'launcher_sha256': installed['launcher_sha256'], 'binding_sha256': installed['binding_sha256'],
        'no_default_activation': True, 'model_calls': 0})
    print(json.dumps({'ready': True, 'entry': installed['entry'], 'source_sha256': CANONICAL}))


if __name__ == '__main__':
    main()
