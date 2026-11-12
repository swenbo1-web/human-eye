"""Independent saved-input and source identity checks for the new consumption phase."""

import hashlib
import json
from pathlib import Path
import subprocess


HERE = Path(__file__).resolve().parent
BATCH = HERE.parent
ROOT = BATCH.parents[1]
QUALIFICATION = ROOT / 'verification/m4_grooved_rail_transfer_001'
PARENT = '25e4f21335a53b28c5688dc6611f13204a6fde15'
QUALIFIED = '9f38e8522cfeea9a580a19baad0e0d823eb1a16f'
checks = {}
git_reads = 0


def read(path):
    return json.loads(path.read_bytes())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check(name, value):
    checks[name] = bool(value)


def tree(commit, names):
    global git_reads
    git_reads += 1
    raw = subprocess.check_output(['git', 'ls-tree', '-r', '--full-tree', '-z', commit, '--', *names], cwd=ROOT)
    result = {}
    for row in raw.split(b'\0'):
        if row:
            meta, name = row.split(b'\t', 1)
            mode, kind, digest = meta.split()
            assert kind == b'blob' and mode in (b'100644', b'100755')
            result[name.decode('utf8')] = digest.decode('ascii')
    return result


def blob(path):
    data = path.read_bytes()
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def main():
    seal = read(BATCH / 'QUALIFICATION_SEAL.json')
    check('root_qualification_seal_exact_sha', sha(BATCH / 'QUALIFICATION_SEAL.json') == '98222645f650e95519912519ac192f8a94f404483e272fafe0a9e443b7f063b9')
    root_names = [row['path'] for row in seal['files']]
    seal_name = 'verification/fixes/20261112_m4_grooved_rail_qualification_review/QUALIFICATION_REVIEW.json'
    root_names.append(seal_name)
    root_blobs = tree(PARENT, root_names)
    check('all_sealed_root_files_equal_committed_bytes', all(
        blob(Path('D:/hefe') / name) == root_blobs[name] for name in root_names))
    check('all_sealed_root_hashes_equal_disk', all(sha(Path('D:/hefe') / row['path']) == row['sha256']
          and (Path('D:/hefe') / row['path']).stat().st_size == row['bytes'] for row in seal['files']))
    for name, source in (('ROOT_PLAN.md', 'docs/M4_GROOVED_RAIL_TRANSFER_001_CONSUMPTION_PLAN.md'),
                         ('QUALIFICATION_REVIEW.md', 'docs/M4_GROOVED_RAIL_TRANSFER_001_QUALIFICATION_REVIEW.md'),
                         ('QUALIFICATION_SEAL.json', seal_name)):
        check(name + '_equals_root_commit', blob(BATCH / name) == root_blobs[source])
    check('accepted_input_commit', seal['implementation_commit'] == QUALIFIED)
    check('accepted_product_commit', seal['product_commit'] == 'e836e03f4b3821f869c72ac3e50df5204f28b50f')
    check('accepted_qualification_status', seal['status'] == 'qualified_for_frozen_six_consumer_phase')

    manifest = read(QUALIFICATION / 'QUALIFICATION_MANIFEST.json')
    check('qualification_manifest_sha', sha(QUALIFICATION / 'QUALIFICATION_MANIFEST.json') == '6ff0b854aa52385322e93693c3fa647647eae7705fe91c6a6ca87d209855a9c4')
    prefix = QUALIFICATION.relative_to(ROOT).as_posix() + '/'
    qualification_blobs = tree(QUALIFIED, [prefix])
    actual = {p.relative_to(ROOT).as_posix() for p in QUALIFICATION.rglob('*') if p.is_file()}
    check('qualification_exact_57_file_inventory', len(actual) == 57 and actual == set(qualification_blobs))
    check('qualification_57_fixed_git_bytes', all(blob(ROOT / name) == digest for name, digest in qualification_blobs.items()))
    check('qualification_56_manifest_entries', len(manifest['files']) == 56 and all(
        sha(QUALIFICATION / row['path']) == row['sha256']
        and (QUALIFICATION / row['path']).stat().st_size == row['bytes'] for row in manifest['files']))
    for source, target, digest in (
        ('asset/grooved_rail.blend', 'input/scene.blend', '49c0dccb233181a97d6d1508cc2570c03c961dffd2f8c8ef4ba12ebae3f9ec67'),
        ('asset/ACTUAL_SNAPSHOT.json', 'scoring/ACTUAL_SNAPSHOT.json', '6bb073b9aa29e7eecc5aa74ad2330cbb8fb5c5e06c79e70bf71091a33470ff52'),
        ('oracle/TRUTH.json', 'scoring/TRUTH.json', '2d072197f67f2d9860cb2ceb86c2782a7d4d2c3a71f1ed6d8be2487afc0eaa74'),
    ):
        check(target + '_qualified_bytes', sha(QUALIFICATION / source) == sha(BATCH / target) == digest)
    prompt = next(line[2:] for line in (BATCH / 'ROOT_PLAN.md').read_text(encoding='utf8').splitlines() if line.startswith('> 检查')).encode('utf8')
    check('prompt_exact_446_utf8_bytes', (BATCH / 'input/PROMPT.txt').read_bytes() == prompt and len(prompt) == 446)
    snapshot = read(BATCH / 'scoring/ACTUAL_SNAPSHOT.json')
    check('actual_snapshot_4_26_36', snapshot['counts'] == {'objects': 4, 'vertices': 26, 'triangles': 36})
    check('actual_object_names', {row['name'] for row in snapshot['objects']} == {'Target', 'Part_A', 'Part_B', 'Part_C'})
    check('actual_input_unit_one', snapshot['unit_scale_m'] == snapshot['scale_length'] == 1)
    check('snapshot_normalizer_fields_present', all(all(key in row for key in ('name', 'vertices_local', 'matrix_world', 'faces')) for row in snapshot['objects']))

    source = read(QUALIFICATION / 'SOURCE_BINDING.json')
    ready = read(BATCH / 'installations/P_READY.json')
    runtime_rows = source['source_manifest']
    check('source_identity_137', len(runtime_rows) == source['source_count'] == ready['source_count'] == 137
          and source['source_sha256'] == ready['source_sha256'] == '2c453e56f3abf83a49f9c8ef37a3a77728dd8f05168db4fd5217d3bad465c390')
    check('worktree_and_isolated_installation_source_sha', all(
        sha(ROOT / row['path']) == sha(Path(ready['install_root']) / row['path']) == row['sha256'] for row in runtime_rows))
    product_blobs = tree(ready['commit'], [row['path'] for row in runtime_rows])
    check('137_sources_equal_fixed_product_git', all(blob(ROOT / row['path']) == product_blobs[row['path']] for row in runtime_rows))
    check('runtime_launcher_and_binding', sha(Path(ready['entry'])) == ready['launcher_sha256']
          and sha(Path(ready['release']) / 'admin/RUNTIME_BINDING.json') == ready['binding_sha256'])
    check('protected_files_equal_bootstrap', all(sha(Path(name)) == digest for name, digest in read(BATCH / 'preflight/PROTECTED_BEFORE.json').items()))
    output = {
        'passed': all(checks.values()), 'checks': checks,
        'failed_checks': [name for name, value in checks.items() if not value],
        'git_read_commands': git_reads,
        'AL': {'context_bound': False, 'host_epoch': 5, 'rebind_required': True, 'borrowed_handle': False},
        'model_consumers': 0, 'Blender_sessions': 0, 'product_runs': 0,
        'reviewer_source_sha256': sha(Path(__file__)),
    }
    with (HERE / 'INPUT_IDENTITY.json').open('x', encoding='utf8', newline='\n') as stream:
        json.dump(output, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write('\n')
    print(json.dumps({'passed': output['passed'], 'checks': len(checks), 'failed': output['failed_checks'], 'git_read_commands': git_reads}))


if __name__ == '__main__':
    main()
