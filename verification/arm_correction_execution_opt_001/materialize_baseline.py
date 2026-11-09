"""Extract accepted runtime bytes, without switching any checkout or branch."""
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).parent
COMMIT = 'a3a72b929f55c40f195ff5e1a9f64ceb303b6360'
TARGET = ROOT / '.arm_correction_opt_baseline'


def main():
    assert not TARGET.exists(), 'new_baseline_directory_required'
    manifest = json.loads((ROOT / 'verification/arm_correction_execution_001/native_01/SOURCE_FREEZE.json')
                          .read_text(encoding='utf8'))['runtime_identity']['source_files']
    TARGET.mkdir()
    members = {}
    for name in [m['path'] for m in manifest] + ['pyproject.toml']:
        blob = subprocess.check_output(['git', 'show', COMMIT + ':' + name], cwd=ROOT)
        dest = TARGET / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(blob)
        members[name] = hashlib.sha256(blob).hexdigest()
    assert all(members[m['path']] == m['sha256'] for m in manifest)
    record = {'commit': COMMIT, 'source_root': str(TARGET),
              'files': members, 'runtime_sources': len(manifest),
              'scope': 'byte_exact_git_materialization_not_branch_or_worktree_switch'}
    (HERE / 'BASELINE_MATERIALIZATION.json').write_text(
        json.dumps(record, indent=2) + '\n', encoding='utf8', newline='\n')
    print(json.dumps({'source_root': str(TARGET), 'runtime_sources': len(manifest)}))


if __name__ == '__main__':
    main()
