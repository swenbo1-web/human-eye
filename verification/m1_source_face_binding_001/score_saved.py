"""Source-quoted, six-slot offline quality and adoption for one frozen scene."""

import argparse
import base64
from collections import Counter
from fractions import Fraction
import hashlib
import importlib.util
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
ORDER = ('A1', 'B1', 'B2', 'A2', 'A3', 'B3')
INPUTS = {}


def raw(path):
    path = Path(path).resolve()
    value = path.read_bytes()
    INPUTS[str(path)] = hashlib.sha256(value).hexdigest()
    return value


def read(path):
    return json.loads(raw(path))


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def save(path, value):
    path = Path(path).resolve()
    if not path.is_relative_to(HERE):
        raise ValueError('new_namespace_output_required')
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2)
        stream.write('\n')


def terminal_binding(run, launch, slot, consumer):
    """Actual routed producer schema, including failed/not-run slots in six."""
    failed = []

    def need(name, passed):
        if not passed:
            failed.append(name)

    need('run.schema', run.get('schema') == 'source-face-binding-six-route-v1')
    need('launch.schema', launch.get('schema') == 'source-face-binding-launch-v1')
    records = run.get('records')
    valid_records = (type(records) is list and len(records) == 6
                     and all(type(r) is dict for r in records)
                     and [r.get('slot') for r in records] == list(ORDER)
                     and all(r.get('group') == 'P' and r.get('comparison_arm') == r.get('slot', '')[:1] for r in records))
    need('run.records', valid_records)
    expected_sequence = [dict(slot=s, group='P', comparison_arm=s[0]) for s in ORDER]
    need('run.comparison_sequence', run.get('comparison_sequence') == expected_sequence)
    need('run.internal_execution_group', run.get('internal_execution_group') == 'P')
    need('launch.internal_execution_group', launch.get('internal_execution_group') == 'P')
    need('launch.comparison_arms', launch.get('comparison_arms') == {s:s[0] for s in ORDER})
    for key, expected in (('planned_routes', 6), ('planned_user_turns', 6), ('outer_retries', 0)):
        need('run.' + key, type(run.get(key)) is int and run[key] == expected)
    need('run.terminal_errors', run.get('terminal_errors') == [])
    need('launch.terminal_errors', launch.get('terminal_errors') == [])
    need('launch.outer_retries', type(launch.get('outer_retries')) is int and launch['outer_retries'] == 0)
    if valid_records:
        for key, expected in (('actual_routes', sum(r.get('route_invoked') is True for r in records)),
                              ('actual_CLI_processes', sum(r.get('consumer_pid') is not None for r in records))):
            need('run.' + key, type(run.get(key)) is int and run[key] == expected)
            need('launch.' + key, type(launch.get(key)) is int and launch[key] == expected)
        row = next(r for r in records if r['slot'] == slot)
        need('slot.execution_state', row.get('execution_state') == 'completed')
        need('launch.execution_state', launch.get('execution_states', {}).get(slot) == row.get('execution_state'))
        need('slot.outer_valid_completion', row.get('outer_valid_completion') is True)
        need('slot.route_invoked', row.get('route_invoked') is True)
        for key in ('errors', 'common_image_faults', 'slot_wrapper_errors', 'slot_wrapper_publication_errors'):
            need('slot.' + key, row.get(key) == [])
        for key in ('runtime_binding', 'runtime_exit', 'owner_process_cleanup', 'consumer_process_cleanup'):
            need('slot.' + key, type(row.get(key)) is dict and row[key].get('confirmed') is True)
    need('consumer.valid_completion', consumer.get('valid_completion') is True)
    for key in ('runtime_binding', 'runtime_exit'):
        need('consumer.' + key, type(consumer.get(key)) is dict and consumer[key].get('confirmed') is True)
    return {'passed': not failed, 'failed_fields': failed}


