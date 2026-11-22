"""Exercise the formal scorer and new ledger against held actual records before launch."""

from copy import deepcopy
import json
from pathlib import Path
from runpy import run_path
from zipfile import ZipFile

HERE = Path(__file__).resolve().parent
L = run_path(str(HERE / 'ledger.py'))
F, C = L['F'], L['C']
V = HERE.parents[1]
PRODUCT = V / 'm1_region_task_first_packet_consumption_holdout_recovery_001'
NATIVE = V / 'perf050_dense_micro_surface_holdout_recovery_001'
P_SLOT = Path('D:/he_m1_region_task_first_packet_consumption_holdout_recovery_001/slots/B1')
N_SLOT = Path('D:/he_perf050_dense_micro_surface_holdout_recovery_001/slots/N1')
require, read, pin = (F[key] for key in ('require', 'read', 'pin'))


def sealed_slots(namespace, slot, relatives):
    index = read(namespace / 'RAW_INDEX.json')
    archive = namespace / index['archive']['name']
    archive_pin = pin(archive)
    require(all(archive_pin[key] == index['archive'][key] for key in ('bytes', 'sha256')),
            'historical_raw_archive_not_exact')
    pinned = [pin(namespace / 'RAW_INDEX.json'), archive_pin]
    with ZipFile(archive) as bundle:
        for relative in relatives:
            path = slot / relative
            found = pin(path)
            member = f'runtime/slots/{slot.name}/{relative}'
            require(all(found[key] == index['members'][member][key] for key in ('bytes','sha256'))
                    and path.read_bytes() == bundle.read(member), 'historical_raw_member_not_exact/' + member)
            pinned.append(found)
    return pinned


def wrong_scene_view():
    response = read(P_SLOT / 'owner/tool_01/RESPONSE.json')
    producer = read(P_SLOT / 'product_full/call_001/SERVICE_RESULT.json')
    view = response['result']['content'][0]['text']
    body = json.loads(view)
    frames, scopes = [F['W']['records'](body[key]) for key in ('frames', 'scopes')]
    witnesses = F['W']['records'](body['witnesses'])
    local, = [(index, row) for index, row in enumerate(witnesses)
              if frames[row['frame_index']]['view_name'] == 'SCENE'
              and scopes[frames[row['frame_index']]['scope_index']]['scope_id'] != 'global']
    global_index, = [index for index, frame in enumerate(frames) if frame['view_name'] == 'SCENE'
                     and scopes[frame['scope_index']]['scope_id'] == 'global']
    bad = deepcopy(response)
    body['witnesses']['rows'][local[0]][body['witnesses']['columns'].index('frame_index')] = global_index
    raw = json.dumps(body, ensure_ascii=False, separators=(',', ':'))
    require(len(view.encode()) == len(raw.encode()) and raw != view, 'scope_substitution_is_not_equal_length')
    bad['result']['content'][0]['text'] = raw
    try:
        F['W']['verify_public_witnesses'](bad, producer)
    except ValueError as issue:
        require(str(issue) == F['W']['WITNESS_BINDING_ERROR'], 'scoped_wrong_frame_wrong_rejection_reason')
        return {'rejected': True, 'equal_length_bytes': len(raw.encode()), 'reason': str(issue)}
    raise ValueError('scoped_wrong_frame_accepted')


def verify():
    equivalent = ('SLOT_RESULT.json', 'SLOT_PUBLICATION.json', 'TERMINAL_SOURCE.json',
                  'DEVICE_EVIDENCE.json', 'consumer/PUBLIC_FINAL.txt', 'consumer/stdout.raw.bin')
    raw = sealed_slots(PRODUCT, P_SLOT, (*equivalent, 'owner/tool_01/RESPONSE.json',
                      'product_full/call_001/SERVICE_RESULT.json'))
    raw += sealed_slots(NATIVE, N_SLOT, equivalent)
    b_claim = PRODUCT / 'evidence/B1_CLAIMS.json'
    p = L['summarize'](P_SLOT, C['digest'](PRODUCT/'FROZEN.json'), F['ORIGINAL']/'fixture/TRUTH.json',
                       F['ORIGINAL_BINDING'], read(b_claim), {})
    require(p['quality']['score'] == p['quality']['planned'] == 7 and p['quality']['all_quality_passed']
            and p['evidence_error'] is None and p['cost_evidence_verified'] and not p['packet_issues']
            and len(p['product_work']['captures']) == 3
            and p['real_raster_budget']['actual'] == 3
            and p['CLI_uncached_plus_output_tokens'] == 24502
            and sum(row['repeat_same_ref_and_PNG'] for rows in p['original_PNG_transfers'].values() for row in rows) == 2
            and [row['kind'] for row in p['verified_product_facts']] ==
                ['discovery', 'occlusion', 'measurement', 'measurement'],
            'closed_historical_product_semantics_or_costs_changed')
    n = C['summarize'](N_SLOT, C['digest'](NATIVE/'FROZEN.json'))
    _, pub = F['D']['publication'](N_SLOT)
    wire = F['D']['formal_wires'](N_SLOT, pub)
    native_delivery = L['picture_transfers'](N_SLOT, wire['attempts'])
    require(n['cost_evidence_verified'] and n['input_plus_output_tokens'] == 103213
            and len(n['actual_requests']) == len(wire['attempts']) == 8
            and L['raster_charges'](N_SLOT)['actual'] == 12
            and all(row['product'] is None for row in n['actual_requests'])
            and sum(len(row) for row in native_delivery.values()) >= 2,
            'closed_historical_native_costs_or_bound_png_changed')
    code = [F['ORIGINAL']/'checks/evidence.py', NATIVE/'checks/evidence.py', NATIVE/'qualification/frame.py',
            PRODUCT/'checks/evidence.py', F['ORIGINAL']/'fixture/TRUTH.json', b_claim,
            V/'m1_region_task_witness_image_path_001/checks/evidence.py',
            V/'m4_dense_region_brief_001/checks/brief_schema.py',
            V/'m4_cross_scale_discovery_001/oracle/check_saved.py',
            V/'m4_cross_scale_live_task_formal_001/scoring/formal.py',
            V/'m4_cross_scale_live_task_formal_001/checks/review_actual_tools.py',
            V/'m1_source_region_first_packet_consumption_001/checks/score.py',
            V/'m5_observe_measure_001/oracle.py',
            V/'perf050_dense_micro_surface_holdout_001/qualification/native.py',
            V/'perf050_readonly_product_pilot_001/consumer/costs.py']
    return {'passed': True, 'actual_models_started': 0, 'actual_Blender_started': 0,
            'historic_actual_product': {'quality': 7, 'calls': 7, 'rasters': 3, 'repeated_bound_png': 2,
                                        'row_measurements': 2, 'witness_and_reopen': True},
            'historic_actual_native': {'calls': 8, 'rasters': 12, 'original_cost_binding': True},
            'wrong_scope_same_view_tamper': wrong_scene_view(),
            'source_pins': [*raw, *(pin(path) for path in code)]}


if __name__ == '__main__':
    output = HERE / 'ANALYSIS_PREFLIGHT.json'
    data = verify()
    with output.open('x', encoding='utf8', newline='\n') as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
    print(f'Analysis preflight passed: {output}')
