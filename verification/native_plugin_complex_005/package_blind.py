"""005-only adapter over the byte-pinned 004 anonymous postprocessors.

Default mode only reports the interface. --run is for terminal 18-slot runs
with protocol/cleanup proof, never a runtime/model launcher. Original answer
text, model code/arguments/query and all attempted tool results are preserved.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import tempfile
import time
import types

HERE = Path(__file__).resolve().parent
PREVIOUS = HERE.parent/'native_plugin_complex_004'
TASK = 'NATIVE-PLUGIN-COMPLEX-005'
REUSED = {
    'anonymize.py': 'dc88541d9d0612f15b58d1f1c908ab4bf8800fdfbbce766006017c62728ffec0',
    'anonymize_evidence.py': '5e599019b61a712d635a446af49cf6d1b49241c04f353229b5508b1cdb013d6c',
}
NEW_ADMIN_KEYS = {'implementation_revision', 'runtime_identity', 'state_file'}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def reuse(name):
    path = PREVIOUS/name
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != REUSED[name]:
        raise ValueError('sealed_004_postprocessor_changed:'+name)
    # Executing the pinned pure helper from bytes avoids pycache writes in 004.
    module = types.ModuleType('_complex005_reused_'+path.stem)
    module.__file__ = str(path)
    exec(compile(raw, str(path), 'exec'), module.__dict__)
    return module


def attachment_cleanup_checks(folder, consumer, provenance):
    """Bind attachment process/exit facts to raw proof, not a supplied flag."""
    folder = Path(folder)
    def record(path):
        if not path.is_file():
            return None
        raw = path.read_bytes()
        provenance[str(path)] = hashlib.sha256(raw).hexdigest()
        def unique(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError('duplicate proof key')
                result[key] = value
            return result
        try:
            return json.loads(raw, object_pairs_hook=unique,
                parse_constant=lambda value: (_ for _ in ()).throw(ValueError('nonfinite proof')))
        except (ValueError, UnicodeError):
            return None
    cleanup = record(folder.parent.parent/'CLEANUP.json')
    rows = cleanup.get('pids') if isinstance(cleanup, dict) else None
    present, absent = set(), set()
    if isinstance(rows, list):
        for row in rows:
            if not isinstance(row, dict) or type(row.get('pid')) is not int or row['pid'] <= 0:
                continue
            if row.get('present') is True:
                present.add(row['pid'])
            elif row.get('present') is False:
                absent.add(row['pid'])
    bridges = sorted(path for path in (folder/'attachments').glob('bridge_*') if path.is_dir())
    absence = []
    normal_exit = []
    receipt_exists = []
    for bridge in bridges:
        started = record(bridge/'STARTED.json')
        pid = started.get('pid') if isinstance(started, dict) else None
        valid_pid = type(pid) is int and pid > 0
        if not valid_pid or pid in (present & absent):
            absence.append(None)
        elif pid in present:
            absence.append(False)
        elif pid in absent:
            absence.append(True)
        else:
            absence.append(None)
        exit_path = bridge/'EXIT.json'
        receipt_exists.append(exit_path.is_file())
        ended = record(exit_path)
        if not isinstance(ended, dict):
            normal_exit.append(None)
        elif not valid_pid or type(ended.get('pid')) is not int or ended.get('pid') != pid:
            normal_exit.append(False)
        elif type(ended.get('normal_exit')) is bool:
            normal_exit.append(ended['normal_exit'])
        else:
            normal_exit.append(None)
    def conjunction(values):
        if any(value is False for value in values):
            return False
        if not values or any(value is None for value in values):
            return None
        return True
    return {
        'consumer_supplied_client_cleanup_confirmed_record': consumer.get('bridge_cleanup', {}).get('confirmed'),
        'client_process_absence_confirmed_by_cleanup_snapshot': conjunction(absence),
        'client_graceful_exit_receipt_present': all(receipt_exists) if bridges else False,
        'client_normal_exit_attested_by_receipt': conjunction(normal_exit),
        'client_cleanup_scope': 'Actual attachment STARTED PIDs matched with the final recorded cleanup snapshot; no inference about unobserved transient processes or graceful termination from PID absence.',
        'client_cleanup_quality_policy': 'Separate operational evidence; missing EXIT does not mean an owned backend is hanging and adds no quality gate.',
    }


def configure():
    answers, evidence = reuse('anonymize.py'), reuse('anonymize_evidence.py')
    answers.TASK = TASK

    def fixed_inputs(root):
        plan_path, run_path = root/'PLAN.json', root/'RUN_RESULT.json'
        plan_blob, run_blob = plan_path.read_bytes(), run_path.read_bytes()
        plan, run = answers.decode(plan_blob), answers.decode(run_blob)
        if (plan.get('cycle_id') != TASK or run.get('cycle_id') != TASK
                or plan.get('denominator') != 18 or run.get('denominator') != 18):
            raise ValueError('fixed_005_task_and_18_slot_denominator_required')
        if type(run.get('ended_ns')) is not int or run['ended_ns'] <= 0:
            raise ValueError('terminal_RUN_RESULT_required')
        sequence, records = plan.get('sequence'), run.get('cells')
        if not isinstance(sequence, list) or not isinstance(records, list) or len(sequence) != 18 or len(records) != 18:
            raise ValueError('all_18_plan_and_run_slots_required')
        if len({row.get('cell') for row in sequence}) != 18 or len({row.get('cell') for row in records}) != 18:
            raise ValueError('duplicate_cell_in_fixed_denominator')
        wanted = Counter({(task, round_, group): 1 for task in ('assembly', 'discovery')
            for round_ in (1, 2, 3) for group in ('N', 'H', 'C')})
        if Counter((row.get('task'), row.get('round'), row.get('group')) for row in sequence) != wanted:
            raise ValueError('fixed_two_tasks_three_rounds_N_H_C_required')
        for slot, record in zip(sequence, records):
            if any(record.get(key) != slot.get(key) for key in ('cell', 'task', 'round', 'group')):
                raise ValueError('RUN_RESULT_slot_identity_or_order_mismatch')
            if record.get('status') not in ('completed', 'failed', 'not_run'):
                raise ValueError('terminal_slot_status_required')
        pin = answers.load(root/'FREEZE.json').get('files_sha256', {}).get(str(plan_path.resolve()))
        if pin != answers.sha(plan_blob):
            raise ValueError('PLAN_not_bound_to_execution_FREEZE')
        return plan, run, answers.sha(plan_blob), answers.sha(run_blob)

    answers.fixed_inputs = fixed_inputs
    original_prepare = answers.prepare

    def prepare(root):
        public, tasks, private = original_prepare(root)
        private['schema'] = 'complex-005-private-blind-map-v1'
        private['postprocess_script_sha256'] = sha(__file__)
        private['reused_postprocessors'] = {str(PREVIOUS/name): pin for name, pin in REUSED.items()}
        return public, tasks, private

    answers.prepare = prepare
    original_redactor = evidence.Redactor

    class VersionRedactor(original_redactor):
        def structured(self, value, pointer='$', admin=False):
            if isinstance(value, dict):
                kept = {}
                for key, item in value.items():
                    # These exact subtrees remain untouched, even if they
                    # contain real file reads or administrative-looking names.
                    if key in ('arguments', 'query', 'code'):
                        kept[key] = item
                    elif key in NEW_ADMIN_KEYS:
                        self.note(pointer+'.'+key, '005_administrative_version_identity_or_local_state_path', item)
                    else:
                        kept[key] = item
                value = kept
            return super().structured(value, pointer, admin)

    evidence.Redactor = VersionRedactor
    original_state_checks = evidence.state_checks

    def state_checks(folder, spec, protocol_state, consumer, provenance):
        checks, close = original_state_checks(folder, spec, protocol_state, consumer, provenance)
        # The old bridge flag is a supplied transport record, not an
        # independent process or graceful-shutdown attestation.
        checks.pop('attached_client_cleanup_confirmed', None)
        checks.update(attachment_cleanup_checks(folder, consumer, provenance))
        return checks, close

    evidence.state_checks = state_checks
    original_output = evidence.output_bytes

    def output_bytes(value):
        if isinstance(value, dict) and value.get('schema') == 'complex004-private-tool-evidence-provenance-v1':
            value = dict(value, schema='complex005-private-tool-evidence-provenance-v1',
                script_sha256=sha(__file__), reused_postprocessors={str(PREVIOUS/name): pin for name, pin in REUSED.items()})
            value['rules'] = value['rules'] + [
                '005 adds only exact return keys implementation_revision, runtime_identity and state_file to administrative removal',
                'The whole runtime_identity is administrative, including source counts and nested expected/actual source pins',
                'Actual method, isError, blocked/unknown/resource reasons, geometry estimates/limits and interface schema semantics remain',
                'Original arguments/query/code subtrees are protected before these new administrative rules',
                'Client cleanup uses bound CLEANUP and actual attachment STARTED/EXIT proof; the consumer-supplied flag is explicitly labelled as a record',
                'Absent or malformed PID/cleanup proof remains unknown; present PID is false; missing EXIT leaves normal exit unknown and adds no quality gate']
        return original_output(value)

    evidence.output_bytes = output_bytes
    return answers, evidence


def terminal_gate(root, answers):
    plan, run, _, _ = answers.fixed_inputs(root)
    protocol = answers.load(root/'private/PROTOCOL_PREFINAL.json')
    states = protocol.get('states')
    if not isinstance(states, list) or len(states) != 18 or {row.get('cell') for row in states} != {row['cell'] for row in plan['sequence']}:
        raise ValueError('all_18_protocol_proof_slots_required_before_packaging')
    cleanup = answers.load(root/'CLEANUP.json')
    if not isinstance(cleanup.get('pids'), list) or not cleanup['pids']:
        raise ValueError('actual_cleanup_proof_required_before_packaging')
    return plan, run


def package(root):
    root = Path(root).resolve()
    answers, evidence = configure()
    terminal_gate(root, answers)
    receipt_path = root/'private/ANON_PACKAGING_RECEIPT.json'
    if receipt_path.exists():
        raise FileExistsError('packaging_receipt_already_exists_never_overwrite')
    began = time.perf_counter_ns()
    final_result = answers.anonymize(root)
    # 004's extractor remains fail-closed on absent CONSUMER/final or incomplete
    # tool lifecycles. Never silently drop an unsuccessful slot or invent checks.
    tool_result = evidence.build(root)
    public = answers.load(root/'blind/ANSWERS.json')['answers']
    index = evidence.load(root/'blind/TOOL_EVIDENCE_INDEX.json')['answers']
    if len(public) != 18 or len(index) != 18 or {(x['task_id'], x['answer_id']) for x in public} != {(x['task_id'], x['answer_id']) for x in index}:
        raise ValueError('anonymous_final_and_tool_evidence_ID_sets_differ')
    private = {'schema': 'complex005-anonymous-packaging-receipt-v1', 'script_sha256': sha(__file__),
        'reused_postprocessors': {str(PREVIOUS/name): pin for name, pin in REUSED.items()},
        'started_ns': began, 'elapsed_ns': time.perf_counter_ns()-began,
        'final_extraction': final_result, 'tool_extraction': tool_result,
        'public_files_sha256': {str(path): sha(path) for path in (root/'blind/ANSWERS.json', root/'blind/TASKS.json', root/'blind/TOOL_EVIDENCE_INDEX.json')},
        'model_calls': 0, 'product_calls': 0, 'Blender_calls': 0, 'scoring_calls': 0}
    with receipt_path.open('xb') as stream:
        stream.write(evidence.output_bytes(private))
    return {'answers': 18, 'tool_packets': 18, 'delivered': final_result['delivered'],
        'blind_answers': str(root/'blind/ANSWERS.json'), 'answers_sha256': sha(root/'blind/ANSWERS.json'),
        'blind_tasks': str(root/'blind/TASKS.json'), 'tasks_sha256': sha(root/'blind/TASKS.json'),
        'blind_tool_index': str(root/'blind/TOOL_EVIDENCE_INDEX.json'), 'tool_index_sha256': sha(root/'blind/TOOL_EVIDENCE_INDEX.json'),
        'model_calls': 0, 'product_calls': 0, 'Blender_calls': 0, 'scoring_calls': 0}


def self_test():
    answers, evidence = configure()
    with tempfile.TemporaryDirectory(prefix='complex005-postprocess-fake-') as temporary:
        root = Path(temporary)
        source = root/'fake.json'; source.write_bytes(b'{}')
        removals = []; redactor = evidence.Redactor(source, removals)
        code = 'print(open("D:/private/TRUTH.json").read())\nprint("elapsed",0.25)\n'
        args = {'code': code, 'query': {'implementation_revision': 'keep', 'state_file': 'D:/private/keep', 'runtime_identity': {'source_file_count': 125}}}
        request = {'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call', 'params': {'name': 'execute_blender_code', 'arguments': args}}
        assert evidence.projected_request(request, redactor)['arguments'] == args
        assert redactor.structured({'arguments': args, 'query': args['query'], 'code': code}) == {'arguments': args, 'query': args['query'], 'code': code}
        actual = {'implementation_revision': 'v21-scene-trace-owner-20261103',
            'runtime_identity': {'source_file_count': 125, 'identity_check': {'expected': {'source_sha256': 'pin'}, 'actual': {'distribution_version': 'old'}}},
            'state_file': 'D:/private/preflight/assembly_H/owner/state.json', 'enabled': True,
            'status': 'blocked', 'reason_codes': ['geometry_resource_limit'], 'isError': True,
            'geometry_work_budget': {'within_budget': False, 'estimates': {'largest_sat_projection_elements': 2081280},
                'limits': {'sat_projection_elements': 2000000}, 'reason_codes': ['sat_projection_work_limit']},
            'schema_version': 'original-query-v1', 'distance_m': .003, 'elapsed_ns': 123,
            'binding': {'runtime_source_sha256': 'pin', 'currentness': 'capture_snapshot'}}
        clean = redactor.structured(actual)
        assert not (NEW_ADMIN_KEYS & set(clean)) and clean['isError'] is True
        assert clean['geometry_work_budget'] == actual['geometry_work_budget'] and clean['reason_codes'] == actual['reason_codes']
        assert clean['schema_version'] == actual['schema_version'] and clean['distance_m'] == .003
        assert clean['binding'] == {'currentness': 'capture_snapshot'} and 'elapsed_ns' not in clean
        assert json.loads(redactor.text(json.dumps(actual))) == clean
        text = 'candidate count 47 elapsed 0.25\ngap 0.003 normal [0.2, 0.4, 0.8]\n'
        assert redactor.text(text) == text.replace('elapsed 0.25', 'elapsed <timing-redacted>')
        stack = '  File "D:/host/runtime.py", line 7, in go\n    print(open("D:/private/TRUTH.json").read())\n'
        assert 'D:/host/runtime.py' not in redactor.text(stack) and 'D:/private/TRUTH.json' in redactor.text(stack)
        assert evidence.code_audit(code) and all(row['source_sha256'] == sha(source) for row in removals)
        rules = root/'rules.txt'; rules.write_bytes('只读\r\n'.encode('utf8'))
        tasks = {}
        for task in ('assembly', 'discovery'):
            path = root/(task+'.txt'); path.write_bytes(('task '+task+'\n').encode())
            raw = rules.read_bytes()+b'\n'+path.read_bytes()
            tasks[task] = {'prompt': str(path), 'prompt_sha256': sha(path),
                'model_input_sha256': hashlib.sha256(raw).hexdigest(), 'model_input_bytes': len(raw)}
        slots = [{'cell': str(i+1).zfill(2), 'task': task, 'round': round_, 'group': group}
            for i, (task, round_, group) in enumerate((t, r, g) for t in tasks for r in (1, 2, 3) for g in ('N', 'H', 'C'))]
        plan = {'cycle_id': TASK, 'denominator': 18, 'sequence': slots, 'tasks': tasks,
            'session_rules': str(rules), 'session_rules_sha256': sha(rules)}
        (root/'PLAN.json').write_bytes(answers.json_bytes(plan))
        (root/'FREEZE.json').write_bytes(answers.json_bytes({'files_sha256': {str((root/'PLAN.json').resolve()): sha(root/'PLAN.json')}}))
        records = []
        for i, slot in enumerate(slots):
            status = 'completed' if i < 12 else 'failed' if i < 15 else 'not_run'
            records.append(dict(slot, status=status))
            if status == 'not_run':
                continue
            directory = root/'cells'/slot['cell']; directory.mkdir(parents=True)
            text = '原始\r\nNative/plugin '+slot['cell']+'\n' if i < 13 else None
            consumer = dict(slot, final=text, valid_completion=status == 'completed')
            (directory/'CONSUMER.json').write_bytes(answers.json_bytes(consumer))
            if text is not None:
                (directory/'PUBLIC_FINAL.txt').write_bytes(text.encode('utf8'))
        run = {'cycle_id': TASK, 'denominator': 18, 'ended_ns': 1, 'cells': records}
        (root/'RUN_RESULT.json').write_bytes(answers.json_bytes(run))
        public, public_tasks, mapping = answers.prepare(root)
        assert len(public['answers']) == len(mapping['answers']) == 18
        assert {row['group'] for row in mapping['answers'].values()} == {'N', 'H', 'C'}
        assert sum(row['delivered'] for row in public['answers']) == 12 and sum(row['text'] is None for row in public['answers']) == 5
        assert all(set(row) == {'task_id', 'answer_id', 'text', 'delivered'} for row in public['answers'])
        for row in public['answers']:
            hidden = mapping['answers'][row['answer_id']]
            if row['text'] is not None:
                assert hashlib.sha256(row['text'].encode('utf8')).hexdigest() == hidden['final_sha256'] == hidden['public_final_sha256']
        run['cells'] = records[:-1]+[records[0]]; (root/'RUN_RESULT.json').write_bytes(answers.json_bytes(run))
        try:
            answers.prepare(root)
        except ValueError:
            pass
        else:
            raise AssertionError('duplicate_or_tail_run_accepted')
    return {'passed': True, 'fake_only': True, 'checks': ['005_N_H_C_eighteen_slots_and_missing_finals_preserved',
        'exact_UTF8_CRLF_and_model_input_bytes', 'duplicate_tail_rejected', 'original_arguments_query_code_untouched',
        'status_version_identity_state_file_targeted_only', 'blocked_isError_and_geometry_budget_preserved',
        'embedded_JSON_same_rules', 'narrow_timing_not_geometry', 'traceback_source_line_and_truth_read_preserved',
        'private_removal_source_hash_bound'], 'reused_postprocessors': REUSED,
        'actual_anonymous_files_created': False, 'model_calls': 0, 'product_calls': 0, 'Blender_calls': 0, 'scoring_calls': 0}


def cleanup_self_test():
    with tempfile.TemporaryDirectory(prefix='complex005-client-proof-fake-') as temporary:
        root = Path(temporary); folder = root/'cells/01'; bridge = folder/'attachments/bridge_fake'
        bridge.mkdir(parents=True)
        def save(path, value):
            path.write_bytes((json.dumps(value)+'\n').encode('utf8'))
        cleanup = root/'CLEANUP.json'; start = bridge/'STARTED.json'; exit_path = bridge/'EXIT.json'
        supplied = {'bridge_cleanup': {'confirmed': True}}
        save(cleanup, {'pids': [{'pid': 123, 'present': False}]}); save(start, {'pid': 123})
        provenance = {}; result = attachment_cleanup_checks(folder, supplied, provenance)
        assert result['consumer_supplied_client_cleanup_confirmed_record'] is True
        assert result['client_process_absence_confirmed_by_cleanup_snapshot'] is True
        assert result['client_graceful_exit_receipt_present'] is False
        assert result['client_normal_exit_attested_by_receipt'] is None
        assert provenance == {str(cleanup): sha(cleanup), str(start): sha(start)}
        save(cleanup, {'pids': [{'pid': 123, 'present': True}]})
        assert attachment_cleanup_checks(folder, supplied, {})['client_process_absence_confirmed_by_cleanup_snapshot'] is False
        save(cleanup, {'pids': []})
        assert attachment_cleanup_checks(folder, supplied, {})['client_process_absence_confirmed_by_cleanup_snapshot'] is None
        save(start, {})
        assert attachment_cleanup_checks(folder, supplied, {})['client_process_absence_confirmed_by_cleanup_snapshot'] is None
        save(start, {'pid': 123}); save(cleanup, {'pids': [{'pid': 123, 'present': False}]})
        save(exit_path, {'pid': 123, 'normal_exit': True})
        provenance = {}; result = attachment_cleanup_checks(folder, supplied, provenance)
        assert result['client_graceful_exit_receipt_present'] is True and result['client_normal_exit_attested_by_receipt'] is True
        assert provenance[str(exit_path)] == sha(exit_path)
        save(exit_path, {'pid': 999, 'normal_exit': True})
        assert attachment_cleanup_checks(folder, supplied, {})['client_normal_exit_attested_by_receipt'] is False
        save(exit_path, {'pid': 123, 'normal_exit': False})
        assert attachment_cleanup_checks(folder, supplied, {})['client_normal_exit_attested_by_receipt'] is False
        save(cleanup, {'pids': [{'pid': 123, 'present': False}, {'pid': 123, 'present': True}]})
        assert attachment_cleanup_checks(folder, supplied, {})['client_process_absence_confirmed_by_cleanup_snapshot'] is None
        save(start, {'pid': True})
        assert attachment_cleanup_checks(folder, supplied, {})['client_process_absence_confirmed_by_cleanup_snapshot'] is None
    return {'passed': True, 'fake_only': True, 'checks': ['supplied_true_is_record_only',
        'actual_PID_absent_is_separate_proof', 'missing_EXIT_does_not_attest_graceful_exit',
        'present_PID_false', 'missing_or_unlisted_or_boolean_PID_unknown', 'contradictory_PID_snapshot_unknown',
        'normal_EXIT_requires_actual_PID_binding', 'abnormal_exit_false', 'cleanup_STARTED_EXIT_raw_hashes_private'],
        'actual_anonymous_files_created': False, 'model_calls': 0, 'product_calls': 0, 'Blender_calls': 0, 'scoring_calls': 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=HERE)
    parser.add_argument('--run', action='store_true')
    parser.add_argument('--self-test', action='store_true')
    parser.add_argument('--self-test-cleanup', action='store_true')
    args = parser.parse_args()
    if args.self_test_cleanup:
        output = HERE/'POSTPROCESSOR_CLEANUP_SELF_TEST.json'
        if output.exists():
            raise FileExistsError('postprocessor_cleanup_self_test_receipt_exists')
        result = dict(cleanup_self_test(), script_sha256=sha(__file__))
        with output.open('x', encoding='utf8', newline='\n') as stream:
            stream.write(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)+'\n')
        print(json.dumps(result, ensure_ascii=False))
    elif args.self_test:
        output = HERE/'POSTPROCESSOR_SELF_TEST.json'
        if output.exists():
            raise FileExistsError('postprocessor_self_test_receipt_exists')
        result = dict(self_test(), script_sha256=sha(__file__))
        with output.open('x', encoding='utf8', newline='\n') as stream:
            stream.write(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)+'\n')
        print(json.dumps(result, ensure_ascii=False))
    elif args.run:
        print(json.dumps(package(args.root), ensure_ascii=False))
    else:
        print(json.dumps({'mode': 'interface_only_no_results_read', 'run_after': 'terminal 18 slots plus protocol and cleanup proof, on coordinator instruction',
            'command': '--run [--root PATH]', 'outputs': 'blind/ANSWERS.json, TASKS.json and same-ID tools/ + TOOL_EVIDENCE_INDEX.json',
            'no_overwrite': True, 'missing_lifecycle_or_absent_final': 'fail closed; retain partial output and raw records for coordinator review, never omit a slot'}))


if __name__ == '__main__':
    main()
