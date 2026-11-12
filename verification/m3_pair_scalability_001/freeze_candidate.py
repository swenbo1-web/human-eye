"""Record the final runtime source bytes without importing the product."""

import ast
import hashlib
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sha = lambda raw: hashlib.sha256(raw).hexdigest()


def main():
    tree = ast.parse((ROOT / 'human_eye_plugin/runtime_identity.py').read_bytes())
    constants = {
        node.targets[0].id: ast.literal_eval(node.value)
        for node in tree.body
        if isinstance(node, ast.Assign)
        and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id in ('BASE_VERSION', 'IMPLEMENTATION_REVISION', '_ROOT_MODULES')
    }
    names = set(constants['_ROOT_MODULES'])
    for package in ('human_eye_plugin', 'human_eye_module1_operators'):
        names.update(path.relative_to(ROOT).as_posix() for path in (ROOT / package).glob('*.py'))
    manifest = [{'path': name, 'sha256': sha((ROOT / name).read_bytes())} for name in sorted(names)]
    assert len(manifest) == 137
    canonical = sha(json.dumps({
        'base_version': constants['BASE_VERSION'],
        'implementation_revision': constants['IMPLEMENTATION_REVISION'],
        'files': manifest,
    }, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode())
    pins = {row['path']: row['sha256'] for row in manifest}
    assert pins['human_eye_plugin/surface_proximity.py'] == 'ef909bed94344408c6ac53a3e40b8fac3886c6ea69d96dbcb2c2a51ce6cdbf98'
    assert pins['human_eye_plugin/surface_geometry.py'] == '5142952ffb61976e40966bf5a69ef1e2aa25c7dde11de9d4755f7a2c4d71a9d3'
    record = {
        'cycle_id': 'M3-PAIR-SCALABILITY-001',
        'source_count': len(manifest),
        'source_sha256': canonical,
        'manifest': manifest,
        'baseline_product_commit': 'fac9b4373575d653cc96f39f1dcb225300cd5977',
        'simplification_review_sha256': sha((HERE / 'SIMPLIFICATION_REVIEW.md').read_bytes()),
        'substantive_optimizations_after_initial_candidate': 1,
        'prior_closed_failure_preserved': True,
        'final_closed_counter_result': 'three G508 pairs still reach the original work budget',
        'remaining_execution': 'same-source regressions, forty frozen kernel samples, one isolated install and three-business MCP sequence',
        'default_activation': False,
    }
    with (HERE / 'CANDIDATE_FREEZE.json').open('x', encoding='utf8', newline='\n') as stream:
        json.dump(record, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write('\n')
    print(json.dumps({'source_count': len(manifest), 'source_sha256': canonical}))


if __name__ == '__main__':
    main()
