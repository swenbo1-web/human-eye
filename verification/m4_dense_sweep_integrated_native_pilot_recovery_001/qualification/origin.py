"""Read the immutable, published qualification source for the recovery batch."""

from hashlib import sha256
import json
from pathlib import Path
from subprocess import check_output
from zipfile import ZipFile


HERE = Path(__file__).resolve().parent
NS = HERE.parent
OLD_NS = NS.parent / 'm4_dense_sweep_integrated_native_pilot_001'
OLD_ROOT = Path('D:/he_m4_dense_sweep_integrated_native_pilot_001')
OLD_COMMIT = '8a7ff397efd99fb5474c3018a36444db36f13395'
OLD_FREEZE = '5145456e2a8dbd272800a70e5e0b9ea9402e034592a29d8008f26367579f3aad'
OLD_ARCHIVE = '018c22641c8e539aa42ba0c4e36d324178f90699877f3c15504c363d1769bc09'
OLD_REJECT = 'actual_owned_raster_accounting_changed'
ASSET = '219541e921666ddf6c406507afb5e59168415a14b8ea7b3d8eca28c6dacbe12f'
LABELS = ('QN', 'QP')
FORMAL = ('N1', 'P1')


def require(value, reason):
    if not value:
        raise ValueError(reason)


def digest(raw):
    return {'bytes':len(raw), 'sha256':sha256(raw).hexdigest()}


def pin(path):
    path = Path(path).resolve(strict=True)
    return {'path':str(path), **digest(path.read_bytes())}


def read(path):
    return json.loads(Path(path).read_bytes())


def check_archived_source():
    archive = OLD_NS / 'ORIGINAL_RUNTIME.zip'
    index = OLD_NS / 'RAW_INDEX.json'
    freeze = OLD_NS / 'FROZEN.json'
    for path in (archive, index, freeze):
        relative = path.relative_to(NS.parent.parent).as_posix()
        require(path.read_bytes() == check_output(['git','show',f'{OLD_COMMIT}:{relative}'],
                                                 cwd=NS.parent.parent), f'old_Git_artifact_changed/{path.name}')
    idx = read(index)
    require(pin(freeze)['sha256'] == idx['freeze_sha256'] == OLD_FREEZE
            and pin(archive)['sha256'] == idx['archive']['sha256'] == OLD_ARCHIVE
            and archive.stat().st_size == idx['archive']['bytes'] == 2002049
            and idx['member_count'] == 736, 'old_freeze_or_archive_changed')
    require(idx['slots']['QN']['qualified'] is True and idx['slots']['QP']['qualified'] is False
            and all(idx['slots'][label] == {'owned':'unrun','models':0} for label in FORMAL),
            'published_original_qualification_or_formal_denominator_changed')
    paths = sorted(path for path in OLD_ROOT.rglob('*') if path.is_file())
    have = {'runtime/'+path.relative_to(OLD_ROOT).as_posix():path for path in paths}
    require(set(have) == idx['members'].keys(), 'old_runtime_member_roster_changed')
    with ZipFile(archive) as bundle:
        require(len(bundle.namelist()) == 736 and set(bundle.namelist()) == have.keys(),
                'old_archive_member_roster_changed')
        for name, path in have.items():
            data = bundle.read(name)
            require(path.resolve(strict=True).is_relative_to(OLD_ROOT.resolve())
                    and digest(data) == idx['members'][name] and path.read_bytes() == data,
                    f'old_archive_or_disk_member_changed/{name}')
    require(not any((OLD_ROOT/'slots'/label).exists() for label in FORMAL)
            and not (OLD_ROOT/'preflight/QP_CLOSED_GATE.json').exists(),
            'unexpected_original_formal_or_replaced_QP_gate')
    return {'commit':OLD_COMMIT,'freeze':pin(freeze),'archive':pin(archive),'index':pin(index),
            'member_count':len(have),'original_slots':idx['slots']}


def checked_publication(label, result, publication, result_digest):
    phase = result['group'],result['phase']
    source = result['asset_sha256']
    owner = result['owner_close']
    close = result['closure_verification']
    require(result['label'] == publication['label'] == label and phase == (label[-1],'qualification')
            and result_digest == publication['result_sha256'] and result['freeze_sha256'] == OLD_FREEZE
            and source == ASSET and result['status'] == publication['status'] == 'completed'
            and publication['owned_budget_passed'] is True and result['model_consumers'] == result['paid_API_calls'] == 0,
            'old_qualification_publication_binding_changed/'+label)
    require(close['passed'] and close['status'] == 'ready_closed' and owner['confirmed']
            and not owner['errors'] and not owner['transport_errors']
            and close['mcp_closure_required'] is (label=='QP')
            and result['independent_before_after']['passed'] and result['diagnostic_close']['confirmed']
            and result['diagnostic_close']['exit_code'] == 0,
            'old_owned_or_worker_close_changed/'+label)
    require(result['ready_ns'] <= result['cleanup_started_ns'] <= publication['published_ns']
            < result['owned_deadline_ns'], 'old_qualification_published_outside_deadline/'+label)


def read_qualifiers():
    journal_path = OLD_ROOT/'preflight/SEQUENCE.jsonl'
    journal = [json.loads(row) for row in journal_path.read_bytes().splitlines()]
    require([(row['event'], row['label']) for row in journal] ==
            [('start','QN'),('publication','QN'),('qualification_passed','QN'),
             ('start','QP'),('publication','QP'),('blocked','QP')]
            and journal[-1]['reason'] == OLD_REJECT and journal[-1]['remaining'] == list(FORMAL),
            'old_sequence_and_exact_QP_rejection_required')
    results, publications = {}, {}
    for label, start, published in (('QN',journal[0],journal[1]),('QP',journal[3],journal[4])):
        slot = OLD_ROOT/'slots'/label
        raw = slot/'SLOT_RESULT.json'
        receipt = slot/'SLOT_PUBLICATION.json'
        result, publication = read(raw),read(receipt)
        checked_publication(label,result,publication,pin(raw)['sha256'])
        require(start['freeze_sha256'] == OLD_FREEZE and start['stamp_ns'] <= result['ready_ns']
                and published['result_sha256'] == publication['result_sha256'] and published['exit_code'] == 0
                and published['model_consumers'] == 0 and published['safe_to_continue'] is True,
                'old_sequence_publication_detached/'+label)
        results[label],publications[label] = result,publication
    gate_path = OLD_ROOT/'preflight/QN_CLOSED_GATE.json'
    qn_proof = OLD_ROOT/'preflight/QN_CLOSED_PROOF.json'
    gate = read(gate_path)
    require(gate['passed'] is True and gate['freeze_sha256'] == OLD_FREEZE and read(qn_proof)['passed'] is True
            and gate['result_sha256'] == publications['QN']['result_sha256']
            and gate['proof_sha256'] == pin(qn_proof)['sha256'] == journal[2]['proof_sha256']
            and publications['QN']['published_ns'] <= gate['verified_ns'] < results['QN']['owned_deadline_ns'],
            'old_QN_pass_not_at_original_time')
    return results, publications, {'sequence':pin(journal_path),'QN_gate':pin(gate_path),'QN_proof':pin(qn_proof),
                                  'QP_rejected':journal[-1]}
