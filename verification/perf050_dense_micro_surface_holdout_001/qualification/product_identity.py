"""Verify the existing installation without building or changing the product."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[3]
INSTALL = ROOT / 'verification/m4_source_region_blocker_frame_list_001/install'
BINDING = INSTALL / 'PRODUCT_RUN_BINDING.json'
SCHEMA = INSTALL / 'PRODUCT_SCHEMA.json'
CATALOGUE = INSTALL / 'TOOLS_SCHEMA.json'
COMMIT = '8cf3fabc1a735b7ff5849b3c63c49cf932df4b6b'
SOURCE = '65bd1ec8009f8024e85ef1cd30c1229957cceb1c1766c8e5b62f2ef2489ce48c'
WHEEL = '97053290d96270fefeff95d681efaf5222a64ef136a084267be5d7c707d6813d'


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def read(path):
    return json.loads(path.read_bytes())


def pin(path):
    path = path.resolve(strict=True)
    data = path.read_bytes()
    return {'path': str(path), 'bytes': len(data), 'sha256': sha256(data).hexdigest()}


def verify_identity():
    binding = read(BINDING)
    install_root = Path(binding['install_root']).resolve(strict=True)
    wheel = pin(Path(binding['wheel_path']))
    require((binding['preparation_git'], binding['source_sha256'], wheel['sha256'], binding['wheel_sha256']) ==
            (COMMIT, SOURCE, WHEEL, WHEEL), 'frozen_product_hashes_changed')
    require(install_root == Path('D:/he_m4_source_region_blocker_frame_list_001/candidate_install/product'),
            'frozen_install_path_changed')
    manifest = {row['path']: row['sha256'] for row in binding['source_manifest']}
    require(len(manifest) == len(binding['source_manifest']) == 143, 'frozen_manifest_size_changed')
    batch = ''.join(f'{COMMIT}:{name}\n' for name in manifest).encode('utf-8')
    blobs = subprocess.check_output(['git', 'cat-file', '--batch'], input=batch, cwd=ROOT, timeout=25)
    cursor = 0
    with ZipFile(wheel['path']) as archive:
        require(len(archive.namelist()) == len(set(archive.namelist())), 'duplicate_wheel_member')
        for name, digest in manifest.items():
            line_end = blobs.index(b'\n', cursor)
            _, kind, length = blobs[cursor:line_end].split()
            end = line_end + 1 + int(length)
            data = blobs[line_end+1:end]
            require(kind == b'blob' and blobs[end:end+1] == b'\n', 'git_source_blob_unavailable/' + name)
            cursor = end + 1
            actual = (install_root / name).resolve(strict=True)
            require(actual.is_relative_to(install_root) and data == archive.read(name) == actual.read_bytes()
                    and sha256(data).hexdigest() == digest, 'install_wheel_git_source_mismatch/' + name)
    require(cursor == len(blobs), 'unexpected_git_source_members')

    sys.path[:0] = [str(install_root), binding['dependency_root']]
    from human_eye_plugin import live_spatial_mcp
    from human_eye_plugin.runtime_identity import runtime_identity

    identity = runtime_identity()
    require(Path(live_spatial_mcp.__file__).is_relative_to(install_root)
            and identity['source_kind'] == 'installed_distribution' and len(identity['source_files']) == 143
            and all(identity[key] == binding[key] for key in (
                'source_sha256', 'distribution_version', 'build_id', 'implementation_revision', 'protocol_version')),
            'installed_loaded_identity_mismatch')
    expected = read(SCHEMA)
    definitions = read(CATALOGUE)
    require(expected['name'] == 'human_eye_scene_observe'
            and [row for row in definitions if row['name'] == expected['name']] == [expected],
            'observe_frozen_schema_not_unique')
    return {'passed': True, 'git_commit': COMMIT, 'source_sha256': SOURCE, 'sources_verified': len(manifest),
            'wheel': wheel, 'install_root': str(install_root), 'runtime_identity': identity,
            'binding': pin(BINDING), 'schema': pin(SCHEMA), 'catalogue': pin(CATALOGUE),
            'builds': 0, 'installs': 0}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = verify_identity()
    with args.output.open('xb') as stream:
        stream.write((json.dumps(report, indent=2, ensure_ascii=False) + '\n').encode())
    print(f"Verified {report['sources_verified']} Git, wheel and installed sources.")
