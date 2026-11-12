"""Record the authorized saved-data unseal and its immutable source index."""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess


HERE = Path(__file__).resolve().parent
BATCH = HERE.parent
ROOT = BATCH.parents[1]
AUTHOR = '4a90bbe95ef46c6666050ef1a1096fc6719c3b97'
REVIEW = 'e94798714d5d23694f0515f00e9eb083982a2b2f'
SEAL = Path('D:/hefe/verification/fixes/20261112_m4_grooved_rail_quality_review/QUALITY_SEAL.json')
SEAL_SHA = 'a493bd997b2003c595795ad90ae3bc9420e9a2a884a0adcf6225493f880f0c21'
REPORT = Path('D:/hefe/docs/M4_GROOVED_RAIL_TRANSFER_001_QUALITY_REVIEW.md')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def save(path, value):
    with path.open('x', encoding='utf8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        stream.write('\n')


def main():
    assert sha(SEAL.read_bytes()) == SEAL_SHA
    seal = json.loads(SEAL.read_bytes())
    assert seal['formal_commit'] == AUTHOR
    assert seal['quality']['complete_correct'] == 6
    assert seal['quality']['facts_correct'] == seal['quality']['facts_required'] == 78
    source = HERE / 'quality_source'
    source.mkdir(exist_ok=True)
    for original, name in ((SEAL, 'QUALITY_SEAL.json'), (REPORT, 'QUALITY_REVIEW.md')):
        data = original.read_bytes()
        tracked = original.relative_to(Path('D:/hefe')).as_posix()
        committed = subprocess.check_output(['git', 'show', REVIEW + ':' + tracked], cwd=ROOT)
        assert committed == data, tracked
        with (source / name).open('xb') as stream:
            stream.write(data)

    prefix = BATCH.relative_to(ROOT).as_posix() + '/'
    names = subprocess.check_output(['git', 'ls-tree', '-r', '-z', AUTHOR, '--', prefix], cwd=ROOT)
    records = []
    for raw in names.split(b'\0'):
        if not raw:
            continue
        metadata, raw_name = raw.split(b'\t', 1)
        name = raw_name.decode('utf8')
        data = (ROOT / name).read_bytes()
        mode, kind, blob_raw = metadata.split()
        assert kind == b'blob'
        blob = blob_raw.decode()
        actual_blob = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
        assert blob == actual_blob, name
        records.append({'path': name, 'bytes': len(data), 'sha256': sha(data), 'git_blob': blob})
    save(HERE / 'ORIGINAL_DATA_INDEX.json', {
        'author_commit': AUTHOR, 'original_batch_files': records,
        'all_disk_bytes_match_fixed_commit': True,
        'index_scope': 'All batch files in the fixed author commit. New analysis outputs are outside this index.',
    })
    save(HERE / 'WORK_ORDER.json', {
        'cycle': 'M4-GROOVED-RAIL-TRANSFER-001', 'phase': 'saved_data_cost_and_mechanism_unseal',
        'recorded_utc': datetime.now(timezone.utc).isoformat(),
        'authorization': 'Administrator delegated quality-sealed unseal, saved-data analysis, original-branch evidence commit and callback.',
        'author_commit': AUTHOR, 'quality_review_commit': REVIEW, 'quality_seal_sha256': SEAL_SHA,
        'public_packet_sha256': seal['public_packet_sha256'],
        'allowed_scope': 'Read existing evidence, execute standard-library analysis and Git, write this cost_review_01 directory, commit and push original branch.',
        'new_consumer_allowance': 0, 'new_Blender_or_product_run_allowance': 0,
        'AL': {'context_bound': False, 'host_epoch': 5, 'rebind_required': True,
               'task_registered': False, 'borrowed_handle': False},
        'pre_record_events': 'Read-only sealed quality, contracts, prior analysis scripts and current session context inspection preceded this record.',
        'completion': 'Cost and mechanism review ready callback, then wait for administrator review.',
    })
    print(json.dumps({'original_files_bound': len(records), 'quality_seal_sha256': SEAL_SHA,
                      'new_consumers': 0, 'new_Blender_or_product_runs': 0}))


if __name__ == '__main__':
    main()
