"""Derive the fixed score from the original, already closed replay slots."""

from pathlib import Path
from runpy import run_path
from statistics import median


HERE = Path(__file__).resolve().parent
BATCH = run_path(str(HERE/'batch.py'))
RUN = BATCH['RUN']
REPLAY = run_path(str(BATCH['REPLAY']))
read, require, pin, write = (BATCH[k] for k in ('read', 'require', 'pin', 'write'))


def score():
    freeze_digest = BATCH['verify_freeze']()
    journal = RUN/'FORMAL_SEQUENCE.jsonl'
    sequence = [REPLAY['json'].loads(line) for line in journal.read_bytes().splitlines()]
    order = REPLAY['ORDER']
    require([(r['event'],r['label']) for r in sequence] ==
            [(event,label) for label in order for event in ('start','closed')],
            'expected_complete_original_slot_sequence')
    arms = {}
    for i,label in enumerate(order):
        start,end = sequence[2*i:2*i+2]
        control = label in ('AN','BP')
        path = RUN/('controls' if control else 'arms')/label/'SUMMARY.json'
        require(start['perf_ns'] < end['perf_ns'] and end['summary'] == pin(path),
                'original_slot_identity_changed/' + label)
        receipt = read(path)
        close = read(path.parent/'mcp/HELD_CLOSE.json')
        binding = read(BATCH['BINDINGS']['A' if label.startswith(('N','A')) else 'B'])
        rows = receipt['requests']
        require(receipt['label'] == label and receipt['passed'] is True
                and receipt['held_close'] == pin(path.parent/'mcp/HELD_CLOSE.json')
                and close['confirmed'] and close['production_eof_and_exit_verified']
                and close['process_handle_closed'] and close['exit_code'] == 0
                and receipt['binding'] == binding['source_sha256']
                and receipt['actual_Blender'] == receipt['actual_models'] == 0
                and len(rows) == (8 if control else 4),
                'original_slot_contract_failed/' + label)
        rejected = [r for r in rows if 'error' in r]
        require([r['stage'] for r in rejected] == (['stale'] if control else [])
                and all(r['raster'] == 0 for r in rejected), 'original_rejection_changed/' + label)
        arms[label] = receipt

    stage = REPLAY['SELECTION_STAGE']
    pairs = {}
    for a,b in REPLAY['PAIRS']:
        old,new = arms[a], arms[b]
        rows = []
        for prev,now in zip(old['requests'],new['requests'],strict=True):
            require(all(prev[key] == now[key] for key in ('stage','ref','measurement','capture_state')),
                    'A_B_selected_measurement_binding_changed')
            rows.append({'stage':prev['stage'],'probe_ns':now['stage_ns'].get(stage,0),
                         'service_ns':[prev['service_ns'],now['service_ns']],
                         'capture_ns':[prev['capture_ns'],now['capture_ns']]})
        pairs[f'{a}/{b}'] = {'rows':rows,'window_ns':[old['window_ns'],new['window_ns']]}
    controls = {r['stage']:r['probe']['elapsed_ns'] for r in arms['BP']['requests']
                if 'error' not in r and r['probe'] is not None}
    require(tuple(controls) == ('upper','lower','holdout'), 'positive_selection_controls_missing')
    selection = {side:median(q['rows'][n]['probe_ns'] for q in pairs.values())
                 for n,side in enumerate(('left','right'))}
    limits = BATCH['LIMITS']
    passed = (0 < selection['left'] <= limits['left_median_selection_ns']
              and 0 < selection['right'] <= limits['positive_selection_ns']
              and all(0 < t <= limits['positive_selection_ns'] for t in controls.values()))
    out = RUN/'DERIVED_REPLAY_SCORE.json'
    require(not out.exists(), 'derived_replay_score_already_exists')
    write(out, {'passed':passed, 'original_aggregation_exit_code':1, 'original_error_stage':'BP/stale',
                'original_error':"KeyError: 'probe'", 'freeze_sha256':freeze_digest,
                'original_journal':pin(journal), 'scorer':pin(__file__), 'arms':arms, 'pairs':pairs,
                'selection_median_ns':selection, 'SCENE_positive_control_ns':controls,
                'actual_Blender':0, 'actual_models':0, 'actual_mcp_slots':len(arms),
                'actual_mcp_requests':sum(len(a['requests']) for a in arms.values()),
                'actual_rasters':sum(r['raster'] for a in arms.values() for r in a['requests']),
                'expected_rejections':2, 'replacement_slots':0, 'real_model_use_untested':True})
    print(out, 'passed' if passed else 'selection_budget_exceeded')
    return passed


if __name__ == '__main__':
    raise SystemExit(0 if score() else 1)
