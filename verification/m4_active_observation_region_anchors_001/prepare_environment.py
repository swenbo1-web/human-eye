"""Copy the previously verified numerical dependencies into an owned venv."""

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import time


ROOT = Path(__file__).resolve().parents[2]
TASK = Path(__file__).resolve().parent
EXTERNAL = Path('D:/he_anchor_001')
BASE = Path('C:/Users/Administrator/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe')
BASE_SHA = '50f885251e42eb8cd1fbf5d4fbcc01efdbe8b9f4d4379e16664d4d0f3d4a9869'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    started = time.perf_counter_ns()
    assert digest(BASE) == BASE_SHA
    assert not EXTERNAL.exists(), 'owned task root must be new'
    EXTERNAL.mkdir()
    output = TASK / 'preparation'
    output.mkdir(exist_ok=False)
    command = [str(BASE), '-I', '-B', '-m', 'venv', str(EXTERNAL / 'venv')]
    result = subprocess.run(command, capture_output=True)
    (output / 'VENV_STDOUT.bin').write_bytes(result.stdout)
    (output / 'VENV_STDERR.bin').write_bytes(result.stderr)
    assert result.returncode == 0
    previous = ROOT / 'verification/m4_active_observation_patch_ownership_001/preparation/ENVIRONMENT.json'
    manifest = json.loads(previous.read_bytes())
    previous_site = Path('D:/he_patch_001/venv/Lib/site-packages')
    site = EXTERNAL / 'venv/Lib/site-packages'
    copied = []
    copy_started = time.perf_counter_ns()
    for row in manifest['dependencies']:
        source = Path(row['path'])
        assert source.is_relative_to(previous_site)
        assert source.stat().st_size == row['bytes'] and digest(source) == row['sha256']
        target = site / source.relative_to(previous_site)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        assert digest(target) == row['sha256']
        copied.append({**row, 'path': str(target), 'copied_from': str(source)})
    (site / 'human_eye_owned_product.pth').write_text(str(EXTERNAL / 'product') + '\n', encoding='utf8')
    receipt = {'started_ns': started, 'copy_started_ns': copy_started,
               'closed_before_publication_ns': time.perf_counter_ns(),
               'base_python': str(BASE), 'base_python_sha256': BASE_SHA,
               'command': command, 'venv_exit_code': result.returncode,
               'prior_environment_path': str(previous), 'prior_environment_sha256': digest(previous),
               'dependencies': copied, 'dependency_file_count': len(copied),
               'dependency_bytes': sum(row['bytes'] for row in copied),
               'product_functions_tests_rasters_model_calls': 0}
    (output / 'ENVIRONMENT.json').write_text(json.dumps(receipt, sort_keys=True, indent=2) + '\n', encoding='utf8')
    print(json.dumps({'dependency_files': len(copied), 'bytes': receipt['dependency_bytes']}))


if __name__ == '__main__':
    main()
