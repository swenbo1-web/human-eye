"""Copy the frozen quality tree and remove only its consumer-error clock envelope."""

import copy
import hashlib
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
BATCH = HERE.parent
SOURCE = BATCH/'runtime/handoff_01/public'
DESTINATION = BATCH/'quality/public'
RECEIPT = BATCH/'quality/ADMIN_REDACTION.json'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf8')


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)+'\n').encode('utf8')


def tree_manifest(files):
    return [{'path':name, 'bytes':len(raw), 'sha256':sha(raw)} for name,raw in sorted(files.items())]


def main():
    assert not DESTINATION.exists() and not RECEIPT.exists(), 'preserve existing handoff copies'
    provenance_path = BATCH/'runtime/handoff_01/private/PROVENANCE.json'
    provenance_raw = provenance_path.read_bytes()
    provenance = json.loads(provenance_raw)
    originals = {path.relative_to(SOURCE).as_posix():path.read_bytes()
                 for path in SOURCE.rglob('*') if path.is_file()}
    assert len(originals) == 42
    assert {name:sha(raw) for name,raw in originals.items()} == provenance['public_files_sha256']
    index = json.loads(originals['INDEX.json'])
    assert encoded(index) == originals['INDEX.json'], 'frozen INDEX encoding differs'
    assert index['fixed_slots'] == len(index['answers']) == 9 and index['scoring_performed'] is False
    redacted = copy.deepcopy(index)
    removals = []
    envelope_keys = set()
    for answer_index,answer in enumerate(redacted['answers']):
        for error_index,error in enumerate(answer['consumer_execution_errors']):
            assert isinstance(error,dict)
            envelope_keys.update(error)
            # These are the actual frozen CLI error-envelope fields. The event
            # payload is retained without recursively filtering its contents.
            assert set(error) <= {'event','perf_ns'}, 'unknown consumer error envelope requires explicit review'
            if 'perf_ns' in error:
                value = error.pop('perf_ns')
                assert type(value) is int
                removals.append({'pointer':f'$/answers/{answer_index}/consumer_execution_errors/{error_index}/perf_ns',
                    'rule':'known_consumer_error_administrative_perf_counter',
                    'removed_value_canonical_sha256':sha(canonical(value)),
                    'event_payload_canonical_sha256':sha(canonical(error['event']))})
    assert len(removals) == 2
    restored = copy.deepcopy(redacted)
    for source_answer,target_answer in zip(index['answers'],restored['answers'],strict=True):
        for source_error,target_error in zip(source_answer['consumer_execution_errors'],target_answer['consumer_execution_errors'],strict=True):
            if 'perf_ns' in source_error:
                target_error['perf_ns'] = source_error['perf_ns']
    assert encoded(restored) == originals['INDEX.json'], 'unrelated INDEX fields changed'
    transformed = dict(originals)
    transformed['INDEX.json'] = encoded(redacted)
    assert all(transformed[name] == raw for name,raw in originals.items() if name != 'INDEX.json')
    historical_zips = {path.name:sha(path.read_bytes()) for path in (BATCH/'quality').glob('*.zip')}
    DESTINATION.mkdir(parents=True,exist_ok=False)
    for name,raw in transformed.items():
        target = DESTINATION/name
        target.parent.mkdir(parents=True,exist_ok=True)
        with target.open('xb') as stream:
            stream.write(raw)
    actual = {path.relative_to(DESTINATION).as_posix():path.read_bytes()
              for path in DESTINATION.rglob('*') if path.is_file()}
    assert actual == transformed
    assert provenance_path.read_bytes() == provenance_raw
    assert {path.relative_to(SOURCE).as_posix():path.read_bytes()
            for path in SOURCE.rglob('*') if path.is_file()} == originals
    assert {name:sha((BATCH/'quality'/name).read_bytes()) for name in historical_zips} == historical_zips
    manifest = tree_manifest(actual)
    record = {'schema':'nine_slot_quality_admin_redaction_v1',
        'source_public':'runtime/handoff_01/public','final_public':'quality/public',
        'source_public_manifest_sha256':sha(canonical(tree_manifest(originals))),
        'final_public_manifest_sha256':sha(canonical(manifest)),
        'manifest_canonicalization':'SHA256 of UTF-8 JSON list sorted by POSIX path, each path/bytes/sha256, sort_keys=true, compact separators, ensure_ascii=false',
        'source_INDEX_sha256':sha(originals['INDEX.json']),'final_INDEX_sha256':sha(actual['INDEX.json']),
        'original_PROVENANCE_sha256':sha(provenance_raw),'historical_zip_sha256_unchanged':historical_zips,
        'public_file_count':42,'other_public_files_exact_byte_equal':41,
        'INDEX_restored_after_reinserting_only_original_removed_values_matches_original_bytes':True,
        'consumer_error_envelope_keys_found':sorted(envelope_keys),
        'other_management_time_fields_in_the_exact_error_envelope':[],
        'removals':removals,'final_public_manifest':manifest,
        'all_error_event_messages_preserved':True,'source_and_historical_zip_unchanged':True,
        'frozen_packer_or_originals_modified':False,'formal_scoring_performed':False,
        'new_model_Blender_product_API_runs':0,'script_sha256':sha(Path(__file__).read_bytes())}
    with RECEIPT.open('xb') as stream:
        stream.write(encoded(record))
    print(json.dumps({'public_files':42,'removed_administrative_clock_fields':len(removals),
        'final_public_manifest_sha256':record['final_public_manifest_sha256'],
        'final_INDEX_sha256':record['final_INDEX_sha256'],'formal_scoring_performed':False}))


if __name__ == '__main__':
    main()
