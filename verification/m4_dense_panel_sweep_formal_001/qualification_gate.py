"""Bind the previous successful QP and the only new native qualification."""

from hashlib import sha256
from pathlib import Path
import sys
from zipfile import ZipFile


NS = Path(__file__).resolve().parent
sys.path.insert(0, str(NS / 'harness'))
from common import EXTERNAL, PRODUCT_BINDING, read, save, sha


V = NS.parent
COMPACT = V / 'm4_dense_region_brief_001'
DENSE = V / 'm4_dense_panel_sweep_001'
QP_RUN = Path('D:/he_m4_dense_region_brief_001')
PRODUCT_GIT = '278fd3003758299379f6d87b7e9174c577f5bb88'
SOURCE = '6e8663feb57b630048fe919141cfcabbae4ae2365df1f80da693382c360b65e8'
WHEEL = '46664941fbd83be143ae4866486d1a76593c82c7331a4c9926a600189c8ee347'
ASSET = '2d7c48f01665588bd7cfc93280ea50b559f4dc08196738c504ea56c88c75a164'
TRUTH = 'd4d05b3ffb713331c4348852335b9d17ebfe9690c7013062d39b82bb8087700a'
QP_FREEZE = 'b0660b1eb64afec1c6f8a6c78e208dbe194c117efc9a36ccbae30213186a0f50'
QP_REVIEW = 'dfb3caf6a4709c667bb13b7f592cfcda81b482b2708d87185f26bfcffe72824a'
QP_DECISION = '7930e33eebefc57d2bf728f2ac466c841bb0312671ff63d192582a5f2dca3840'
QP_INDEX = 'd22eae5a40a75a8b6dda86fca05b16c48c09a4f1a030bbbe6b0cc46715e2b645'
QP_RESULT = 'ab3ac0b8c307902ebac7bba66e0d1597f49fde0ae7b0bffd15ab30952bf68ca9'
QP_PUBLICATION = '596d7628d46fdc175e048f3893de9507bfcfabbfedac09f3cee0c3fbf0acf163'
QP_ARCHIVE = '0afc0e820eaef19efcf5c2c4c502191c3d69e0852d9f6d732da04312713deb42'
OLD_DECISION = '52af3750cafb7fba7a40449600d64940527621924768541c570264dd31957bac'


