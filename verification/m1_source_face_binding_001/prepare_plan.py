"""Bind the fixed old task to two product versions and one common prompt."""
import importlib.util
from pathlib import Path
import json

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('_m1_prepare_launcher', HERE / 'launcher.py')
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


def main():
    if (HERE / 'PLAN.json').exists():
        raise FileExistsError('prepared_plan_already_exists')
    target = HERE / 'inputs'
    target.mkdir(exist_ok=True)
    old = launcher.read(launcher.PREVIOUS / 'inputs/SOURCES.json')
    bindings = dict(A=old['product_binding'], B=dict(path=str(HERE / 'build/RUN_BINDING.json'),
        sha256=launcher.sha(HERE / 'build/RUN_BINDING.json')))
    manifests = {}
    external = launcher.EXTERNAL
    for arm in ('A', 'B'):
        binding = launcher.read(bindings[arm]['path'])
        value = {key:old[key] for key in ('schema', 'replay_label', 'scene', 'cameras', 'capture',
            'tasks', 'public_surface_color_rgb')}
        value.update(product_binding=bindings[arm], expected_product_source_sha256=binding['source_sha256'],
            comparison_arm=arm, budget_contract=dict(external_root=str(external),
                formal_root=str(external / 'formal'), preparation_root=str(external / 'preparation'),
                ledger_root=str(external / 'raster_budget'), preparation_cap=12,
                formal_cap=36, total_cap=48, per_slot_cap=6))
        path = target / ('SOURCES_' + arm + '.json')
        launcher.save(path, value, exclusive=True)
        manifests[arm] = str(path)
    prompt = target / 'PROMPT.txt'
    with prompt.open('xb') as stream:
        stream.write((launcher.PREVIOUS / 'inputs/PROMPT_P.txt').read_bytes())
    plan = dict(schema='source-face-binding-001-plan-v1', task='M1-SOURCE-FACE-BINDING-001',
        baseline_commit='1f3db153d4a46363ed3e64103d495bbc5ee65864',
        administrator_plan_sha256='fe0862499c7ffe53a2dfb3208a8742afc8b424d6877cd631ad4350aeef685837',
        products=bindings, external_root=str(external), runtime_root=str(external / 'formal'),
        preparation_root=str(external / 'preparation'), model_consumer_enabled=True,
        authentication='existing ChatGPT Pro login', formal_batch_attempts=1,
        qualification_model_consumers=0, qualification_total_cap=12, outer_retries=0,
        preparation_render_cap=12, formal_render_cap=36, total_new_render_cap=48,
        route_deadline_seconds=450, max_tool_calls=12, max_render_attempts=6,
        requested_model='gpt-6.1-sol', requested_reasoning_effort='medium', requested_service_tier='default',
        inputs=dict(manifests=manifests, prompt=str(prompt), qualification=str(HERE / 'admin/QUALIFICATION.json')),
        expected_prompt_sha256=launcher.sha(prompt),
        sequence=[dict(slot=s, group=g, comparison_arm=s[0]) for s,g in launcher.SEQUENCE],
        paired_slots=[['A1','B1'],['A2','B2'],['A3','B3']],
        shared_dependency=launcher.shared_dependency(), internal_execution_group='P',
        ordinary_answer_error_continues=True, quality_before_cost=True,
        limits_scope='All qualification attempts share preparation12; formal36 is distinct; task48 is cumulative.',
        decision_registration=dict(A_complete_correct=3, B_complete_correct=3,
            B_actual_source_binding_adoption=3, maximum_median_B_over_A=.90,
            minimum_B_faster_pairs=2, B_raw_input_plus_output_no_greater_than_A=True,
            comparable_usage_required=True, direct_only='diagnostic'))
    launcher.input_checks(plan)
    launcher.save(HERE / 'PLAN.json', plan, exclusive=True)
    print(json.dumps(dict(plan=str(HERE / 'PLAN.json'), prompt_sha256=launcher.sha(prompt),
        products=bindings, sequence=plan['sequence'])))


if __name__ == '__main__':
    main()
