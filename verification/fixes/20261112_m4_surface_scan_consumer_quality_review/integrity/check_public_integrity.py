"""Independent public quality-packet byte/provenance audit; no scoring or unblinding.

Private and raw per-cell files are read only as opaque bytes for manifest hashing.
Their JSON, ZIP members, group mapping, events, timing and usage are not decoded.
"""
from pathlib import Path, PurePosixPath
import ast
import hashlib
import json
import subprocess
import zipfile

ROOT = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
OUT = Path(__file__).resolve().parent
PREFIX = 'verification/m4_surface_scan_consumption_001'
BASE = ROOT / PREFIX
PUBLIC = BASE / 'runtime/handoff_01/public'
DELIVERY = 'e5c8afafbcd7cf55307be9e640a3e2ad61e25fd3'
PREPARE = 'bedcc827ec548e3afab816c0986db0c99eb42bb8'
PRODUCT = 'c1cb2da32034e056a270384e691a2cde8dddbc0d'
QUALIFICATION = '96fce78b98cb749885792112e039a406744d282b'
SOURCE = 'c4832b1a1ced9438f904e25a431e2327c2d7532e2f4efbb34e34ce58a7ed1943'
ASSET = '7f6452d1d706a9f2db31126eb3aa7d08622e37a28abb9610992006bad5f5ad66'
CHECKS = []


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def blob(raw):
    return hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()


def check(name, value, detail=None):
    CHECKS.append({'name': name, 'passed': bool(value), 'detail': detail})
    assert value, name


def decode(path):
    # No raw per-cell records or private archives may be decoded by this audit.
    path = path.resolve()
    allowed = (path.is_relative_to(PUBLIC.resolve())
               or path in {(BASE / 'DELIVERY_MANIFEST.json').resolve(),
                           (ROOT / 'verification/m4_surface_scan_001_opt1/CANDIDATE_SOURCE.json').resolve(),
                           (ROOT / 'verification/m4_surface_scan_001_opt1/installation/run_01/READY.json').resolve()})
    assert allowed, 'decode outside public/explicit nonprivate allowlist'
    return json.loads(path.read_bytes())


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)


def tree(commit, *paths):
    return {name.decode(): meta.split()[2].decode()
            for row in git('ls-tree', '-r', '-z', commit, '--', *paths).split(b'\0') if row
            for meta, name in [row.split(b'\t', 1)]}


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()