class Grader:
    def __init__(self, truth, pixel_truth, runtime):
        self.truth, self.pixel_truth, self.runtime = truth, pixel_truth, Path(runtime).resolve()
        self.saved = load('_occluded_transfer_saved', HERE / 'saved_evidence.py')
        self.contract = load('_occluded_transfer_result_contract',
                             HERE.parent / 'm4_consumer_error_contract_001/result_contract.py')
        self.targets = {r['roi_id']: r for r in truth['regions']}
        self.aliases = {}
        self.sources = {}
        self.source_paths = {}

    def identity(self, value):
        if type(value) is not dict:
            return None
        matches = []
        if 'roi_id' in value:
            matches.append(self.aliases.get(value['roi_id']))
        if 'source_triangle_indices' in value:
            faces = value['source_triangle_indices']
            if type(faces) is not list or any(type(v) is not int for v in faces) or len(set(faces)) != len(faces):
                return None
            if 'object_index' in value or 'object_name' in value:
                found = [key for key, r in self.targets.items()
                         if sorted(faces) == sorted(r['source_triangle_indices'])
                         and ('object_index' not in value or value['object_index'] == r['object_index'])
                         and ('object_name' not in value or value['object_name'] == r['object_name'])]
            else:
                found = [key for key, r in self.targets.items()
                         if sorted(faces) == sorted(r['global_source_triangle_indices'])]
            matches.append(found[0] if len(found) == 1 else None)
        if 'quad_world_m' in value:
            corners = set(map(self.saved.vec, value['quad_world_m']))
            found = [key for key, r in self.targets.items() if corners == set(map(self.saved.vec, r['quad_world_m']))]
            matches.append(found[0] if len(found) == 1 else None)
        if 'center_world_m' in value and 'front_direction_world' in value:
            found = [key for key, r in self.targets.items()
                     if self.saved.vec(value['center_world_m']) == self.saved.vec(r['center_world_m'])
                     and self.saved.same_normal(value['front_direction_world'], r['front_direction_world'])]
            matches.append(found[0] if len(found) == 1 else None)
        return matches[0] if matches and None not in matches and len(set(matches)) == 1 else None

    def tools(self, owner, consumer):
        calls = consumer['tool_calls']
        tools = read(owner / 'TOOLS.json')['tools']
        if len(calls) != len(tools) or len(tools) > 12 or [t['attempt'] for t in tools] != list(range(1, len(tools)+1)):
            raise ValueError('tool_count_budget_or_sequence')
        paths = set()
        image_hashes = set()
        for tool, call in zip(tools, calls):
            folder = owner / ('tool_' + str(tool['attempt']).zfill(2))
            request = read(folder / 'REQUEST.json')
            path = folder / 'RESPONSE.json'
            if not path.exists():
                path = folder / 'ERROR_RESPONSE.json'
            response = read(path)
            item = call['item']
            if request['params']['name'] != item['tool'] or request['params']['arguments'] != item['arguments']:
                raise ValueError('current_tool_request_binding')
            if type(request.get('id')) is not type(response.get('id')) or request.get('id') != response.get('id'):
                raise ValueError('current_tool_response_id')
            if not self.contract.bind_tool_result(response, item)['matched']:
                raise ValueError('current_tool_result_binding')
            paths.add(str(path.resolve()))
            for block in item['result']['content']:
                if block.get('type') == 'image':
                    image_hashes.add(hashlib.sha256(base64.b64decode(block['data'], validate=True)).hexdigest())
        return paths, image_hashes

    def bind_sources(self, row, owner, answer, tool_paths):
        self.sources, self.source_paths = {'final': answer}, {}
        self.source_kinds = {'final': 'final'}
        for source in row.get('sources', []):
            identity = source['id']
            path = Path(source['path']).resolve()
            if identity in self.sources or hashlib.sha256(raw(path)).hexdigest() != source['sha256']:
                raise ValueError('source_duplicate_or_SHA')
            kind = source['kind']
            if kind == 'tool_result':
                if str(path) not in tool_paths:
                    raise ValueError('source_not_actual_tool_result')
                body = '\n'.join(b['text'] for b in read(path)['result']['content'] if b.get('type') == 'text')
            elif kind == 'cited_artifact':
                citation = source.get('final_citation_excerpt', '')
                if not path.is_relative_to(owner) or not citation or citation not in answer or path.name not in citation:
                    raise ValueError('artifact_not_current_and_final_cited')
                body = raw(path).decode('utf-8-sig')
            elif kind == 'tool_request':
                responses = {str(path.with_name(name)) for name in ('RESPONSE.json', 'ERROR_RESPONSE.json')}
                if path.name != 'REQUEST.json' or not responses.intersection(tool_paths):
                    raise ValueError('request_not_current_tool')
                body = raw(path).decode('utf-8-sig')
            else:
                raise ValueError('source_kind')
            self.sources[identity], self.source_paths[identity] = body, path
            self.source_kinds[identity] = kind
        excerpt = row.get('coverage_use_excerpt')
        if type(excerpt) is not str or not excerpt or excerpt not in answer:
            raise ValueError('final_coverage_use_excerpt_required')

    def support(self, items, allow_request=False):
        items = items if type(items) is list else [items]
        return bool(items) and all(type(item) is dict and type(item.get('excerpt')) is str
            and item['excerpt'] and item.get('source_id') in self.sources
            and item['excerpt'] in self.sources[item['source_id']]
            and (allow_request or self.source_paths.get(item['source_id'], Path('final')).name != 'REQUEST.json')
            for item in items)

    def witness(self, identity, claim, evidence):
        frame = evidence.get(claim.get('ref'))
        if frame is None or claim.get('view') != frame['view_name']:
            return False
        row = next(r for r in frame['rows'] if r['roi_id'] == identity)
        if not row['complete_readable']:
            return False
        for claim_key, fact_key in (('surface_pixels', 'surface_pixels'), ('boundary_pixels', 'boundary_pixels')):
            if claim_key in claim and claim[claim_key] != row[fact_key]:
                return False
        return True

    def extent(self, row, target):
        corners = set(map(self.saved.vec, target['quad_world_m']))
        if 'quad_world_m' in row:
            return set(map(self.saved.vec, row['quad_world_m'])) == corners
        if 'bounds_world_m' in row:
            expected = [tuple(min(p[k] for p in corners) for k in range(3)),
                        tuple(max(p[k] for p in corners) for k in range(3))]
            return list(map(self.saved.vec, row['bounds_world_m'])) == expected
        if 'half_edge_u_world_m' in row and 'half_edge_v_world_m' in row:
            center, u, v = (self.saved.vec(row[k]) for k in ('center_world_m', 'half_edge_u_world_m', 'half_edge_v_world_m'))
            return {tuple(center[k]+a*u[k]+b*v[k] for k in range(3))
                    for a, b in ((-1, -1), (1, -1), (1, 1), (-1, 1))} == corners
        return False

    def unsupported_identity(self, identity):
        if type(identity) is not dict:
            return False
        expected = self.truth['unsupported_source_triangles']
        global_faces = sorted(r['global_source_triangle_index'] for r in expected)
        checks = []
        if 'global_source_triangle_indices' in identity:
            faces = identity['global_source_triangle_indices']
            checks.append(type(faces) is list and all(type(v) is int for v in faces)
                          and len(set(faces)) == len(faces) and sorted(faces) == global_faces)
        for field in ('object_index', 'object_name'):
            if field in identity:
                checks.append({r[field] for r in expected} == {identity[field]})
        if 'source_triangle_indices' in identity:
            faces = identity['source_triangle_indices']
            checks.append(('object_index' in identity or 'object_name' in identity)
                          and type(faces) is list and all(type(v) is int for v in faces)
                          and len(set(faces)) == len(faces)
                          and sorted(faces) == sorted(r['source_triangle_index'] for r in expected))
        return bool(checks) and all(checks)

    def score_slot(self, row, run, launch):
        slot = row['slot_id']
        folder = self.runtime / slot
        owner, consumer_path = folder / 'o', folder / 'c/CONSUMER.json'
        consumer = read(consumer_path)
        terminal = terminal_binding(run, launch, slot, consumer)
        checks = []

        def check(name, value):
            checks.append({'check': name, 'passed': bool(value)})

        check('actual_routed_terminal', terminal['passed'])
        answer_path = folder / 'c/PUBLIC_FINAL.txt'
        answer = raw(answer_path).decode('utf-8')
        check('current_final_binding', Path(row['raw_answer_path']).resolve() == answer_path.resolve()
              and row['raw_answer_sha256'] == hashlib.sha256(raw(answer_path)).hexdigest()
              and answer == consumer['final'])
        tool_paths, image_hashes = self.tools(owner, consumer)
        self.bind_sources(row, owner, answer, tool_paths)
        evidence = self.saved.evaluate_owner(owner, self.truth)
        self.aliases = evidence['aliases']
        check('actual_owner_comparison_arm', evidence['comparison_arm'] == slot[0])
        check('current_product_facts_correct', evidence['product_errors'] == [])
        required = set(self.pixel_truth['complete_readable_roi_ids'])
        unknown = set(self.targets)-required
        panels = row.get('panels', [])
        identities = [self.identity(p.get('identity')) for p in panels]
        check('exact_supported_surface_bijection', len(identities) == len(self.targets)
              and len(set(identities)) == len(identities) and set(identities) == set(self.targets))
        for panel, identity in zip(panels, identities):
            check('panel_source:' + str(identity), self.support(panel.get('support')))
            if identity is None:
                continue
            if identity in required:
                views = panel.get('views', [])
                check('complete_current_witness:' + identity, panel.get('status') == 'covered' and bool(views)
                      and all(self.witness(identity, v, evidence['by_ref']) for v in views))
            else:
                reason = self.pixel_truth['remaining_reasons'][identity]
                check('bounded_unknown:' + identity, panel.get('status') == 'unknown'
                      and panel.get('reason_code') == reason and panel.get('finite_pool_only') is True)
        remaining = row.get('remaining', [])
        remaining_ids = [self.identity(item) for item in remaining]
        check('explicit_exact_remaining_set', len(set(remaining_ids)) == len(remaining_ids) and set(remaining_ids) == unknown)
        unsupported = row.get('unsupported', [])
        check('unsupported_component', len(unsupported) == 1 and unsupported[0].get('status') == 'unsupported'
              and unsupported[0].get('domain') == 'outside_supported_rectangle_domain'
              and unsupported[0].get('component_count') == 1 and unsupported[0].get('shape') == 'nonrectangular'
              and self.unsupported_identity(unsupported[0].get('identity'))
              and self.support(unsupported[0].get('support')))
        check('bounded_finite_pool_scope', row.get('finite_pool_only') is True
              and row.get('global_invisibility_overclaim') is False and self.support(row.get('finite_pool_support')))
        check('no_unretracted_contradictions', row.get('contradictions') == [])
        pixels = row.get('pixel_targets', [])
        expected_pixels = {p['id']: p for p in self.truth['pixel_targets']}
        check('exact_two_pixel_targets', Counter(p.get('id') for p in pixels) == Counter(expected_pixels.keys()))
        for p in pixels:
            expected = expected_pixels.get(p.get('id'))
            if expected is None:
                continue
            identity = self.identity(p.get('identity'))
            frame = evidence['by_ref'].get(p.get('ref'))
            target = self.targets[expected['region_id']]
            x, y = expected['x'], expected['y']
            position = list(self.targets).index(expected['region_id'])
            check('pixel_location:' + p['id'], identity == expected['region_id'] and frame is not None
                  and frame['view_name'] == expected['view_name'] and p.get('view') == expected['view_name']
                  and frame['raw_region_by_pixel'][y*512+x] == position
                  and self.saved.vec(p.get('center_world_m', [])) == self.saved.vec(target['center_world_m'])
                  and self.saved.same_normal(p.get('front_direction_world', []), target['front_direction_world'])
                  and self.extent(p, target) and self.support(p.get('support')))
        source_targets = row.get('source_targets', [])
        expected_sources = {p['id']: p for p in self.truth['source_targets']}
        check('exact_two_source_targets', Counter(p.get('id') for p in source_targets) == Counter(expected_sources.keys()))
        for p in source_targets:
            expected = expected_sources.get(p.get('id'))
            if expected is None:
                continue
            identity = self.identity(p.get('identity'))
            key = expected['region_id']
            valid = identity == key and self.support(p.get('support')) and p.get('finite_pool_only') is True
            if key in required:
                valid = valid and p.get('status') == 'covered' and self.witness(key, p.get('witness', {}), evidence['by_ref'])
            else:
                valid = valid and p.get('status') == 'unknown' and p.get('reason_code') == self.pixel_truth['remaining_reasons'][key]
            check('source_target:' + p['id'], valid)
        quality = all(c['passed'] for c in checks)
        adoption = self.adoption(row, owner, consumer, evidence, answer, quality)
        binding_use = self.source_binding_use(row, owner, consumer, evidence)
        diagnostics = self.process_diagnostics(row, owner, consumer, evidence)
        return {'slot_id': slot, 'execution_state': next(r['execution_state'] for r in run['records'] if r['slot'] == slot),
                'final_quality_passed': quality, 'terminal_binding': terminal, 'checks': checks,
                'errors': [r['check'] for r in checks if not r['passed']], 'adoption': adoption,
                'comparison_arm': slot[0], 'source_binding_use': binding_use, 'process_diagnostics': diagnostics,
                'saved_evidence': self.saved.summary(evidence), 'actual_tool_calls': len(consumer['tool_calls']),
                'CLI_image_ref_hashes': sorted(image_hashes)}

    def source_binding_use(self, row, owner, consumer, evidence):
        """Bind declared consumption evidence without inferring use from delivery."""
        claims = row.get('source_binding_use', {}).get('claims', [])
        first_response = (owner / 'tool_01/RESPONSE.json').resolve()
        actual_default = evidence.get('source_face_binding_delivered') is True
        adopted, rejected = [], []
        operations = {'source_face_to_region_lookup', 'region_to_source_faces',
                      'pixel_source_face_to_region', 'direct_table_reasoning'}
        for index, claim in enumerate(claims):
            identity = self.identity(claim.get('identity'))
            product_support = claim.get('product_support', [])
            product_support = product_support if type(product_support) is list else [product_support]
            product_origin = bool(product_support) and all(
                self.source_paths.get(item.get('source_id')) == first_response for item in product_support)
            operation_support = claim.get('operation_support', [])
            task_support = claim.get('task_use_support', [])
            task_support = task_support if type(task_support) is list else [task_support]
            final_task_origin = bool(task_support) and all(
                self.source_kinds.get(item.get('source_id')) in ('final', 'cited_artifact')
                for item in task_support)
            valid = (actual_default and identity is not None and product_origin
                     and claim.get('operation') in operations and claim.get('binding_scoped') is True
                     and claim.get('dataflow_confirmed_by_review') is True
                     and self.support(product_support)
                     and self.support(operation_support, allow_request=True)
                     and final_task_origin and self.support(task_support))
            if valid:
                adopted.append(identity)
            else:
                rejected.append(index)
        return {'default_binding_received': actual_default,
                'actual_binding_adopted': bool(actual_default and adopted),
                'source_quoted_used_regions': sorted(set(adopted)), 'rejected_claim_indices': rejected,
                'mere_field_presence_counts_as_adoption': False,
                'manual_dataflow_entailment_review_required': True,
                'comparison_arm': evidence['comparison_arm']}

    def process_diagnostics(self, row, owner, consumer, evidence):
        """Keep reviewed consumer work separate from answer correctness."""
        expected = list(range(1, len(consumer['tool_calls']) + 1))
        output = {}
        for name in ('geometry_reverse_lookup', 'full_witness_pixel_recomputation'):
            declaration = row.get('process_diagnostics', {}).get(name, {})
            observed = declaration.get('observed')
            complete = (declaration.get('reviewed_tool_attempts') == expected
                        and declaration.get('review_complete') is True
                        and self.support(declaration.get('support'), allow_request=True))
            output[name] = {'observed': observed if complete and type(observed) is bool else None,
                            'review_complete': complete, 'declared_reason': declaration.get('reason'),
                            'interpretation': 'Actual consumer operation, with necessity unmeasured.'}
        output['native_supplement_necessity'] = 'unmeasured'
        return output

    def adoption(self, row, owner, consumer, evidence, answer, quality):
        product = row.get('product_adoption', {})
        claims = product.get('claims', [])
        first_response = (owner / 'tool_01/RESPONSE.json').resolve()
        adopted = []
        for claim in claims:
            identity = self.identity(claim.get('identity'))
            supports = claim.get('product_support', [])
            supports = supports if type(supports) is list else [supports]
            product_provenance = bool(supports) and all(
                self.source_paths.get(s.get('source_id')) == first_response for s in supports)
            excerpt = claim.get('final_use_excerpt', '')
            if (identity is not None and product_provenance and self.support(supports)
                    and type(excerpt) is str and excerpt and excerpt in answer):
                adopted.append(identity)
        actual = bool(evidence['actual_product_calls'] and adopted)
        extra = row.get('extra_tool_classification', [])
        attempts = list(range(2 if evidence['actual_product_calls'] else 1, len(consumer['tool_calls'])+1))
        errors = []
        if [r.get('attempt') for r in extra] != attempts:
            errors.append('all_actual_extra_tools_require_classification')
        for item in extra:
            if not self.support(item.get('support'), allow_request=True):
                errors.append('extra_tool_classification_missing_exact_source:' + str(item.get('attempt')))
        direct = {'public_json_query', 'cached_image_read', 'existing_buffer_lookup', 'format_artifact', 'cached_product_observation'}
        native = {'raw_source_read', 'native_computation', 'new_native_observation'}
        categories = [r.get('category') for r in extra]
        unknown = bool(errors) or any(c not in direct | native for c in categories)
        return {'actual_product_calls': evidence['actual_product_calls'],
                'actual_product_facts_adopted': actual, 'source_quoted_adopted_regions': sorted(set(adopted)),
                'direct_only': None if unknown else bool(quality and actual and all(c in direct for c in categories)),
                'additional_native_supplement_observed': any(c in native for c in categories),
                'extra_tool_categories': categories, 'classification_errors': errors,
                'necessity_of_native_supplement': 'unmeasured',
                'normalization_entailment_review_required': True}


