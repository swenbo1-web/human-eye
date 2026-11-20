"""Publish the sole dense region qualification, original wire and verdict."""

import argparse
import base64
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys


NS = Path(__file__).resolve().parent
sys.path.insert(0, str(NS / 'harness'))
from admission import registered_product, verify_freeze
from common import ASSET_SHA256, EXTERNAL, FORMAL, PRODUCT_BINDING, ROOT, asset_identity, load, read, save, sha


BASE = '76a46db953418c7204d7c4e80c7a2364fe0f26d8'


def archive():
    verify_freeze()
    original = load('_dense_region_exact_runtime_archive', FORMAL / 'publish.py')
    original.NS, original.EXTERNAL = NS, EXTERNAL
    original.archive()


def export():
    verify_freeze()
    review = read(NS / 'checks/LIVE_REVIEW.json')
    if review['passed'] is not True:
        raise ValueError('requires_complete_verified_wire')
    wire = review['wire']
    slot = EXTERNAL / 'slots/QP'
    original = slot / 'mcp/rpc_04/RX.bin'
    if sha(original) != wire['RX_sha256'] or original.stat().st_size != wire['RX_bytes']:
        raise ValueError('original_response_wire_changed')
    message = read(original)
    if message != read(slot / 'product_calls/call_001/RESPONSE.json'):
        raise ValueError('recorded_public_response_disagrees_with_wire')
    body, *blocks = message['result']['content']
    raw = body['text'].encode('utf8')
    if len(raw) != wire['body_UTF8_bytes'] or sha256(raw).hexdigest() != wire['body_sha256']:
        raise ValueError('original_fact_body_changed')
    digest_rows = [(f"{frame['view']}.png", frame['image_sha256'])
                   for frame in review['frames'] if frame['view'] in ('SCENE', 'LEFT')]
    if (body['type'] != 'text' or json.loads(raw)['schema'] != 'active-observation-region-task-brief-v2'
            or [row[0] for row in digest_rows] != ['SCENE.png', 'LEFT.png'] or len(blocks) != 2):
        raise ValueError('fixed_actual_public_content_reordered')
    files = {'BRIEF.json': raw}
    for block, (filename, digest) in zip(blocks, digest_rows, strict=True):
        if block['type'] != 'image' or block['mimeType'] != 'image/png':
            raise ValueError('original_native_image_block_changed')
        png = base64.b64decode(block['data'], validate=True)
        if sha256(png).hexdigest() != digest:
            raise ValueError('actual_original_png_bytes_changed/' + filename)
        files[filename] = png
    public = NS / 'public'
    public.mkdir()
    for name, content in files.items():
        with (public / name).open('xb') as stream:
            stream.write(content)


def finalize():
    frozen = verify_freeze()
    asset_identity()
    namespace = NS.relative_to(ROOT).as_posix() + '/'
    changed = subprocess.check_output(['git', 'diff', '--name-only', BASE], cwd=ROOT).decode().splitlines()
    if any(not path.startswith(namespace) for path in changed):
        raise ValueError('unexpected_difference_outside_registered_evidence')
    slots = EXTERNAL / 'slots'
    if {path.name for path in slots.iterdir()} != {'QP'}:
        raise ValueError('exactly_one_actual_qualification_slot_required')
    slot = slots / 'QP'
    result_file, publication_file = slot / 'SLOT_RESULT.json', slot / 'SLOT_PUBLICATION.json'
    result, publication = read(result_file), read(publication_file)
    product = registered_product()
    if (result['label'] != 'QP' or publication['label'] != 'QP'
            or publication['result_sha256'] != sha(result_file)
            or result['freeze_sha256'] != frozen or result['asset_sha256'] != ASSET_SHA256
            or result['model_consumers'] != 0 or result['paid_API_calls'] != 0
            or result['product_source_sha256'] != product['source_sha256']
            or result['product_binding_sha256'] != sha(PRODUCT_BINDING)):
        raise ValueError('actual_single_slot_lost_its_fixed_bindings')
    review = read(NS / 'checks/LIVE_REVIEW.json')
    if (review['freeze_sha256'] != frozen or review['slot_result_sha256'] != sha(result_file)
            or review['publication_sha256'] != sha(publication_file)):
        raise ValueError('review_does_not_name_the_actual_slot')
    counts = (result.get('budget') or {}).get('counts')
    passed = bool(publication['status'] == 'completed' and review['passed'] is True)
    if passed and ((counts['Blender_start_attempts'], counts['business_admissions'], counts['all_raster_actual'],
                    counts['all_raster_upper'], counts['consumer_admissions']) != (1, 1, 2, 2, 0)
                   or review['wire']['body_UTF8_bytes'] > 10800
                   or review['CLI']['passed'] is not True):
        raise ValueError('passed_result_disagrees_with_metadata_or_fixed_limits')
    files = ('REPORT.md', 'checks/OFFLINE_CONTROLS.json', 'checks/LIVE_REVIEW.json', 'install/BUILD_INSTALL.json',
             'public/BRIEF.json', 'public/SCENE.png', 'public/LEFT.png', 'RUNTIME_INDEX.json')
    save(NS / 'DECISION.json', {'task': 'M4-DENSE-REGION-BRIEF-001', 'passed': passed, 'freeze_sha256': frozen,
         'product': product, 'product_diff_files': 1, 'label': 'QP', 'qualification_denominator': 1,
         'original_slot_status': publication['status'], 'original_slot_sha256': sha(result_file),
         'actual_ledger_counts': counts, 'formal_model_slots_run': 0, 'native_qualifications_run': 0,
         'models': 0, 'replacements': 0, 'asset_builds': 0, 'paid_API_calls': 0,
         'evidence_sha256': {name: sha(NS / name) for name in files if (NS / name).is_file()}})
    manifest = NS / 'CONTENT_MANIFEST.json'
    rows = [{'path': path.relative_to(NS).as_posix(), 'sha256': sha(path), 'bytes': path.stat().st_size}
            for path in sorted(NS.rglob('*')) if path.is_file() and path != manifest]
    if any(row['path'].endswith('.pyc') for row in rows):
        raise ValueError('generated_bytecode_must_stay_outside_evidence')
    save(manifest, {'count': len(rows), 'files': rows, 'self_excluded': True})
    print('Sealed', len(rows) + 1, sha(manifest), 'passed', passed)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('archive', 'export', 'finalize'))
    globals()[parser.parse_args().action]()