def run():
    check('delivery_HEAD', git('rev-parse', 'HEAD').decode().strip() == DELIVERY)
    check('implementation_tracked_clean', not git('status', '--porcelain').strip())
    manifest_path = BASE / 'DELIVERY_MANIFEST.json'
    raw = manifest_path.read_bytes()
    check('delivery_manifest_anchor', sha(raw) == '1ead579f888711876cb6295d86c3134285bcf578e278247c8ea5a8affc66ce2d')
    manifest = decode(manifest_path)
    records = manifest['files']
    check('delivery_1974_unique_content_files', len(records) == len({r['path'] for r in records}) == 1974)
    entries = tree(DELIVERY, PREFIX)
    check('delivery_manifest_Git_bytes', entries[PREFIX + '/DELIVERY_MANIFEST.json'] == blob(raw))
    check('delivery_Git_full_set', set(entries) == {r['path'] for r in records} | {PREFIX + '/DELIVERY_MANIFEST.json'})
    # Do not output per-cell paths or associate any anonymous ID with them.
    all_hashes = set()
    for index, record in enumerate(records):
        rel = PurePosixPath(record['path'])
        check('manifest_path_' + str(index), not rel.is_absolute() and '..' not in rel.parts)
        path = ROOT / record['path']
        check('manifest_inside_scope_' + str(index), path.resolve().is_relative_to(BASE.resolve()) and not path.is_symlink())
        content = path.read_bytes()
        check('manifest_bytes_' + str(index), len(content) == record['bytes'] and sha(content) == record['sha256'])
        check('manifest_Git_blob_' + str(index), blob(content) == entries.get(record['path']))
        all_hashes.add(record['sha256'])

    public_files = sorted((p for p in PUBLIC.rglob('*') if p.is_file()), key=lambda p: p.relative_to(PUBLIC).as_posix())
    check('public_30_files', len(public_files) == 30)
    public_manifest = [{'path': p.relative_to(PUBLIC).as_posix(), 'bytes': p.stat().st_size,
                        'sha256': sha(p.read_bytes())} for p in public_files]
    public_digest = sha(canonical(public_manifest))
    check('public_tree_canonical_anchor', public_digest == '1c58a4b2ecc758b27764a5c500ad38825b6acb9894b5677bce2def666076b23f')
    archive = BASE / 'quality/SURFACE_SCAN_ANONYMOUS_QUALITY_001.zip'
    check('public_zip_anchor', sha(archive.read_bytes()) == '05638c8d324c661e7d8c816fe737045516dd7440d1018023c83149dc549f1051')
    check('public_zip_size', archive.stat().st_size == 272765)
    with zipfile.ZipFile(archive) as z:
        names = z.namelist()
        check('public_zip_unique_exact_members', len(names) == len(set(names)) == 30 and set(names) == {r['path'] for r in public_manifest})
        for name in names:
            check('public_zip_member_' + name, z.read(name) == (PUBLIC / name).read_bytes())
            check('public_zip_metadata_' + name, z.getinfo(name).date_time == (1980, 1, 1, 0, 0, 0))

    index = decode(PUBLIC / 'INDEX.json')
    answers = index['answers']
    check('six_anonymous_slots', index['fixed_slots'] == len(answers) == 6 and len({x['anonymous_id'] for x in answers}) == 6)
    check('six_directories_match_index', {p.name for p in PUBLIC.glob('answer_*') if p.is_dir()} == {x['directory'] for x in answers})
    check('no_author_quality_score', index['scoring_performed'] is False)
    check('public_execution_six_completed', all(x['cell_execution_state'] == 'completed' and x['answer_state'] == 'present' for x in answers))
    check('one_common_T1_prompt', len(index['tasks']) == 1 and index['tasks'][0]['task_id'] == 'T1')
    prompt = (PUBLIC / 'tasks/T1.txt').read_bytes()
    check('prompt_anchor', sha(prompt) == index['tasks'][0]['input_sha256'] == '6a78e38a474647c0c0c49558be215864cb672932273b3e15ca6ba7f9fa02b4fc')
    check('public_task_zero_images', index['tasks'][0]['initial_image_count'] == index['tasks'][0]['new_images'] == 0)
    bindings = []
    for answer in answers:
        aid = answer['anonymous_id']
        folder = PUBLIC / answer['directory']
        final = (folder / answer['answer_file']).read_bytes()
        check(aid + '_final_byte_hash', sha(final) == answer['answer_original_sha256'] == answer['source_provenance']['public_final_sha256'])
        check(aid + '_final_has_original_blob_in_delivery', sha(final) in all_hashes)
        check(aid + '_consumer_record_digest_exists', answer['source_provenance']['consumer_record_sha256'] in all_hashes)
        consistency = decode(folder / answer['source_consistency_file'])
        check(aid + '_both_asset_claims', consistency['ACTOR_CONFIG']['asset_sha256'] == consistency['owner_IDENTITY']['asset_sha256'] == ASSET)
        check(aid + '_initial_final_record_digest_exists', consistency['INITIAL_original_file_sha256'] in all_hashes and consistency['FINAL_original_file_sha256'] in all_hashes)
        check(aid + '_initial_final_record_digest_equal', consistency['INITIAL_original_file_sha256'] == consistency['FINAL_original_file_sha256'])
        check(aid + '_source_record_digests_exist', all(h in all_hashes for h in consistency['source_records_sha256'].values() if h is not None))
        close = consistency['CLOSE']
        check(aid + '_public_close_claims', close['asset_unchanged'] is True and close['geometry_unchanged'] is True and close['errors'] == [])
        check(aid + '_public_geometry_fingerprints', close['worker_fingerprint_fields']['initial_geometry_fingerprint'] == close['worker_fingerprint_fields']['final_geometry_fingerprint'])
        inp = consistency['CONSUMER_INPUT']
        check(aid + '_text_only_claims', inp['input_image_count'] == inp['input_image_bytes'] == 0 and inp['image_delivery']['initial_attachment_in_argv'] is False)
        evidence = decode(folder / answer['evidence_file'])
        attempts = evidence['owner_attempts']
        events = evidence['public_tool_events']
        check(aid + '_attempt_order', [x['order'] for x in attempts] == list(range(1, len(attempts) + 1)))
        check(aid + '_event_order', [x['order'] for x in events] == list(range(1, len(events) + 1)))
        check(aid + '_owner_record_digests_exist', all(row['original_sha256'] in all_hashes for a in attempts for row in a['source_files']))
        check(aid + '_event_record_digests_exist', all(e['source_sha256'] in all_hashes for e in events))
        check(aid + '_owner_request_response_present', all(not a['request_missing'] and not a['response_missing'] for a in attempts))
        completed = [e['event'] for e in events if e['phase'] == 'item.completed']
        check(aid + '_public_completed_event_count', len(completed) == len(attempts))
        for number, (a, ev) in enumerate(zip(attempts, completed), 1):
            params = a['request']['params']
            check(aid + '_request_event_' + str(number), params['name'] == ev['tool'] and params['arguments'] == ev['arguments'])
            response = a['responses']
            check(aid + '_response_event_' + str(number), len(response) == 1 and response[0]['value'].get('result', {}).get('content') == (ev.get('result') or {}).get('content'))
        bindings.append({'anonymous_id': aid, 'answer_sha256': sha(final),
                         'public_owner_attempts': len(attempts), 'public_completed_events': len(completed),
                         'initial_final_digest_equal': True, 'private_mapping_read': False})

    qualification_prefix = 'verification/m4_surface_scan_001/qualification'
    qualification_tree = tree(QUALIFICATION, qualification_prefix)
    for public_name, old_name, want in [
        ('scoring/ACTUAL_SNAPSHOT.json', 'BASE_SNAPSHOT.json', 'f8a578f78004a21e611c76d47506c5290f6015e7343e67b3b094a9e54da9884b'),
        ('scoring/TRUTH.json', 'BASE_TRUTH.json', 'a0f14b1a48601590445ce5e2d13bb34f56647caa2acedf3eeac97b32e8a656c7')]:
        content = (PUBLIC / public_name).read_bytes()
        check(public_name + '_original_qualification', sha(content) == want and content == (ROOT / qualification_prefix / old_name).read_bytes() and blob(content) == qualification_tree[qualification_prefix + '/' + old_name])
    asset_raw = (ROOT / qualification_prefix / 'assembly.blend').read_bytes()
    check('asset_original_qualification', sha(asset_raw) == ASSET and blob(asset_raw) == qualification_tree[qualification_prefix + '/assembly.blend'])
    for row in index['scoring_materials']:
        check('scoring_material_' + row['file'], sha((PUBLIC / row['file']).read_bytes()) == row['sha256'])

    candidate_path = ROOT / 'verification/m4_surface_scan_001_opt1/CANDIDATE_SOURCE.json'
    identity = decode(candidate_path)['identity']
    check('candidate_record_Git_bound', blob(candidate_path.read_bytes()) == tree(DELIVERY, candidate_path.relative_to(ROOT).as_posix())[candidate_path.relative_to(ROOT).as_posix()])
    source_rows = identity['source_files']
    check('runtime_138_sources', len(source_rows) == len({r['path'] for r in source_rows}) == 138)
    runtime_ast = ast.parse((ROOT / 'human_eye_plugin/runtime_identity.py').read_text(encoding='utf-8'))
    constants = {}
    for node in runtime_ast.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) and node.targets[0].id in {'BASE_VERSION','IMPLEMENTATION_REVISION','_ROOT_MODULES'}:
            constants[node.targets[0].id] = ast.literal_eval(node.value)
    actual_names = set(constants['_ROOT_MODULES'])
    for package in ['human_eye_plugin', 'human_eye_module1_operators']:
        actual_names.update(package + '/' + p.name for p in (ROOT / package).glob('*.py'))
    check('runtime_manifest_current_enumeration', actual_names == {r['path'] for r in source_rows})
    source_tree = tree(PRODUCT, *sorted(actual_names))
    install_ready = decode(ROOT / 'verification/m4_surface_scan_001_opt1/installation/run_01/READY.json')
    site = Path(install_ready['install_root'])
    wheels = list((ROOT / 'verification/m4_surface_scan_001_opt1/installation/run_01/bundle').glob('*.whl'))
    check('single_candidate_wheel', len(wheels) == 1)
    check('candidate_wheel_hash', sha(wheels[0].read_bytes()) == install_ready['wheel_sha256'] == '1ad6cd9ad3eb4ca27b62b49e3fa1e2ad66c00f163a80cf268b033d06b7bb4d79')
    with zipfile.ZipFile(wheels[0]) as z:
        for row in source_rows:
            name = row['path']
            raw = z.read(name)
            check('source_' + name, sha(raw) == row['sha256'] and blob(raw) == source_tree[name] and (ROOT / name).read_bytes() == raw and (site / name).read_bytes() == raw)
    digest = {'base_version': constants['BASE_VERSION'], 'implementation_revision': constants['IMPLEMENTATION_REVISION'], 'files': source_rows}
    source_hash = sha(json.dumps(digest, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode())
    check('runtime_aggregate_source', source_hash == identity['source_sha256'] == install_ready['source_sha256'] == SOURCE)
    check('runtime_no_product_diff', not git('diff', '--name-only', PRODUCT, DELIVERY, '--', *sorted(actual_names)).strip())

    return {'passed': True, 'delivery': DELIVERY, 'prepare': PREPARE, 'product': PRODUCT,
            'runtime_source_sha256': source_hash, 'delivery_content_files': len(records),
            'delivery_content_bytes': sum(r['bytes'] for r in records), 'public_file_count': len(public_files),
            'public_canonical_sha256': public_digest, 'public_manifest': public_manifest,
            'anonymous_bindings': bindings, 'checks_count': len(CHECKS),
            'new_Blender_model_API_runs': 0, 'private_semantic_decode_count': 0,
            'source_claim_scope': 'Public provenance claims bound to committed bytes; private raw projections, exact model-event origins, six thread IDs, and per-cell installation/initial-final snapshots deferred until quality seal.'}


if __name__ == '__main__':
    OUT.mkdir(parents=True, exist_ok=True)
    try:
        result = run()
    except Exception as exc:
        failure = OUT / 'FAILED.json'
        suffix = 2
        while failure.exists():
            failure = OUT / ('FAILED_' + str(suffix) + '.json')
            suffix += 1
        failure.write_text(json.dumps({'error': repr(exc), 'checks': CHECKS}, indent=2) + '\n', encoding='utf-8')
        raise
    (OUT / 'RESULTS.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (OUT / 'CHECKS.json').write_text(json.dumps(CHECKS, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: result[k] for k in ['passed','checks_count','delivery_content_files','public_file_count','private_semantic_decode_count']}))
