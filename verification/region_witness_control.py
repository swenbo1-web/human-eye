"""Bounded OFFLINE cycle007 entry: scripted model, recording read-only reader.

No real model/product adapter exists here. The three-stage, two-file contract is
deliberately finite. Simulated nanoseconds are not model or Blender performance.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
from secrets import token_hex

CAPS = dict(directories=2, facts=4, native_supplements=1, model_stages=3)
# Finite offline public-data view, not a general product-report interpreter.
UNKNOWN_STATE_FIELDS = {'state', 'status'}
UNKNOWN_COUNT_FIELDS = {'triangles_unknown', 'unknown_count'}
REQUIRED_QUERY_FIELDS = {'triangle_rows', 'principal_stretches', 'area_ratio'}


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode('utf8')


def frozen(value):
    return json.loads(encoded(value))


def digest(value):
    return hashlib.sha256(encoded(value)).hexdigest()


class Reject(ValueError):
    pass


def need(value, reason):
    if not value:
        raise Reject(reason)


class SimulatedClock:
    def __init__(self, start=0):
        need(type(start) is int and start >= 0, 'clock_start')
        self.now = start

    def advance(self, amount):
        need(type(amount) is int and amount >= 0, 'negative_or_invalid_simulated_time')
        self.now += amount


class ScriptedModel:
    """Transport placeholders bind metadata only, never target IDs or answers."""
    def __init__(self, script, clock):
        self.steps = frozen(script)
        self.clock = clock
        self.calls = []
        self.previous = None

    def respond(self, prompt):
        prompt = frozen(prompt)
        index = len(self.calls)
        self.calls.append(prompt)
        need(index < len(self.steps), 'script_exhausted')
        step = self.steps[index]
        self.clock.advance(step.get('advance_ns', 0))
        if step.get('raise'):
            raise RuntimeError('scripted_model_receipt_unknown')
        tokens = {'$task': prompt['task_sha256'], '$condition': prompt['condition_id'], '$run': prompt['run_nonce'],
                  '$prompt': prompt['prompt_id'], '$evidence': prompt['evidence_ref'],
                  '$response': prompt['prompt_id'] + '/response', '$previous_evidence': self.previous}
        tokens.update({'$evidence.'+key: value for key,value in prompt['evidence_ref'].items()})

        def substitute(value):
            if type(value) is str and value in tokens:
                return frozen(tokens[value])
            if type(value) is dict:
                return {k: substitute(v) for k, v in value.items()}
            if type(value) is list:
                return [substitute(v) for v in value]
            return value

        def bind_headers(raw):
            value=frozen(raw)
            for key in ('response_id','run_nonce','task_sha256','condition_id','prompt_id','evidence_ref'):
                if key in value: value[key]=substitute(value[key])
            return value

        decision = bind_headers(step['response'])
        self.previous = frozen(prompt['evidence_ref'])
        extra = [bind_headers(v) for v in step.get('additional_deliveries', [])]
        return [decision, *[frozen(decision) for _ in range(step.get('duplicate_deliveries', 0))], *extra]


class RecordingReader:
    def __init__(self, config, clock):
        self.config = frozen(config)
        self.clock = clock
        self.calls = []

    def read(self, request):
        request = frozen(request)
        self.calls.append(request)
        override = self.config.get('overrides', {}).get(str(len(self.calls)), {})
        self.clock.advance(override.get('advance_ns', 0))
        if override.get('raise'):
            raise RuntimeError('scripted_reader_unknown_receipt')
        result = dict(request_id=request['request_id'], task_sha256=request['task_sha256'],
                      run_nonce=request['run_nonce'],
                      condition_id=request['condition_id'], source_ref=request['source_ref'],
                      status='ok', data=frozen(self.config.get(request['kind'] + '_data', {'state': 'unknown', 'details_omitted': 1})))
        result.update(frozen(override.get('receipt', {})))
        return result


class Control:
    def __init__(self, task, limits, duration_ns, clock, model, reader):
        self.task = frozen(task)
        self.run_nonce = token_hex(16)
        need(set(task) == {'task_sha256', 'condition_id', 'sources'}, 'task_fields')
        need(type(task['task_sha256']) is str and len(task['task_sha256']) == 64 and all(c in '0123456789abcdef' for c in task['task_sha256']) and type(task['condition_id']) is str and task['condition_id'], 'task_binding')
        need(type(task['sources']) is dict and len(task['sources']) == 2, 'two_sources_required')
        need(set(limits) == set(CAPS) and all(type(limits[k]) is int and 0 <= limits[k] <= CAPS[k] for k in CAPS), 'original_budget_caps')
        need(type(duration_ns) is int and 0 < duration_ns <= 600_000_000_000, 'original_duration_cap')
        self.limits = frozen(limits)
        self.counts = dict.fromkeys(CAPS, 0)
        self.counts.update(decision_attempts=0, physical_reader_calls=0, reader_groups_including_directory=0)
        self.clock, self.model, self.reader = clock, model, reader
        self.started_ns = clock.now
        self.deadline_ns = self.started_ns + duration_ns
        self.source_digest = digest(self.task['sources'])
        self.events = []
        self.evidence = []
        self.current = None
        self.delivered = set()
        self.responses = {}
        self.terminal = None
        self.anchors = None

    def log(self, event, **data):
        self.events.append(frozen(dict(sequence=len(self.events)+1, simulated_ns=self.clock.now, event=event, **data)))

    def stop(self, status, reason, answer=None):
        if self.terminal is None:
            self.terminal = frozen(dict(status=status, reason=reason, answer=answer))
            self.log('terminal', **self.terminal)

    def in_time(self):
        if self.clock.now >= self.deadline_ns:
            self.stop('deadline_exceeded', 'original_absolute_deadline')
            return False
        return True

    def reserve(self, kind, amount=1):
        if self.counts[kind] + amount > self.limits[kind]:
            self.stop('budget_exhausted', kind)
            return False
        self.counts[kind] += amount
        return True

    def collect(self, kind, selections):
        if not self.in_time(): return None
        counter = 'directories' if kind == 'directory' else 'facts'
        if kind == 'supplement':
            if not self.reserve('native_supplements'): return None
        elif self.counts[counter] + 2 > self.limits[counter]:
            self.stop('budget_exhausted', counter)
            return None
        self.counts['reader_groups_including_directory'] += 1
        receipts = []
        for label, source in self.task['sources'].items():
            if not self.in_time(): return None
            if kind != 'supplement' and not self.reserve(counter): return None
            self.counts['physical_reader_calls'] += 1
            request = frozen(dict(request_id=self.run_nonce+'/'+self.task['condition_id']+'/read/'+str(self.counts['physical_reader_calls']),
                                  task_sha256=self.task['task_sha256'], condition_id=self.task['condition_id'],
                                  run_nonce=self.run_nonce,
                                  source_ref=source, label=label, kind=kind, selection=selections.get(label),
                                  deadline_ns=min(self.deadline_ns, self.clock.now+30_000_000_000),
                                  task_deadline_ns=self.deadline_ns, max_requests=16, byte_limit=524288))
            self.log('dispatch', request=request)
            try:
                receipt = frozen(self.reader.read(frozen(request)))
                need(len(encoded(receipt)) <= 524288, 'receipt_byte_budget')
            except Exception as exc:
                self.log('receipt_unknown', request_id=request['request_id'], error=type(exc).__name__)
                self.stop('receipt_unknown', 'no_retry_no_refund')
                return None
            self.log('receipt', request_id=request['request_id'], receipt=receipt)
            if not self.in_time(): return None
            if self.clock.now >= request['deadline_ns']:
                self.stop('deadline_exceeded', 'readonly_call_deadline_no_retry_no_refund')
                return None
            if any(encoded(receipt.get(k)) != encoded(request[k]) for k in ('request_id', 'run_nonce', 'task_sha256', 'condition_id', 'source_ref')):
                self.stop('receipt_unknown', 'receipt_binding_mismatch_no_refund')
                return None
            if receipt.get('status') != 'ok':
                self.stop('receipt_unknown' if receipt.get('status') == 'unknown' else 'execution_failed', 'no_retry_no_refund')
                return None
            receipts.append(dict(label=label, receipt=receipt))
        return receipts

    def prepare_evidence(self, kind, results, response_id):
        value = frozen(dict(kind=kind, results=results, task_sha256=self.task['task_sha256'],
                            run_nonce=self.run_nonce,
                            condition_id=self.task['condition_id'], sources_sha256=self.source_digest,
                            origin_response_id=response_id, evidence_sequence=len(self.evidence)+1))
        value['evidence_id'] = digest(value)
        self.evidence.append(frozen(value))
        self.current = value
        self.log('evidence_prepared', evidence_id=value['evidence_id'], kind=kind)

    def reference(self):
        return {k: self.current[k] for k in ('evidence_id', 'origin_response_id', 'sources_sha256')}

    def gap_valid(self, gap):
        need(type(gap) is dict and set(gap) == {'pointer', 'kind', 'expected', 'reason'}, 'gap_fields')
        need(type(gap['reason']) is str and gap['reason'].strip() and type(gap['pointer']) is str and gap['pointer'].startswith('/'), 'gap_reason_or_pointer')
        parts=gap['pointer'].split('/')[1:]
        need(len(parts)==5 and parts[0]=='results' and parts[1] in ('0','1')
             and parts[2:4]==['receipt','data'], 'gap_outside_public_source_data')
        data=self.current['results'][int(parts[1])]['receipt']['data']
        need(type(data) is dict, 'gap_data_shape')
        field=parts[-1];missing=field not in data;value=data.get(field)
        if gap['kind'] == 'missing':
            need(field in REQUIRED_QUERY_FIELDS and missing and gap['expected'] is None, 'gap_not_required_missing_field')
        else:
            need(not missing and encoded(value) == encoded(gap['expected']), 'gap_value_mismatch')
            if gap['kind'] == 'omitted': need(field=='details_omitted' and type(value) is int and value > 0, 'gap_not_omitted')
            elif gap['kind'] == 'unknown': need(field in UNKNOWN_STATE_FIELDS and value in ('unknown', 'partial')
                or field in UNKNOWN_COUNT_FIELDS and type(value) is int and value > 0, 'gap_not_unknown_marker')
            else: raise Reject('gap_kind')

    def accept(self, raw, prompt):
        if self.terminal is not None:
            self.log('ignored_after_terminal')
            return
        if not self.in_time(): return
        self.counts['decision_attempts'] += 1
        response = frozen(raw)
        self.log('decision_received', response=response)
        need(type(response) is dict and type(response.get('response_id')) is str and response['response_id'], 'response_id')
        identity, content = response['response_id'], digest(response)
        if identity in self.responses:
            need(self.responses[identity] == content, 'response_id_conflict')
            self.log('duplicate_decision', response_id=identity)
            return
        self.responses[identity] = content
        need(all(response.get(k) == prompt[k] for k in ('run_nonce','task_sha256','condition_id','prompt_id')), 'decision_task_condition_prompt_binding')
        need(response.get('evidence_ref') == prompt['evidence_ref'] == self.reference(), 'decision_evidence_binding')
        need(self.current['evidence_id'] in self.delivered, 'evidence_not_delivered')
        action = response.get('action')
        common = {'response_id','run_nonce','task_sha256','condition_id','prompt_id','evidence_ref','action'}
        fields = {'final': {'answer'}, 'abstain': {'reason'}, 'base': {'anchors'},
                  'verify': {'triangle_indices'}, 'supplement': {'gap'},
                  'verify_and_supplement': {'triangle_indices','gap'}}
        need(action in fields and set(response) == common | fields[action], 'decision_fields')
        if action == 'final':
            self.stop('final', 'model_final', response['answer']); return
        if action == 'abstain':
            need(type(response['reason']) is str and response['reason'].strip(), 'abstention_reason')
            self.stop('abstain', response['reason']); return
        if action in ('verify','verify_and_supplement'):
            indices = response['triangle_indices']
            need(type(indices) is list and len(indices) <= 4 and all(type(v) is int and v >= 0 for v in indices) and len(set(indices)) == len(indices), 'triangle_indices')
            if not indices:
                self.stop('abstain', 'empty_triangle_selection'); return
        if self.counts['model_stages'] >= self.limits['model_stages']:
            self.stop('model_stage_exhausted', 'no_stage_left_to_consume_query_evidence'); return
        if action == 'base':
            need(self.current['kind'] == 'directory' and self.anchors is None, 'base_order')
            need(type(response['anchors']) is dict and set(response['anchors']) == set(self.task['sources']) and all(type(v) is str and v for v in response['anchors'].values()), 'anchors')
            self.anchors = frozen(response['anchors'])
            result = self.collect('base', self.anchors)
            if result is not None: self.prepare_evidence('base', result, identity)
            return
        need(self.current['kind'] in ('base','supplement'), 'query_order')
        if action in ('supplement','verify_and_supplement'):
            need(self.current['kind'] == 'base', 'supplement_requires_current_delivered_base')
            self.gap_valid(response['gap'])
            result = self.collect('supplement', self.anchors)
            if result is None: return
        if action in ('verify','verify_and_supplement'):
            verified = self.collect('targeted', {label: response['triangle_indices'] for label in self.task['sources']})
            if verified is None: return
            if action == 'verify_and_supplement': result = dict(supplement=result, targeted=verified)
            else: result = verified
        self.prepare_evidence('supplement' if action == 'supplement' else 'verified', result, identity)

    def run(self):
        initial = self.collect('directory', {})
        if initial is not None: self.prepare_evidence('directory', initial, 'directory-entry')
        while self.terminal is None:
            if not self.in_time(): break
            if not self.reserve('model_stages'): break
            prompt = frozen(dict(task_sha256=self.task['task_sha256'], condition_id=self.task['condition_id'],
                                 run_nonce=self.run_nonce,
                                 prompt_id=self.run_nonce+'/'+self.task['condition_id']+'/model/'+str(self.counts['model_stages']),
                                 evidence_ref=self.reference(), evidence=self.current, counts=self.counts,
                                 deadline_ns=self.deadline_ns))
            self.delivered.add(self.current['evidence_id'])
            self.log('evidence_delivered', evidence_ref=self.reference())
            self.log('model_dispatch', prompt_id=prompt['prompt_id'])
            before = self.current['evidence_id']
            try:
                replies = frozen(self.model.respond(frozen(prompt)))
                need(type(replies) is list and 1 <= len(replies) <= 8, 'response_delivery_batch')
                if not self.in_time(): break
                for reply in replies:
                    self.accept(reply, prompt)
            except Reject as exc: self.stop('rejected', str(exc))
            except Exception as exc: self.stop('model_receipt_unknown', type(exc).__name__)
            if self.terminal is None and self.current['evidence_id'] == before:
                self.stop('evidence_insufficient', 'no_new_decision_no_automatic_model_retry')
        return frozen(dict(schema='offline-region-witness-control-result-v1', task=self.task,
                           terminal=self.terminal, counts=self.counts, limits=self.limits, run_nonce=self.run_nonce,
                           started_ns=self.started_ns, deadline_ns=self.deadline_ns,
                           finished_ns=self.clock.now, evidence=self.evidence, events=self.events,
                           reader_calls=self.reader.calls, model_prompts=self.model.calls,
                           simulated_only=True, real_model_calls=0, product_calls=0,
                           tokens=None, usd=None, geometry_conclusion_inferred_by_controller=False))


def run_script(script):
    script = frozen(script)
    need(script.get('schema') == 'offline-region-witness-script-v1', 'script_schema')
    clock = SimulatedClock(script.get('started_ns', 0))
    model = ScriptedModel(script['model_steps'], clock)
    reader = RecordingReader(script.get('reader', {}), clock)
    control = Control(script['task'], script.get('limits', CAPS), script.get('duration_ns', 600_000_000_000), clock, model, reader)
    return control.run()


def main(argv=None, *, load_script=None, reserve_output=None, publish=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--script', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    # Reusing an existing output never starts another registered run.
    if reserve_output is None: args.output.mkdir(parents=True, exist_ok=False)
    else: reserve_output(args.output)
    script = json.loads(args.script.read_bytes()) if load_script is None else load_script(args.script)
    result = run_script(script)
    if publish is None:
        with (args.output/'RESULT.json').open('x', encoding='utf8') as stream:
            json.dump(result, stream, indent=2, ensure_ascii=False, allow_nan=False)
    else: publish(args.output, frozen(result))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
