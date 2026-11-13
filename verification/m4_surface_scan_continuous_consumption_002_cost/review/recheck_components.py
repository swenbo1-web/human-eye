"""Cross-check cost components against terminal events and original clocks."""

from collections import Counter
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import statistics


HERE = Path(__file__).resolve().parent
BATCH = HERE.parent
ROOT = BATCH.parents[1]
SOURCE = ROOT / 'verification/m4_surface_scan_continuous_consumption_002'
REVIEW = Path('D:/hefe/verification/fixes/20261113_m4_surface_scan_continuous_002_quality_review')
CELLS = ('N1', 'C1', 'C2', 'N2', 'N3', 'C3')
LABELS = ('BASE', 'REPEAT', 'EDIT')
VIEWS = {'FULL': (1, 2, 3), 'BASE': (1,), 'REPEAT_EDIT': (2, 3)}


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def exact_ratio(value):
    return Fraction(value['numerator'], value['denominator'])


def main():
    checks, inputs = [], {}

    def check(label, condition):
        checks.append({'check': label, 'passed': bool(condition)})

    def source(path):
        path = Path(path).resolve()
        inputs[str(path)] = sha(path)
        return read(path)

    usage = source(BATCH / 'usage/USAGE.json')
    timing = source(BATCH / 'timing/TIMING.json')
    for name, component in (('usage', usage), ('timing', timing)):
        check(name + '_all_input_hashes', all(Path(path).is_absolute() and sha(Path(path)) == expected
              for path, expected in component['inputs_sha256'].items()))
    seal = source(REVIEW / 'QUALITY_SEAL.json')
    check('fixed_quality_seal', inputs[str((REVIEW / 'QUALITY_SEAL.json').resolve())]
          == 'ccea554353a6f0607263124d2170ef3b2094a07e222c86276f522184b7f5316c')
    judgments = source(REVIEW / 'quality/FINAL_RESULTS.json')['results']
    judged = {(row['anonymous_episode_id'], row['turn']): row for row in judgments}
    mapping = source(SOURCE / 'private/ANON_MAP.json')['rows']
    cells = {row['cell']: row for row in mapping}
    check('fixed_18_rows', [(row['cell'], row['turn_index']) for row in usage['rows']]
          == [(cell, turn) for cell in CELLS for turn in (1, 2, 3)])
    counts = {group: {'episodes': 0, 'turns': 0} for group in ('N', 'C')}
    raw_usage, clocks = {}, {}
    reported_timing = {row['cell']: row for row in timing['episodes']}
    for cell in CELLS:
        group = cell[0]
        identity = cells[cell]
        outer = source(SOURCE / 'episodes' / cell / 'FINAL_TIMING.json')
        duration = outer['business_receipts_closed_ns'] - outer['started_ns']
        check(cell + '_outer_original_integer_interval', duration == outer['full_episode_wall_ns']
              and outer['outer_valid_completion'] is True)
        counts[group]['episodes'] += outer['outer_valid_completion'] is True
        per_turn = {}
        for index, label in enumerate(LABELS, 1):
            folder = ROOT / '.m4cc2' / cell / 'c/turns' / label
            consumer = source(folder / 'CONSUMER.json')
            clock = source(folder / 'FINAL_TIMING.json')
            per_turn[index] = clock['consumer_record_closed_ns'] - clock['started_ns']
            check(cell + '_' + label + '_turn_original_interval', per_turn[index] == clock['full_turn_wall_ns']
                  and clock['accepted_success'] is True)
            events = folder / 'events.jsonl'
            inputs[str(events.resolve())] = sha(events)
            terminals = [item['event']['usage'] for item in map(json.loads, events.read_bytes().splitlines())
                         if item.get('event', {}).get('type') == 'turn.completed']
            check(cell + '_' + label + '_single_terminal', len(terminals) == 1)
            raw_usage[(cell, index)] = terminals[0]
            published = next(row for row in usage['rows'] if row['cell'] == cell and row['turn_index'] == index)
            check(cell + '_' + label + '_raw_usage_exact', terminals == consumer['raw_usage_events']
                  and terminals[0] == published['raw_usage']
                  and published['input_plus_output_tokens'] == terminals[0]['input_tokens'] + terminals[0]['output_tokens'])
            judgment = judged[(identity['anonymous_episode_id'], index)]
            good = (judgment['anonymous_turn_id'] == identity['anonymous_turn_ids'][index - 1]
                    and judgment['primary_content_classification'] == 'complete_correct'
                    and judgment['current_state_basis']['classification'] == 'sufficient'
                    and judgment['execution_classification'] == 'completed')
            check(cell + '_' + label + '_sealed_quality_map', good)
            counts[group]['turns'] += good
        clocks[cell] = {'FULL': duration, 'BASE': per_turn[1], 'REPEAT_EDIT': per_turn[2] + per_turn[3]}
        check(cell + '_timing_three_views', all(reported_timing[cell]['segments_ns'][view] == value
              for view, value in clocks[cell].items()))
    view_results = {}
    for view, turns in VIEWS.items():
        group_tokens, group_time, token_pairs, time_pairs = {}, {}, [], []
        for group in ('N', 'C'):
            fields = Counter()
            for (cell, turn), values in raw_usage.items():
                if cell[0] == group and turn in turns:
                    fields.update(values)
            group_tokens[group] = fields['input_tokens'] + fields['output_tokens']
            group_time[group] = sum(clocks[cell][view] for cell in CELLS if cell[0] == group)
            published = usage['group_aggregates'][group][view]
            check(group + '_' + view + '_reported_fields_sum', dict(fields) == published['usage_fields']
                  and group_tokens[group] == published['input_plus_output_tokens'])
        for pair in (1, 2, 3):
            totals = {group: sum(values['input_tokens'] + values['output_tokens']
                for (cell, turn), values in raw_usage.items() if cell == group + str(pair) and turn in turns)
                for group in ('N', 'C')}
            token_ratio = Fraction(totals['C'], totals['N'])
            time_ratio = Fraction(clocks['C' + str(pair)][view], clocks['N' + str(pair)][view])
            token_pairs.append(token_ratio)
            time_pairs.append(time_ratio)
            published_pair = next(row for row in usage['pair_comparisons'][view] if row['pair'] == pair)
            check(view + '_pair_' + str(pair) + '_token_originals_and_ratio',
                  published_pair['N_usage']['input_plus_output_tokens'] == totals['N']
                  and published_pair['C_usage']['input_plus_output_tokens'] == totals['C']
                  and exact_ratio(published_pair['C_over_N_input_plus_output']) == token_ratio)
        token_median = statistics.median(token_pairs)
        time_median = statistics.median(time_pairs)
        check(view + '_exact_token_pair_median', token_median == exact_ratio(usage['segment_summaries'][view]['median_pair_ratio']))
        check(view + '_exact_time_pair_median', time_median == exact_ratio(timing['aggregates'][view]['median_pair_C_over_N']))
        check(view + '_time_totals', group_time['N'] == timing['aggregates'][view]['N_total_ns']
              and group_time['C'] == timing['aggregates'][view]['C_total_ns'])
        view_results[view] = {'N_input_plus_output': group_tokens['N'], 'C_input_plus_output': group_tokens['C'],
            'time_median_pair_ratio': str(time_median), 'token_median_pair_ratio': str(token_median),
            'time_median_pair_ratio_decimal': float(time_median), 'token_median_pair_ratio_decimal': float(token_median)}
    quality_pass = all(row == {'episodes': 3, 'turns': 9} for row in counts.values())
    token_pass = view_results['FULL']['C_input_plus_output'] <= view_results['FULL']['N_input_plus_output']
    time_pass = Fraction(view_results['FULL']['time_median_pair_ratio']) <= Fraction(7, 10)
    check('quality_gate_matches_usage_component', usage['gates']['quality']['passed'] is quality_pass)
    check('token_gate_matches_usage_component', usage['gates']['token']['passed'] is token_pass)
    check('time_gate_matches_timing_component', timing['full_episode_time_gate_C_over_N_median_le_0_70'] is time_pass)
    ledger = source(BATCH / 'LEDGER.json')
    check('master_six_episode_rows', len(ledger['episodes']) == 6 and ledger['episodes'] == timing['episodes'])
    check('master_eighteen_turn_rows', [(row['cell'], row['turn_index']) for row in ledger['turns']]
          == [(cell, turn) for cell in CELLS for turn in (1, 2, 3)])
    check('master_group_usage_exact', ledger['group_usage'] == usage['group_aggregates'])
    published_usage = {(row['cell'], row['turn_index']): row for row in usage['rows']}
    published_timing = {(row['cell'], row['turn_index']): row for row in timing['turns']}
    check('master_all_usage_and_timing_turn_values', all(row['usage'] == published_usage[(row['cell'], row['turn_index'])]
          and row['timing'] == published_timing[(row['cell'], row['turn_index'])] for row in ledger['turns']))
    for view, turns in VIEWS.items():
        published_view = ledger['views'][view]
        check('master_' + view + '_exact_medians',
              exact_ratio(published_view['median_pair_time_C_over_N']) == Fraction(view_results[view]['time_median_pair_ratio'])
              and exact_ratio(published_view['median_pair_token_C_over_N']) == Fraction(view_results[view]['token_median_pair_ratio']))
        check('master_' + view + '_all_pair_ids', [row['pair'] for row in published_view['pairs']] == [1, 2, 3])
        for pair in published_view['pairs']:
            number = pair['pair']
            n_time, c_time = clocks['N' + str(number)][view], clocks['C' + str(number)][view]
            tokens = {group: sum(values['input_tokens'] + values['output_tokens']
                for (cell, turn), values in raw_usage.items() if cell == group + str(number) and turn in turns)
                for group in ('N', 'C')}
            check('master_' + view + '_pair_' + str(number) + '_all_originals',
                  pair['N_time_ns'] == n_time and pair['C_time_ns'] == c_time
                  and pair['N_input_plus_output'] == tokens['N'] and pair['C_input_plus_output'] == tokens['C']
                  and exact_ratio(pair['time_C_over_N']) == Fraction(c_time, n_time)
                  and exact_ratio(pair['token_C_over_N']) == Fraction(tokens['C'], tokens['N']))
    expected_gates = {'quality': quality_pass, 'time': time_pass, 'token': token_pass,
                      'overall_fixed_task': quality_pass and time_pass and token_pass}
    check('master_gates_match_independent_originals', ledger['gates'] == expected_gates)
    check('master_unknowns_retained', ledger['fees_subscription_debit_provider_requests'] is None
          and ledger['shared_and_historical_costs']['project_total_investment_ns'] is None)
    root_check = source(BATCH / 'RECALC_CHECK.json')
    check('root_recalculation_bound_to_master_bytes', root_check['passed'] is True
          and root_check['gates'] == expected_gates and root_check['ledger_sha256'] == sha(BATCH / 'LEDGER.json'))
    inputs[str(Path(__file__).resolve())] = sha(Path(__file__))
    result = {'passed': all(row['passed'] for row in checks), 'checks': checks, 'views': view_results,
        'gates': {'quality': quality_pass, 'time': time_pass, 'token': token_pass,
                  'overall_fixed_task_gate': quality_pass and time_pass and token_pass},
        'quality_counts': counts, 'inputs_sha256': inputs,
        'scope': 'Independent terminal-event/original-clock recomputation and simple master-ledger row/gate/pair cross-check. No session-log read or new experiment.',
        'new_model_Blender_product_API_runs': 0}
    (HERE / 'COMPONENT_CHECK.json').write_text(json.dumps(result, ensure_ascii=False, allow_nan=False, indent=2) + '\n',
                                             encoding='utf8', newline='\n')
    print(json.dumps({'passed': result['passed'], 'checks': len(checks), 'gates': result['gates']}))


if __name__ == '__main__':
    main()
