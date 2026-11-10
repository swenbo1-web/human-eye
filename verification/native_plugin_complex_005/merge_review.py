"""005-only sealed-review adapter over the unchanged 004 final cost join.

The two root reviews already contain every quality judgment. In-memory views
only rename their differing fields for the old join; no scoring or tests run.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import types

HERE = Path(__file__).resolve().parent
REUSED = HERE.parent / 'native_plugin_complex_004/merge_review.py'
REUSED_SHA = '8b78866dc13e17e1ce1ca85493fe94dc21feabe8965f7bf35211116189c6542e'
SEAL_PATH = Path('D:/hefe/verification/fixes/20261110_native_plugin_compare_005/BLIND_QUALITY_SEAL.json')
SEAL_SHA = 'e45390ea05209760f094127ee7bd853f8c73fc12e341a7c46b2dcae5b8249ca1'
REVIEW_PINS = {
    'assembly': ('BLIND_ASSEMBLY_REVIEW.json', 'fb71727a85f7695e651ce66e546ca260ec815349677453b0ca13c9d850d13a2a'),
    'discovery': ('BLIND_DISCOVERY_REVIEW.json', 'ae0f57655c2d740ebf4eb4e8abc9570e39fe12d09079f058a031bb4848c8a119'),
}
ANALYSIS_SHA = 'be7ee2d995bb613ce4ba9868d2f6b545a8ec9e43bf5152fccd734589269dadc7'
EXTRA_METRICS = ('scene_observe_attempts', 'connection_status_attempts', 'all_plugin_read_attempts')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical_sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
        ensure_ascii=True, allow_nan=False).encode('utf8')).hexdigest()


def reuse():
    raw = REUSED.read_bytes()
    if hashlib.sha256(raw).hexdigest() != REUSED_SHA:
        raise ValueError('sealed_004_merge_source_changed')
    module = types.ModuleType('_complex005_reused_final_merge')
    module.__file__ = str(REUSED)
    exec(compile(raw, str(REUSED), 'exec'), module.__dict__)
    module.GROUPS = ('N', 'H', 'C')
    module.METRICS += EXTRA_METRICS
    return module


def input_pins(base, document):
    entries = document['inputs']
    entries = list(entries.values()) if isinstance(entries, dict) else entries
    return base.review_inputs({'input_files': entries}, 'original_root_review')


def views(base, root, seal_path):
    seal = base.sealed(seal_path, SEAL_SHA, 'root_quality_seal')
    if (seal['sealed_before_root_unblinding'] is not True or seal['planned'] != 18
            or seal['reviewed'] != 18):
        raise ValueError('root_quality_seal_complete_eighteen_required')
    pins = {}
    for name, pin in seal['files'].items():
        path = seal_path.parent / name
        base.sealed(path, pin, 'root_quality_seal_member') if path.suffix == '.json' else None
        if sha(path) != pin:
            raise ValueError('root_quality_seal_member_changed:' + name)
        pins[str(path.resolve())] = pin
    pins[str(seal_path.resolve())] = SEAL_SHA
    documents, semantic_rows, evidence_views, lineage = {}, [], {}, []
    for task, (name, pin) in REVIEW_PINS.items():
        path = (seal_path.parent / name).resolve()
        if seal['files'].get(name) != pin:
            raise ValueError('quality_seal_review_pin_mismatch')
        document = base.sealed(path, pin, 'task_review')
        if len(document['answers']) != 9:
            raise ValueError('each_root_task_review_requires_nine_rows')
        original_inputs = input_pins(base, document)
        for source, digest in original_inputs.items():
            if source in pins and pins[source] != digest:
                raise ValueError('root_review_input_pin_conflict')
            pins[source] = digest
        normalized = []
        for index, original in enumerate(document['answers']):
            if original['task_id'] != task:
                raise ValueError('sealed_review_task_mismatch')
            for key in ('delivered', 'core_facts_correct', 'requested_answer_complete',
                        'evidence_supported', 'readonly_current_state', 'full_pass'):
                if type(original[key]) is not bool:
                    raise ValueError('sealed_root_quality_field_must_be_bool:' + key)
            final_sha = original['final_text_utf8_sha256'] if task == 'assembly' else original['final_answer_sha256']
            packet = (original['tool_evidence'] if task == 'assembly' else
                {'path': original['evidence_path'], 'sha256': original['evidence_sha256']})
            if sha(packet['path']) != packet['sha256']:
                raise ValueError('root_sealed_packet_changed')
            origin = {'path': str(path), 'sha256': pin, 'row_pointer': '/answers/' + str(index),
                'original_row_canonical_sha256': canonical_sha(original)}
            row = dict(copy.deepcopy(original), answer_text_sha256=final_sha,
                input_evidence=copy.deepcopy(packet), derived_from_sealed_root=origin)
            normalized.append(row)
            semantic_rows.append(copy.deepcopy(row))
            lineage.append({'answer_id': row['answer_id'], 'task_id': task, **origin})
        documents[task] = document
        evidence_views[str(path)] = {'schema': 'derived_from_sealed_root_task_review_view',
            'input_files': [{'path': p, 'sha256': s} for p, s in original_inputs.items()],
            'answers': normalized, 'summary': document.get('summary')}
    ids = [row['answer_id'] for row in semantic_rows]
    if len(ids) != 18 or len(set(ids)) != 18:
        raise ValueError('root_reviews_exact_eighteen_unique_answers_required')
    failed = {row['answer_id'] for row in semantic_rows if row['full_pass'] is False}
    if (failed != set(seal['failed_answer_ids']) or len(failed) != seal['fail']
            or sum(row['full_pass'] is True for row in semantic_rows) != seal['full_pass']):
        raise ValueError('root_quality_seal_and_original_rows_disagree')
    plan = base.load(root / 'PLAN.json')
    if plan['cycle_id'] != 'NATIVE-PLUGIN-COMPLEX-005':
        raise ValueError('005_plan_required')
    tasks = base.unique_rows(base.load(root / 'blind/TASKS.json')['tasks'], 'task_id', base.TASKS, 'tasks')
    rules = Path(plan['session_rules']).read_bytes()
    prompt_bindings = []
    for task in base.TASKS:
        body = Path(plan['tasks'][task]['prompt']).read_bytes()
        text = tasks[task]['text'].encode('utf8')
        expected = plan['tasks'][task]['model_input_sha256']
        if (rules + b'\n' + body != text or base.digest(text) != expected
                or base.digest(rules) != plan['session_rules_sha256']
                or base.digest(body) != plan['tasks'][task]['prompt_sha256']
                or len(text) != plan['tasks'][task]['model_input_bytes']):
            raise ValueError('actual_rules_and_prompt_reconstruction_failed:' + task)
        prompt_bindings.append({'task_id': task, 'model_input_sha256': expected,
            'text_utf8_sha256': base.digest(text), 'declared_input_hash_matches_frozen_binding': True,
            'exact_reconstruction_matches': True,
            'origin': 'derived actual bytes; TASKS is SHA-bound in both original root review manifests'})
    semantic = {'schema': 'derived_from_sealed_root_combined_quality_view',
        'input_files': [{'path': p, 'sha256': s} for p, s in pins.items()],
        'answers': semantic_rows, 'task_prompt_binding': prompt_bindings}
    return seal, documents, semantic, evidence_views, lineage


def merge(root, seal_path):
    base = reuse()
    root, seal_path = Path(root).resolve(), Path(seal_path).resolve()
    seal, original, semantic, evidence, lineage = views(base, root, seal_path)
    original_sealed = base.sealed

    def normalized_sealed(path, pin, label):
        # Always verify actual original bytes before returning a derived view.
        document = original_sealed(path, pin, label)
        absolute = str(Path(path).resolve())
        if absolute == str(seal_path):
            return semantic
        return evidence.get(absolute, document)

    base.sealed = normalized_sealed
    analysis_path = root / 'private/ANALYSIS_PENDING_QUALITY.json'
    analysis = original_sealed(analysis_path, ANALYSIS_SHA, 'analysis')
    if len(analysis['inputs_sha256']) != 1752:
        raise ValueError('fixed_analysis_1752_input_manifest_required')
    for row in analysis['rows']:
        if (row['plugin_attempts'] != row['scene_observe_attempts']
                or row['all_plugin_read_attempts'] != row['scene_observe_attempts'] + row['connection_status_attempts']):
            raise ValueError('distinct_plugin_read_attempt_accounting_mismatch')
    paths = [seal_path.parent / name for name, _ in REVIEW_PINS.values()]
    review_shas = [pin for _, pin in REVIEW_PINS.values()]
    result = base.merge(root, seal_path, SEAL_SHA, paths, review_shas, analysis_path, ANALYSIS_SHA)
    discovery = original['discovery']['answers']
    initial = [row for row in discovery if row['initial_false_intersection_call'] is not None]
    d3 = [row['criteria']['D3_complete_scope'] for row in discovery]
    history = {'scope': 'Direct aggregation of sealed 005 reviewer fields; no geometry replay or new scoring',
        'initial_false_intersection': len(initial),
        'recovered_before_final': sum(row['recovered_before_final'] is True for row in initial),
        'unrecovered_final': sum(row['recovered_before_final'] is False for row in initial),
        'all_47_enumerated': sum(row['visited_candidates'] == row['expected_candidates'] == 47
            and row['enumeration_complete'] is True for row in d3),
        'valid_complete_resolution': sum(row['valid_complete_resolution'] is True for row in d3),
        'coverage_claim_valid': sum(row['coverage_claim_valid'] is True for row in discovery),
        'per_answer': [{key: row[key] for key in ('answer_id', 'initial_false_intersection_call',
            'recovered_before_final', 'final_geometry_call', 'enumeration_complete', 'coverage_claim_valid')}
            for row in discovery],
        'attribution': 'Sealed false-intersection events are in model-authored Native calculations; no product-geometry advantage is inferred.'}
    result['schema'] = 'complex005-sealed-quality-cost-join-v1'
    result['discovery_error_history'] = history
    result['seals'].pop('semantic_review')
    result['seals'].update(root_quality_seal={'path': str(seal_path), 'sha256': SEAL_SHA,
        'pinned_members': seal['files']}, postprocess_script_sha256=sha(__file__),
        reused_complex004_merge={'path': str(REUSED), 'sha256': REUSED_SHA},
        derived_review_views={'kind': 'in_memory_derived_from_sealed_root',
            'semantic_view_canonical_sha256': canonical_sha(semantic),
            'evidence_view_canonical_sha256': {p: canonical_sha(v) for p, v in evidence.items()},
            'row_lineage': lineage, 'separate_derived_files_written': False})
    result['adapter_notes'] = [
        'Each original task review contains semantic/evidence/readonly/full_pass booleans; two legacy join views reuse those same judgments, not independent new scores.',
        'Assembly final_text_utf8_sha256/tool_evidence and discovery final_answer_sha256/evidence_path+evidence_sha256 are renamed only in memory.',
        'Every normalized row retains its original review path/SHA/row pointer/canonical row SHA; original sealed files are never changed.',
        'Actual rules+prompt bytes are reconstructed, 19 anonymous members bound, and all 1752 analysis inputs rehashed by the pinned join.',
        'Status, scene-observe and all-plugin-read attempts are distinct; status does not establish geometry execution.',
        '005 history uses initial_false_intersection_call/recovered_before_final/final_geometry_call and original D3 visited/resolved scope, not 004 historical counts.']
    result['verified_analysis_input_count'] = 1752
    result['quality_rate'] = {'denominator': 18,
        'full_pass': sum(row['quality_full_pass'] is True for row in result['rows']),
        'full_fail': sum(row['quality_full_pass'] is False for row in result['rows']),
        'unknown': sum(row['quality_full_pass'] is None for row in result['rows'])}
    return base, result


def markdown(base, result):
    display = dict(result, discovery_error_history=dict(result['discovery_error_history'],
        initial_false_zero=result['discovery_error_history']['initial_false_intersection']))
    text = base.markdown(display)
    text = text.replace('Evidence review and semantic review are preserved separately.',
        'Both legacy review views derive from the same sealed task-specific root judgments; no new scoring occurred.')
    text = text.replace('initial false-zero results', 'initial false-intersection results')
    history = result['discovery_error_history']
    text += ('\nOriginal D3 scope: all-47 enumeration is distinct from valid complete resolution: '
        f"{history['all_47_enumerated']}/9 visited all candidates; {history['valid_complete_resolution']}/9 validly resolved the full query.\n"
        '\nJSON separately preserves scene-observe, connection-status and all-plugin-read attempts. '
        'A status read is not a geometry query. All 1752 analysis inputs and 19 anonymous members were verified.\n')
    return text


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=HERE)
    parser.add_argument('--seal', type=Path, default=SEAL_PATH)
    parser.add_argument('--run', action='store_true')
    args = parser.parse_args()
    if not args.run:
        print(json.dumps({'mode': 'interface_only', 'command': '--run [--root PATH] [--seal PATH]',
            'sealed_quality_sha256': SEAL_SHA, 'analysis_sha256': ANALYSIS_SHA,
            'outputs': 'private/FINAL_QUALITY_COST.json and .md; exclusive',
            'new_tests_or_model_or_solver_runs': 0}))
        return
    output, md = args.root / 'private/FINAL_QUALITY_COST.json', args.root / 'private/FINAL_QUALITY_COST.md'
    if output.exists() or md.exists():
        raise FileExistsError('final_join_outputs_are_exclusive')
    base, result = merge(args.root, args.seal)
    report = markdown(base, result)
    with output.open('xb') as stream:
        stream.write(base.dump_bytes(result))
    with md.open('x', encoding='utf8', newline='\n') as stream:
        stream.write(report)
    print(json.dumps({'quality_rate': result['quality_rate'], 'output_json': str(output),
        'output_json_sha256': sha(output), 'output_md': str(md), 'output_md_sha256': sha(md),
        'wrapper_sha256': sha(__file__), 'model_or_solver_or_test_runs': 0}))


if __name__ == '__main__':
    main()
