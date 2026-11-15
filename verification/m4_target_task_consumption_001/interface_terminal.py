"""Pure terminal-schema checks with an explicitly synthetic consumer envelope."""

import copy
import hashlib
import importlib.util
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    scorer = load(HERE / 'score_saved.py', '_consume_synthetic_terminal')
    launcher = load(HERE / 'launcher.py', '_consume_synthetic_prompt')
    base = Path('D:/he_m4_target_consume_001/qualification/P_qual')
    result = scorer.read(base / 'SLOT_RESULT.json')
    publication = scorer.read(base / 'SLOT_PUBLICATION.json')
    result.update(slot_id='P1', group='P', phase='formal')
    publication.update(slot_id='P1', group='P')
    outer = {'status': 'completed', 'result_path': str(base / 'SLOT_RESULT.json')}
    source = {key: result['source'][key] for key in ('product_source141_sha256', 'common_task_sha256', 'answer_schema_sha256')}
    source['prompt_sha256'] = hashlib.sha256(launcher.common_prompt('P')).hexdigest()
    envelope = {'slot_id': 'P1', 'group': 'P', 'status': 'completed', 'source': source}
    consumer = {'input_sha256': source['prompt_sha256'], 'valid_completion': True, 'status': 'completed',
                'model': 'gpt-6.1-sol', 'requested_effort': 'medium', 'turn_index': 1,
                'deadline_ns': result['clocks']['consumer_deadline_ns'], 'expected_thread_id': None,
                'runtime_binding': {'confirmed': True}, 'runtime_exit': {'confirmed': True},
                'process_reaped': True, 'exit_code': 0, 'readers_stopped': True,
                'errors': [], 'unexpected_tool_deviations': [], 'bridge_protocol_errors': [], 'mutation_unknown': False}
    positive = scorer.terminal('P1', outer, result, publication, envelope, consumer)
    assert positive['passed'], positive
    cases = []

    def rejected(name, mutate):
        r, p, e, c = copy.deepcopy(result), copy.deepcopy(publication), copy.deepcopy(envelope), copy.deepcopy(consumer)
        mutate(r, p, e, c)
        value = scorer.terminal('P1', outer, r, p, e, c)
        assert value['passed'] is False
        cases.append({'case': name, 'passed': True, 'failed_fields': value['failed_fields']})

    rejected('wrong_slot_label', lambda r, p, e, c: r.update(slot_id='N1'))
    rejected('wrong_product_source', lambda r, p, e, c: r['source'].update(product_source141_sha256='0'*64))
    rejected('wrong_asset', lambda r, p, e, c: r['source'].update(asset_sha256='0'*64))
    rejected('wrong_prompt_even_if_two_saved_hashes_agree', lambda r, p, e, c: (e['source'].update(prompt_sha256='0'*64), c.update(input_sha256='0'*64)))
    rejected('consumer_invalid', lambda r, p, e, c: c.update(valid_completion=False))
    rejected('runtime_exit_unknown', lambda r, p, e, c: c['runtime_exit'].update(confirmed=None))
    rejected('root_child_exit_unknown', lambda r, p, e, c: r['cleanup']['native'].update(confirmed=None))
    rejected('root_forced_child', lambda r, p, e, c: r['cleanup']['native'].update(forced_by_root=True))
    rejected('expired_publication', lambda r, p, e, c: p.update(slot_result_published_ns=r['clocks']['owned_deadline_ns']+1))
    rejected('renewed_deadline', lambda r, p, e, c: r['clocks'].update(consumer_deadline_ns=r['clocks']['consumer_deadline_ns']+1))
    rejected('wrong_result_publication_hash', lambda r, p, e, c: p.update(result_sha256='0'*64))
    report = {'schema': 'target-task-consumption-terminal-interface-v1', 'passed_checked_scope': True,
              'synthetic_positive': True, 'negative_cases': cases,
              'fixture_scope': 'Actual closed no-model qualification cleanup shape plus synthetic formal labels and a synthetic consumer. This is an interface test and is not formal quality or a model completion.',
              'actual_qualification_result_sha256': scorer.INPUTS[str((base / 'SLOT_RESULT.json').resolve())],
              'scorer_sha256': hashlib.sha256((HERE / 'score_saved.py').read_bytes()).hexdigest(),
              'new_actual_calls': 0, 'new_rasters': 0, 'new_models': 0}
    with (HERE / 'admin/INTERFACE_TERMINAL.json').open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(report, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write('\n')
    print(json.dumps({'passed_checked_scope': True, 'synthetic_positive': 1, 'negative_cases': len(cases)}))


if __name__ == '__main__':
    main()
