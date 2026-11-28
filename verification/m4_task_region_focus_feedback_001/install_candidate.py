"""Build and install one wheel from the committed task-focus candidate only."""
import argparse
import importlib.util
from pathlib import Path
import subprocess
import sys
import tomllib
from zipfile import ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parent))
from runner import BLENDER, PRODUCT, PYTHON, SOURCE, WHEEL, confirm, need, pin, read, save, sha


def git(checkout, *args):
    return subprocess.check_output(['git', '-C', str(checkout), *args])


def install(root, checkout, candidate, baseline_path):
    baseline = read(baseline_path)
    need(baseline['passed'] and baseline['candidate_commit'] == PRODUCT
         and baseline['source_sha256'] == SOURCE and baseline['wheel']['sha256'] == WHEEL
         and baseline['runtime_sources'] == 146, 'baseline_install_not_fixed')
    for name in ('python', 'blender', 'build', 'wheel'):
        confirm(baseline[name])
    need(sys.flags.isolated and sys.dont_write_bytecode
         and pin(sys.executable) == baseline['python'] and baseline['python']['sha256'] == PYTHON
         and baseline['blender']['sha256'] == BLENDER, 'wrong_install_interpreter')
    commit, parent = git(checkout, 'rev-list', '--parents', '-n', '1', candidate).decode().split()
    need(parent == PRODUCT and commit != PRODUCT and len(commit) == 40, 'candidate_not_direct_child')
    original_manifest = {row['path']: row['sha256'] for row in baseline['source_manifest']}
    allowed = {
        'human_eye_plugin/live_service.py', 'human_eye_plugin/live_spatial_mcp.py',
        'human_eye_plugin/observation_focus.py', 'human_eye_plugin/query_policy.py',
        'human_eye_plugin/source_region.py',
    }
    changed = set(git(checkout, 'diff', '--name-only', '-z', parent, commit).decode().rstrip('\0').split('\0'))
    need(changed and changed <= allowed and changed <= original_manifest.keys(),
         'candidate_contains_out_of_scope_changes')
    build_tool = Path(__file__).resolve().parents[1] / 'build_candidate_release.py'
    need(build_tool.read_bytes() == git(checkout, 'show', PRODUCT + ':verification/build_candidate_release.py'),
         'wheel_builder_has_drift')
    spec = importlib.util.spec_from_file_location('fixed_wheel_builder', build_tool)
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    install_root = root / 'install'
    install_root.mkdir(exist_ok=False)
    staged = install_root / 'git_source'
    staged.mkdir()
    site = install_root / 'candidate-site'
    manifest = []
    for path in sorted(original_manifest.keys() | changed):
        builder.safe_name(path)
        raw = git(checkout, 'show', commit + ':' + path)
        digest = sha(raw)
        if path not in changed:
            need(digest == original_manifest[path], 'unlisted_source_modified/' + path)
        dst = staged / path
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(raw)
        manifest.append({'path': path, 'sha256': digest})
    for relative in ('pyproject.toml', 'human_eye_plugin/plugin.json', 'human_eye_plugin/mcp_config.json'):
        raw = git(checkout, 'show', commit + ':' + relative)
        need(raw == git(checkout, 'show', PRODUCT + ':' + relative), 'unlisted_packaging_change')
        (staged / relative).write_bytes(raw)
    project = tomllib.loads((staged / 'pyproject.toml').read_text(encoding='utf8'))['project']
    artifact, wheel_bytes = builder.wheel_bytes(staged, manifest, project, '9.7.2+m4taskfocus001')
    wheel_check = builder.verify_wheel(wheel_bytes)
    wheel = install_root / artifact
    wheel.write_bytes(wheel_bytes)
    args = [sys.executable, '-IB', '-m', 'pip', '--isolated', '--disable-pip-version-check',
            'install', '--no-index', '--no-deps', '--no-compile', '--target', str(site), str(wheel)]
    result = subprocess.run(args, capture_output=True, check=False)
    (install_root / 'pip.stdout').write_bytes(result.stdout)
    (install_root / 'pip.stderr').write_bytes(result.stderr)
    result.check_returncode()
    with ZipFile(wheel) as archive:
        for name in archive.namelist():
            if name.endswith('.dist-info/RECORD'):
                continue
            need((site / name).read_bytes() == archive.read(name), 'installed_wheel_member_mismatch/' + name)
    sys.path.insert(0, str(site))
    from human_eye_plugin import blender_process, live_spatial_mcp
    from human_eye_plugin import runtime_identity

    ident = runtime_identity.runtime_identity()
    need(ident['source_kind'] == 'installed_distribution' and ident['source_files'] == manifest
         and all(Path(m.__file__).resolve().is_relative_to(site)
                 for m in (runtime_identity, blender_process, live_spatial_mcp)), 'candidate_runtime_mismatch')
    for dep in baseline['dependencies'].values():
        confirm(dep['module'])
    build = install_root / 'BUILD.json'
    save(build, {'candidate_commit': commit, 'parent_commit': parent, 'changed': sorted(changed),
                 'runtime_identity': ident, 'wheel': pin(wheel), 'wheel_builder': pin(build_tool),
                 'wheel_verification': wheel_check, 'builds': 1, 'installs': 1, 'Blender_launches': 0})
    save(root / 'preflight/BASELINE_INSTALL_CUSTODY.json', baseline)
    proof = dict(baseline, candidate_commit=commit, source_sha256=ident['source_sha256'],
                 runtime_sources=len(manifest), installation={'path': str(site)},
                 wheel=pin(wheel), build=pin(build), source_manifest=manifest, candidate_installs=1)
    save(root / 'preflight/CANDIDATE_INSTALL_CUSTODY.json', proof)
    print(f'Installed {commit} with {len(manifest)} verified runtime sources ({ident["source_sha256"]})')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=lambda x: Path(x).resolve(strict=True))
    parser.add_argument('checkout', type=lambda x: Path(x).resolve(strict=True))
    parser.add_argument('candidate')
    parser.add_argument('baseline_custody', type=lambda x: Path(x).resolve(strict=True))
    options = parser.parse_args()
    install(options.root, options.checkout, options.candidate, options.baseline_custody)
