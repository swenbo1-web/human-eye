"""Independent byte and arithmetic checks over the completed fixed matrix."""
import hashlib
import json
import math
from pathlib import Path
import statistics


def read(path):
    return json.loads(path.read_bytes())


def main():
    batch = Path(__file__).resolve().parent
    run = batch / 'measurement/run_01'
    matrix = read(run / 'RESULTS.json')
    bindings = read(run / 'INPUT_BINDINGS.json')
    assert matrix['passed'] and matrix['all_planned_dispatched']
    assert matrix['performance_retries'] == 0 and not matrix['errors']
    assert [entry['case'] for entry in matrix['cases']] == bindings['schedule']
    assert len(matrix['cases']) == 36
    for path, expected in bindings['source_files'].items():
        assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == expected, path
    tables = {}
    steps = []
    business = bridge = runtimes = 0
    for case in matrix['cases']:
        source = Path(case['result'])
        session = read(source)
        assert session['passed'] and not session['errors']
        assert session['native_close']['exit_code'] == 0
        assert session['native_close']['process_reaped'] is True
        assert not session['closed']['poisoned']
        assert session['closed']['initial_geometry_fingerprint'] == session['closed']['final_geometry_fingerprint']
        if session.get('product_runtime_exit'):
            assert session['product_runtime_exit']['confirmed']
            assert session['product_runtime_exit']['exit_code'] == 0
            runtimes += 1
        wire = read(source.parent / 'native/WIRE/INDEX.json')
        for record in wire:
            folder = source.parent / 'native/WIRE' / str(record['sequence']).zfill(3)
            assert len((folder / 'REQUEST.bin').read_bytes()) == record['request_bytes']
            assert len((folder / 'RESPONSE.bin').read_bytes()) == record['response_attempted_bytes']
            assert record['response_sendall_completed'] is True
        bridge += len(wire)
        for row in session['rows']:
            assert row['tool_ns'] == row['ended_ns'] - row['started_ns']
            assert row['host_RPC'] == 1 and len(row['wire']) == 1
        business += len(session['rows'])
        asset, lane = case['case']['asset'], case['case']['lane']
        if case['case']['two_step']:
            assert [row['phase'] for row in session['rows']] == ['cold', 'selected']
            assert session['continuous_request_window_ns'] == session['rows'][1]['ended_ns'] - session['rows'][0]['started_ns']
            steps.append({'asset': asset, 'lane': lane,
                          'directory_ms': session['rows'][0]['tool_ns'] / 1e6,
                          'selected_ms': session['rows'][1]['tool_ns'] / 1e6,
                          'continuous_ms': session['continuous_request_window_ns'] / 1e6,
                          'session_ms': session['session_wall_ns'] / 1e6})
            continue
        assert len(session['rows']) == 11
        for row in session['rows']:
            key = (asset, lane, row['phase'])
            tables.setdefault(key, []).append(row)
    distributions = []
    for (asset, lane, phase), rows in sorted(tables.items()):
        durations = sorted(row['tool_ns'] for row in rows)
        assert len(rows) == (3 if phase == 'cold' else 30)
        distributions.append({'asset': asset, 'lane': lane, 'phase': phase, 'n': len(rows),
            'median_ns': statistics.median(durations),
            'p95_nearest_rank_ns': durations[math.ceil(.95 * len(durations)) - 1],
            'median_bridge_request_bytes': statistics.median(row['wire'][0]['request_bytes'] for row in rows),
            'median_bridge_response_bytes': statistics.median(row['wire'][0]['response_attempted_bytes'] for row in rows)})
    saved = read(run / 'SUMMARY.json')
    for row in distributions:
        group = saved['groups'][row['asset']][row['lane']][row['phase']]
        assert row['median_ns'] == group['tool_ns']['median']
        assert row['p95_nearest_rank_ns'] == group['tool_ns']['p95_nearest_rank']
        assert row['median_bridge_request_bytes'] == group['bridge_request_bytes']['median']
        assert row['median_bridge_response_bytes'] == group['bridge_response_bytes']['median']
    assert business == 315 and bridge == 351 and runtimes == 27
    result = {'cycle_id': 'M2-TIGHT-DIRECTORY-001', 'passed': True,
              'scope': 'independent saved raw byte counts, scheduling, exit receipts and statistical arithmetic',
              'business_RPC': business, 'all_host_RPC': bridge, 'owned_Blender_exits_verified': 36,
              'actual_Python_runtime_exits_verified': runtimes,
              'bindings_verified': len(bindings['source_files']), 'distributions': distributions,
              'continuous_two_steps': steps, 'new_performance_samples': 0}
    with (batch / 'SAVED_VERIFICATION.json').open('x', encoding='utf8', newline='\n') as output:
        json.dump(result, output, indent=2, allow_nan=False)
        output.write('\n')
    print(json.dumps({key: result[key] for key in result if key not in {'distributions', 'continuous_two_steps'}}))


if __name__ == '__main__':
    main()
