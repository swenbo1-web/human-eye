"""Check source-only transcription before the first complete quality score."""

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import re


HERE = Path(__file__).resolve().parent
RUNTIME = Path('D:/he_m5_task_consume_001/formal')
ORDER = ['A1', 'B1', 'B2', 'A2', 'A3', 'B3']
PINS = {}


def raw(path):
    path = Path(path).resolve()
    blob = path.read_bytes()
    PINS[str(path)] = {'path': str(path), 'bytes': len(blob), 'sha256': hashlib.sha256(blob).hexdigest()}
    return blob


def read(path):
    return json.loads(raw(path))


def need(condition, label):
    if not condition:
        raise ValueError(label)


def location(value, path):
    tokens = re.findall(r'([A-Za-z_][A-Za-z_0-9]*)|\[(\d+)\]', path[2:])
    keys = [int(index) if index else key for key, index in tokens]
    for key in keys[:-1]:
        value = value[key]
    return value, keys[-1]


def serialized(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def main():
    normalized_path = HERE / 'admin/NORMALIZED.json'
    normalized = read(normalized_path)
    draft = read(HERE / 'admin/SEMANTIC_REVIEW_DRAFT.json')
    run = read(RUNTIME.parent / 'RUN_RESULT.json')
    raw(normalized['source_annotation_path'])
    raw(HERE / 'admin/ROOT_DECLARED_HASH_REVIEW.json')
    raw(HERE / 'A1_ARCHIVE_CORRELATION_DIAGNOSIS.json')
    raw(RUNTIME.parent / 'ROOT_OPERATOR_STOP.json')
    need([row['slot_id'] for row in normalized['slots']] == ORDER
         and [row['slot_id'] for row in draft['slots']] == ORDER, 'six_original_slots')
    need(draft['normalized_sha256'] == PINS[str(normalized_path.resolve())]['sha256'], 'reviewed_normalized_bytes')
    quoted_path = HERE / 'quoted_sources.py'
    raw(quoted_path)
    specification = importlib.util.spec_from_file_location('_root_source_quotations', quoted_path)
    quoted = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(quoted)
    rows = []
    for row, proposal, dispatch in zip(normalized['slots'], draft['slots'], run['records']):
        slot = row['slot_id']
        need(slot == proposal['slot_id'] == dispatch['slot_id'], 'exact_slot_alignment')
        folder = RUNTIME / slot
        if slot == 'B3':
            need(dispatch['status'] == 'failed' and dispatch['result_path'] is None
                 and not (folder / 'consumer/PUBLIC_FINAL.txt').exists()
                 and row['raw_answer_path'] is None and row['answer'] == {}, 'operator_stopped_absence')
            rows.append({'slot_id': slot, 'actual_final_read': False,
                         'reviewed_absence': True, 'normalized_facts_added': False})
            continue
        final_path = folder / 'consumer/PUBLIC_FINAL.txt'
        final = raw(final_path).decode('utf-8')
        original = json.loads(final)
        need(row['raw_answer_sha256'] == PINS[str(final_path.resolve())]['sha256'], 'original_final_identity/' + slot)
        need(row['answer_excerpt'] == final.strip(), 'complete_original_JSON/' + slot)
        restored = copy.deepcopy(row['answer'])
        resolutions = {item['json_path']: item for item in row['source_reference_resolution']}
        for change in reversed(row['normalization_changes']):
            path = change['json_path']
            before, key = location(original, path)
            after, after_key = location(restored, path)
            need(before[key] == change['raw_value'] and after[after_key] == change['normalized_value'], 'actual_change_values/' + slot)
            if change['kind'] == 'explicit_current_reference_canonicalization':
                need(re.search(r'\.source_references\[\d+\]$', path)
                     and isinstance(before[key], str) and bool(before[key])
                     and path in resolutions and resolutions[path]['original_reference'] == before[key], 'nonempty_explicit_reference/' + slot)
            else:
                need(change['kind'] == 'explicit_notes_reason_equivalence'
                     and re.fullmatch(r'\$\.regions\[\d+\]\.unknown_reason', path)
                     and before[key] is None and before['notes'] == change['normalized_value'], 'exact_notes_reason/' + slot)
            after[after_key] = change['raw_value']
        need(serialized(restored) == serialized(original), 'no_other_answer_changes/' + slot)
        tools = read(folder / 'owner/TOOLS.json')['tools']
        request_paths = [folder / 'owner' / ('tool_' + str(tool['attempt']).zfill(2)) / 'REQUEST.json' for tool in tools]
        result_paths = [path.with_name('RESPONSE.json') for path in request_paths]
        sources = quoted.Sources(folder, final, row['sources'], result_paths, request_paths)
        for source in row['sources']:
            need(hashlib.sha256(raw(source['path'])).hexdigest() == source['sha256'], 'actual_source_bytes/' + slot)
        current_refs = {item['canonical_ref'] for item in row['source_reference_resolution']}
        quoted.validate_reference_resolutions(row, final, sources,
            {'actual_tool_results': result_paths, 'actual_tool_requests': request_paths,
             'current_source_references': current_refs})
        for extra in row['extra_assertions']:
            container, key = location(original, extra['json_path'])
            need(container[key] == extra['actual_value'], 'all_extra_assertions_transcribed/' + slot)
        need(not row.get('extra_assertion_errors') and not row.get('contradictions'), 'source_semantics_review/' + slot)
        rows.append({'slot_id': slot, 'actual_final_read': True,
                     'final_sha256': row['raw_answer_sha256'],
                     'source_references_checked': len(resolutions),
                     'extra_assertions_read': len(row['extra_assertions']),
                     'normalization_changes_checked': len(row['normalization_changes']),
                     'only_source_reference_and_explicit_notes_changes': True,
                     'substantive_values_preserved': True})
    need(run['actual_consumers'] == 5 and len(rows) == 6, 'five_original_answers_six_denominator')
    raw(Path(__file__))
    report = {'schema': 'm5-task-consumption-semantic-review-v1', 'passed': True,
              'all_six_reviewed': True, 'actual_complete_finals_read': 5,
              'normalized_sha256': PINS[str(normalized_path.resolve())]['sha256'],
              'rows': rows, 'cost_analysis_performed': False, 'content_grades_executed': 0,
              'independent_manual_review': [
                  'Root read all five complete original JSON answers, including every note, limitation, optional source field and declared method.',
                  'A1/A2/A3/B2 explicitly use current raw geometry after outer bridge failures. Backend successful replies hidden from the consumer provide no adopted measurement claim.',
                  'B1 explicitly uses the same delivered joint O/T response for observation, full-object distance and source correspondence.',
                  'The five vertical-region notes explicitly state finite-pool orientation and positive-area occlusion. Their exact text supplies the null reason equivalence.',
                  'A2/A3 declare a vertices/triangles compact-JSON hash method. Root independently replayed all four hashes against complete current raw arrays.',
                  'A optional parent hashes identify the quoted current observation binding. Its source correspondence uses publicly matched identities and geometry, with different top-level UUIDs explicitly acknowledged.',
                  'TASK_FAILURE is explicitly a failure collection. Its original definition and all actual responses are preserved, and the canonical reference resolves to its uniquely named last direct tool failure.',
                  'No-scene-save wording concerns source-scene/task files. Infrastructure images, logs and archives remain in the recorded work.',
                  'B3 has an original dispatch failure and an explicit root stop before any consumer launch. No final or facts are supplied for it.'
              ],
              'author_association': 'Root authored cost decision, input freezes and operator stop. A separate scoring agent authored normalization and grading. Harness and bridge authors are disclosed separately. Administrator independent acceptance remains pending.',
              'input_pins': sorted(PINS.values(), key=lambda item: item['path']),
              'new_actual_calls': 0, 'new_models': 0, 'new_rasters': 0}
    with (HERE / 'admin/SEMANTIC_REVIEW.json').open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(report, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write('\n')
    print(json.dumps({'semantic_review_passed': True, 'actual_finals': 5,
                      'all_six_including_absence': True, 'content_grades': 0}))


if __name__ == '__main__':
    main()