def score(args):
    contract = read(HERE / 'admin/SCORING_CONTRACT.json')
    if contract['schema'] != 'source-face-binding-scoring-contract-v1':
        raise ValueError('frozen_scoring_contract')
    for path, expected in contract['files_sha256'].items():
        if hashlib.sha256(raw(path)).hexdigest() != expected:
            raise ValueError('frozen_scoring_source_changed:' + path)
    normalized = read(args.normalized)
    if normalized['schema'] != 'source-face-binding-normalized-v1':
        raise ValueError('normalization_schema')
    rows = normalized['slots']
    if len(rows) != 6 or Counter(r['slot_id'] for r in rows) != Counter(ORDER):
        raise ValueError('six_unique_normalized_slots')
    run, launch = read(args.runtime_root / 'RUN_RESULT.json'), read(args.runtime_root / 'LAUNCH_RESULT.json')
    truth, pixel_truth = read(HERE / 'admin/TRUTH.json'), read(HERE / 'admin/PIXEL_TRUTH.json')
    reference = read(HERE / 'admin/REFERENCE_TRUTH_BINDING.json')
    for name, specification in reference['files'].items():
        if hashlib.sha256(raw(specification['path'])).hexdigest() != specification['sha256']:
            raise ValueError('reference_truth_source_changed:' + name)
    if (hashlib.sha256(raw(HERE / 'admin/TRUTH.json')).hexdigest() != reference['files']['truth']['sha256']
            or hashlib.sha256(raw(HERE / 'admin/PIXEL_TRUTH.json')).hexdigest() != reference['files']['pixels']['sha256']
            or pixel_truth['geometric_truth_sha256'] != reference['files']['truth']['sha256']
            or pixel_truth['source_freeze_sha256'] != reference['files']['freeze']['sha256']):
        raise ValueError('original_independent_truth_provenance')
    qualification = read(HERE / 'admin/QUALIFICATION.json')
    if (qualification['passed'] is not True or qualification['status'] != 'qualified'
            or qualification['source_freeze_sha256'] != hashlib.sha256(raw(HERE / 'FROZEN.json')).hexdigest()):
        raise ValueError('current_final_candidate_qualification')
    run_specification = qualification['qualification_run']
    if hashlib.sha256(raw(run_specification['path'])).hexdigest() != run_specification['sha256']:
        raise ValueError('actual_qualification_run_binding')
    plan = read(HERE / 'PLAN.json')
    for arm in ('A', 'B'):
        manifest = read(plan['inputs']['manifests'][arm])
        for name, expected in truth['input_sha256'].items():
            specification = manifest[name]
            if (specification['sha256'] != expected
                    or hashlib.sha256(raw(specification['path'])).hexdigest() != expected):
                raise ValueError('current_owner_scene_differs_from_reference_truth:' + arm + ':' + name)
    grader = Grader(truth, pixel_truth, args.runtime_root)
    scores = []
    for slot in ORDER:
        row = next(r for r in rows if r['slot_id'] == slot)
        outer = next((r for r in run['records'] if r['slot'] == slot), {})
        if outer.get('execution_state') == 'not_run':
            scores.append({'slot_id': slot, 'execution_state': 'not_run', 'final_quality_passed': False,
                           'adoption': {'actual_product_facts_adopted': False, 'direct_only': None}, 'errors': ['not_run']})
            continue
        try:
            scores.append(grader.score_slot(row, run, launch))
        except (OSError, ValueError, KeyError, TypeError, IndexError, ZeroDivisionError) as error:
            scores.append({'slot_id': slot, 'execution_state': outer.get('execution_state', 'unknown'),
                           'final_quality_passed': False, 'adoption': {'actual_product_facts_adopted': False, 'direct_only': None},
                           'errors': [{'type': type(error).__name__, 'message': str(error)}]})
    output = {'schema': 'source-face-binding-quality-v1', 'denominator': 6, 'slots': scores,
              'all_six_quality_complete': all(r['final_quality_passed'] for r in scores),
              'actual_product_fact_adoption_count': sum(r['adoption']['actual_product_facts_adopted'] for r in scores),
              'B_actual_source_binding_adoption_count': sum(r['slot_id'][0] == 'B' and r.get('source_binding_use', {}).get('actual_binding_adopted') is True for r in scores),
              'cost_analysis_performed': False, 'new_model_product_raster_calls': 0,
              'normalization_entailment_review_required': True, 'inputs_sha256': dict(sorted(INPUTS.items()))}
    save(args.output, output)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--normalized', type=Path, required=True)
    parser.add_argument('--runtime-root', type=Path, default=Path('D:/he_source_face_001/formal'))
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.runtime_root.resolve() != Path('D:/he_source_face_001/formal').resolve():
        raise ValueError('fixed_new_formal_root')
    result = score(args)
    print(json.dumps({'quality': result['all_six_quality_complete'], 'denominator': 6,
                      'B_binding_adoption': result['B_actual_source_binding_adoption_count']}))
    return 0 if result['all_six_quality_complete'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