def external_qp():
    root = QP_RUN / 'slots/QP'
    result_path = root / 'SLOT_RESULT.json'
    publication_path = root / 'SLOT_PUBLICATION.json'
    review_path = COMPACT / 'checks/LIVE_REVIEW.json'
    archive_path = QP_RUN / 'ORIGINAL_RUNTIME.zip'
    old_path = DENSE / 'DECISION.json'
    index_path = COMPACT / 'RUNTIME_INDEX.json'
    for path, digest in (
        (result_path, QP_RESULT), (publication_path, QP_PUBLICATION), (review_path, QP_REVIEW),
        (archive_path, QP_ARCHIVE), (COMPACT / 'DECISION.json', QP_DECISION), (COMPACT / 'FROZEN.json', QP_FREEZE),
        (index_path, QP_INDEX), (DENSE / 'truth/CURRENT_TRUTH.json', TRUTH), (old_path, OLD_DECISION),
    ):
        if sha(path) != digest:
            raise ValueError('external_qualification_original_changed/' + str(path))
    result, pub, review = (read(path) for path in (result_path, publication_path, review_path))
    decision = read(COMPACT / 'DECISION.json')
    old = read(old_path)
    binding = read(PRODUCT_BINDING)
    index = read(index_path)
    counts = result['budget']['counts']
    if (decision['passed'] is not True or decision['original_slot_sha256'] != QP_RESULT
            or decision['evidence_sha256']['checks/LIVE_REVIEW.json'] != QP_REVIEW
            or review['passed'] is not True or review['CLI']['passed'] is not True
            or review['wire']['body_UTF8_bytes'] != 8242
            or review['independent_truth_sha256'] != TRUTH or review['slot_result_sha256'] != QP_RESULT
            or review['publication_sha256'] != QP_PUBLICATION or review['freeze_sha256'] != QP_FREEZE
            or review['installed_product'] != {'commit': PRODUCT_GIT, 'source_sha256': SOURCE,
                    'wheel_sha256': WHEEL, 'runtime_sources_verified': 143}
            or result['label'] != 'QP' or pub['label'] != 'QP' or pub['result_sha256'] != QP_RESULT
            or pub['status'] != result['status'] or result['status'] != 'completed'
            or result['freeze_sha256'] != QP_FREEZE or result['asset_sha256'] != ASSET
            or result['model_consumers'] != 0 or result['paid_API_calls'] != 0
            or result['product_binding_sha256'] != sha(PRODUCT_BINDING) or result['product_source_sha256'] != SOURCE
            or result['independent_before_after']['passed'] is not True
            or binding['preparation_git'] != PRODUCT_GIT or binding['source_sha256'] != SOURCE
            or binding['wheel_sha256'] != WHEEL or len(binding['source_manifest']) != 143
            or decision['formal_model_slots_run'] != 0 or decision['native_qualifications_run'] != 0
            or (counts['Blender_start_attempts'], counts['business_admissions'], counts['all_raster_actual'],
                counts['consumer_admissions']) != (1, 1, 2, 0)
            or old['product_qualification_passed'] is not False or old['actual_formal_model_slots'] != 0
            or any(row['status'] != 'unrun' for row in old['slots'] if row['label'] != 'QP')
            or index['archive']['sha256'] != QP_ARCHIVE or Path(index['archive']['path']).resolve() != archive_path.resolve()):
        raise ValueError('successful_external_QP_does_not_admit_the_current_fixed_product')
    original_wire = root / 'mcp/rpc_04/RX.bin'
    if sha(original_wire) != review['wire']['RX_sha256'] or original_wire.stat().st_size != review['wire']['RX_bytes']:
        raise ValueError('external_QP_original_wire_changed')
    members = (result_path, publication_path, original_wire, root / 'TERMINAL_SOURCE.json',
               root / 'initial_capture/TERMINAL_SOURCE.json')
    indexed = {item['path']: item for item in index['files']}
    with ZipFile(archive_path) as bundle:
        for path in members:
            name = path.relative_to(QP_RUN).as_posix()
            raw = bundle.read(name)
            if (indexed[name]['sha256'] != sha256(raw).hexdigest()
                    or indexed[name]['bytes'] != len(raw) or raw != path.read_bytes()):
                raise ValueError('external_QP_actual_original_not_equal_to_archive/' + name)
    data = {'label': 'QP', 'passed': True, 'asset_sha256': ASSET, 'truth_sha256': TRUTH,
            'product_git': PRODUCT_GIT, 'product_source_sha256': SOURCE,
            'product_binding_sha256': sha(PRODUCT_BINDING), 'prior_freeze_sha256': QP_FREEZE,
            'result_sha256': QP_RESULT, 'publication_sha256': QP_PUBLICATION, 'review_sha256': QP_REVIEW,
            'original_archive_sha256': QP_ARCHIVE, 'result_path': str(result_path.resolve()),
            'publication_path': str(publication_path.resolve()), 'review_path': str(review_path.resolve()),
            'original_archive_path': str(archive_path.resolve())}
    pins = [*members, review_path, archive_path, COMPACT / 'DECISION.json', index_path, old_path]
    return data, pins


def finalize_gate():
    from admission import publication, verify_freeze

    frozen_path = NS / 'FROZEN.json'
    frozen = verify_freeze(frozen_path)
    qp, _ = external_qp()
    if read(frozen_path)['external_qp'] != qp:
        raise ValueError('external_qualification_freeze_binding_changed')
    result, pub = publication('QN', frozen)
    review_path = NS / 'qualification/NATIVE_REVIEW.json'
    review = read(review_path)
    if (review['freeze_sha256'] != frozen or review['slot_result_sha256'] != pub['result_sha256']
            or review['publication_sha256'] != sha(EXTERNAL / 'slots/QN/SLOT_PUBLICATION.json')
            or result['asset_sha256'] != ASSET or result['model_consumers'] != 0):
        raise ValueError('native_qualification_review_lost_current_slot_binding')
    counts = (result.get('budget') or {}).get('counts', {})
    passed = (review['passed'] is True and pub['status'] == 'completed'
              and result.get('independent_before_after', {}).get('passed') is True
              and counts.get('Blender_start_attempts') == 1 and counts.get('consumer_admissions') == 0
              and 2 <= counts.get('all_raster_actual', 0) == counts.get('all_raster_upper') <= 6)
    native = {'label': 'QN', 'passed': passed, 'result_sha256': pub['result_sha256'],
              'publication_sha256': review['publication_sha256'], 'review_sha256': sha(review_path)}
    reused = {key: qp[key] for key in ('label', 'passed', 'result_sha256', 'publication_sha256', 'review_sha256')}
    save(NS / 'QUALIFICATION.json', {'schema': 'm4-dense-panel-sweep-formal-qualification-v1',
         'passed': passed, 'freeze_sha256': frozen, 'slots': [native, reused], 'external_QP_reused': True})
    print('Native qualification gate', passed, review.get('reason'), frozen)
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(finalize_gate())
