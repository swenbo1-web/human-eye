"""Replay the two closed qualifiers without promoting the historical rejection."""

from copy import deepcopy
import json
from pathlib import Path
from runpy import run_path
import sys


HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
from origin import (LABELS, OLD_NS, OLD_REJECT, OLD_ROOT, check_archived_source, checked_publication,
                    digest, pin, read, read_qualifiers, require)


V = HERE.parents[1]
PRODUCT = V/'m3_whole_object_rounded_witness_compat_001/install/PRODUCT_RUN_BINDING.json'
DEPENDENCIES = V/'m5_harness_recovery_001/SHARED_DEPENDENCY.json'
CONTROLS = V/'m1_region_task_witness_image_path_001/checks/controls.py'


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',',':'), allow_nan=False).encode()


def original_checker():
    for path in (read(PRODUCT)['dependency_root'], read(DEPENDENCIES)['dependency_root']):
        if path not in sys.path:
            sys.path.insert(0,path)
    path = OLD_NS/'qualification/closed.py'
    exact, = [item for item in read(OLD_NS/'FROZEN.json')['direct_inputs']
              if Path(item['path']).resolve() == path.resolve()]
    require(pin(path) == exact, 'original_qualification_checker_changed')
    return run_path(str(path))


def rejected(action, expected):
    try:
        action()
    except ValueError as error:
        require(str(error) == expected, f'negative_rejected_for_different_reason/{error}')
        return str(error)
    raise ValueError('negative_control_unexpectedly_accepted/'+expected)


def audit():
    source = check_archived_source()
    results, publications, history = read_qualifiers()
    settlement = run_path(str(HERE/'budget.py'))['verify'](OLD_ROOT)
    require(settlement['passed'] is True
            and settlement['historical_total'] == {'blender':2,'rasters':5,'business':10,'models':0}
            and [(settlement['by_slot'][label]['raster_actual'],
                  settlement['by_slot'][label]['cumulative_raster_actual']) for label in LABELS] == [(2,2),(3,5)],
            'owner_raster_reconciliation_failed')
    checker = original_checker()
    verify = checker['verify']
    original_failure = rejected(lambda: verify(OLD_ROOT/'slots/QP',results['QP']), OLD_REJECT)
    originals = {}
    for label, expected, cumulative in (('QN',2,2),('QP',3,5)):
        original = results[label]
        current = original['budget']['slots'][label]['raster_actual']
        require(current == expected and original['budget']['counts']['all_raster_actual'] == cumulative,
                'original_current_and_batch_counts_disagree/'+label)
        copied = deepcopy(original)
        copied['budget']['counts']['all_raster_actual'] = current
        checked = verify(OLD_ROOT/'slots'/label,copied)
        require(checked['passed'] is True and checked['rasters'] == current
                and len(checked['proof']['witnesses']) == 2
                and all(stage['exact'] for item in checked['proof']['CLI'].values() for stage in item['stages']),
                'original_geometry_path_or_fixed_CLI_recheck_failed/'+label)
        if label == 'QN':
            require(canonical(checked) == canonical(read(history['QN_proof']['path'])),
                    'original_QN_granted_proof_changed')
        slot = OLD_ROOT/'slots'/label
        originals[label] = {
            'result':pin(slot/'SLOT_RESULT.json'),'publication':pin(slot/'SLOT_PUBLICATION.json'),
            'raster_actual':current,'batch_raster_actual_at_publication':cumulative,
            'published_ns':publications[label]['published_ns'],'original_owned_deadline_ns':original['owned_deadline_ns'],
            'closed_geometry':checked,
        }
    return {'passed':True,'original':source,'original_history':history,'old_QP_reproduction':original_failure,
            'slots':originals,'raster_settlement':settlement,'reused_qualification_starts':2,
            'reused_qualification_business':10,'reused_qualification_rasters':5,
            'old_qualified':1,'old_formal_unrun':2,'new_qualification_starts':0}


def scope_control():
    """Swap only the equal-length local SCENE frame index in the actual QP wire."""
    checker = original_checker()
    slot = OLD_ROOT/'slots/QP'
    calls = checker['public_records'](slot,read(slot/'SLOT_RESULT.json'),
                                    ('render_local','human_eye_scene_observe','read_images','human_eye_scene_observe'))
    producer,_ = checker['PRIOR']['product_result'](slot,calls[1],1)
    receipt = read(slot/'client/call_02/RECEIPT.json')
    req = calls[1]['request']
    res = read(slot/'client/call_02/RESPONSE.json')
    _,raw = checker['PRIOR']['rpc_pair'](slot/'client/transport',receipt,req,res)
    module = checker['VISUAL']['W']
    source = read(slot/'TERMINAL_SOURCE.json')
    original_verifier = checker['VISUAL']['verify_product']
    first = original_verifier(slot,json.loads(raw),producer,source)
    mutated,offset = run_path(str(CONTROLS))['mutate_frame_index'](
        raw,{'public_witnesses':first['scoped_public_witnesses']})
    reason = rejected(lambda: original_verifier(slot,json.loads(mutated),producer,source),
                      module['WITNESS_BINDING_ERROR'])
    return {'actual_QP_RX_sha256':digest(raw)['sha256'], 'bytes':len(raw), 'mutated_bytes':len(mutated),
            'offset':offset,'original':raw[offset:offset+1].decode(),'changed':mutated[offset:offset+1].decode(),
            'rejected_for':reason}


def negative_publication_controls():
    results, pubs, _ = read_qualifiers()
    label = 'QP'
    current, published = results[label], pubs[label]
    result_digest = pin(OLD_ROOT/'slots/QP/SLOT_RESULT.json')['sha256']
    bad_close = deepcopy(current)
    bad_close['closure_verification']['passed'] = False
    overdue = {**published, 'published_ns':current['owned_deadline_ns'] + 1}
    wrong_binding = {**published, 'result_sha256':'0'*64}
    return {
        'bad_original_close':rejected(lambda: checked_publication(label,bad_close,published,result_digest),
                                      'old_owned_or_worker_close_changed/QP'),
        'late_original_publication':rejected(lambda: checked_publication(label,current,overdue,result_digest),
                                             'old_qualification_published_outside_deadline/QP'),
        'wrong_publication_digest':rejected(lambda: checked_publication(label,current,wrong_binding,result_digest),
                                            'old_qualification_publication_binding_changed/QP'),
    }
