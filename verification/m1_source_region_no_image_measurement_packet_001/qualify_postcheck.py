"""Recheck original receipts with same-endpoint baseline pairing."""
import json
from hashlib import sha256
from pathlib import Path

from qualify import ARMS, CASES, NS, ROOT, read, require, save, stable_standard_body


def body(row):
    raw = Path(row['public_path']).read_bytes()
    require(len(raw) == row['public_UTF8_bytes'], 'actual text count changed')
    return raw.decode('utf8')


def verify_compatibility():
    baseline_evidence = 'preflight_02'
    arms = (*ARMS, baseline_evidence)
    indexes = {arm:read(ROOT/arm/'INDEX.json') for arm in arms}
    planned = indexes[ARMS[0]]['planned']
    require(all(index['planned'] == planned and index['completed'] and not index['unrun']
                for index in indexes.values()), 'incomplete or different frozen case roster')
    rows = []
    for case in planned:
        roots = {arm:ROOT/arm/'cases'/case for arm in arms}
        calls = {arm:read(root/'CASE.json')['calls'] for arm,root in roots.items()}
        for arm, root in roots.items():
            held = read(root/'HELD_EOF.json')
            close, eof = held['held_close'], held['worker_eof']
            require(held['stdout_eof_observed'] and held['input_eof_observed'] and eof['archived_inputs_unchanged']
                    and close['exit_code']==0 and close['process_handle_closed'] and close['reader_stopped']
                    and eof['host_attempts']==eof['socket_attempts']==eof['blocked_old_writes']==eof['actual_new_rasters']==0,
                    'unsafe read-only replay closure', arm, case)
        for base, stock, evidence, old_evidence in zip(*(calls[arm] for arm in arms), strict=True):
            group = (base,stock,evidence,old_evidence)
            require(all(row['label']==base['label'] and row['arguments']==base['arguments']
                        and row['matches_expected_error'] and row['expected_error']==base['expected_error']
                        for row in group), 'case inputs or outcomes differ', case, base['label'])
            require(all(row['images']==base['images'] for row in group), 'reply image bytes changed', case)
            texts = [body(row) for row in group]
            # Old configuration reuse, EOF and same parameters are proved above.
            # Only generated source-region request trace identifiers can differ in successful full results.
            if base['expected_error']:
                outcomes = [json.loads(text) for text in texts]
                require(all(item==outcomes[0] for item in outcomes), 'public rejection changed', case, base['label'])
                if base['label']=='stale_ref':
                    require(outcomes[0]['error']=='source_region_ref_document_epoch_changed',
                            'valid old epoch must reach current-reference rejection')
            else:
                left = stable_standard_body(texts[0])[0]
                right = stable_standard_body(texts[1])[0]
                require(left==right, 'standard reply changed outside trace identifiers', case, base['label'])
                if case not in CASES:
                    require(stable_standard_body(texts[2])[0]==stable_standard_body(texts[3])[0],
                            'same-mode evidence reply changed', case, base['label'])
            rows.append({'case':case,'call':base['label'],'expected_rejection':base['expected_error'],
                         'same_mode_standard':True,'same_mode_evidence':True if case not in CASES or base['expected_error'] else None,
                         'bytes':{arm:row['public_UTF8_bytes'] for arm,row in zip(arms,group,strict=True)}})
    for arm, index in indexes.items():
        for case in planned:
            path = ROOT/arm/'cases'/case/'CATALOGUE.json'
            catalogue = read(path)['result']['tools']
            other = read(ROOT/('baseline_standard' if arm=='candidate_standard' else baseline_evidence)
                         /'cases'/case/'CATALOGUE.json')['result']['tools']
            if arm=='candidate_standard':
                require(catalogue==other,'standard catalogue changed')
            if arm=='candidate_evidence':
                copies = [item.copy() for item in catalogue]
                observe, = [item for item in copies if item['name']=='human_eye_scene_observe']
                old, = [item for item in other if item['name']=='human_eye_scene_observe']
                note = observe['description'].removeprefix(old['description'])
                require(note.startswith(' A completed source_region measurement of only surface_proximity ')
                        and 'include_image=false' in note and 'standard endpoint with full' in note,
                        'incorrect evidence-mode source_region guidance')
                observe['description'] = old['description']
                require(copies==other, 'unrelated catalogue field changed')
    return {'paired_calls':len(rows),'paired_expected_rejections':sum(row['expected_rejection'] for row in rows),
            'paired_successes':sum(not row['expected_rejection'] for row in rows),'rows':rows,
            'formal_held_processes':len(planned)*len(ARMS),'baseline_evidence_preflight_processes':len(planned)}


def conclude():
    failure = read(ROOT/'qualification/ORIGINAL_GATE_FAILURE.json')
    require(not failure['passed'] and failure['observed_source'].startswith('active_observation'),
            'original frozen verifier failure missing')
    output = ROOT/'qualification_postcheck'
    output.mkdir()
    rows = []
    for case in CASES:
        checks = {}
        for detail in ('full','brief'):
            checks[detail] = {}
            for arm in ARMS:
                proof = read(ROOT/'qualification'/f'{case}_{arm}_{detail}.json')
                expected = arm=='candidate_evidence' or detail=='brief'
                require(proof['passed'] and proof['fixed_CLI']['exact_stages']==(6 if expected else 0),
                        'original positive subprocess packet did not meet its delivery contract', case, arm, detail)
                if expected:
                    require(proof['actual_body_utf8_bytes']<=10800, 'positive body exceeded frozen cap')
                checks[detail][arm] = {
                    'body_bytes':proof['actual_body_utf8_bytes'],'body_sha256':proof['actual_body_sha256'],
                    'stdio_RX_bytes':proof['stdio_receipt']['RX_bytes'],'stdio_RTT_ns':proof['stdio_receipt']['elapsed_ns'],
                    'fixed_CLI_exact_stages':proof['fixed_CLI']['exact_stages'],
                    **proof['execution_timing'],
                }
        rows.append({'case':case,**checks})
    protection = verify_compatibility()
    comparison = {
        'passed':True,'original_frozen_verifier_passed':False,'comparison_corrected_only':True,
        'frozen_sha256':sha256((NS/'FROZEN.json').read_bytes()).hexdigest(),
        'scored_actual_packets':18,'candidate_evidence_CLI_exact_checks':36,'cases':rows,
        'compatibility':protection,'additional_replay_processes':0,
    }
    save(output/'QUALIFICATION.json', comparison)
    print(json.dumps({'passed':True, 'formal_held_processes':protection['formal_held_processes'],
                      'paired_calls':protection['paired_calls'],'expected_rejections':protection['paired_expected_rejections']}))


if __name__=='__main__':
    conclude()
