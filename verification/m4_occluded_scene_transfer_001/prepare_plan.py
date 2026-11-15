"""Bind the single frozen scene and common task to six registered fresh slots."""

import importlib.util
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('_transfer_plan_launcher', HERE / 'launcher.py')
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


def main():
    if (HERE/'PLAN.json').exists() or (HERE/'FROZEN.json').exists():
        raise FileExistsError('single_prepared_plan')
    suffix = HERE/'inputs/PROMPT_SUFFIX.txt'
    suffix_bytes = suffix.read_bytes()
    for name in ('NumPy', 'Pillow', 'Fraction', 'Shapely'):
        if name.encode() not in suffix_bytes:
            raise ValueError('common_available_library_missing_' + name)
    prompts = {}
    for group, prefix in launcher.PREFIXES.items():
        prefix_path = HERE/('inputs/PREFIX_' + group + '.txt')
        prompt_path = HERE/('inputs/PROMPT_' + group + '.txt')
        for path, raw in ((prefix_path, prefix), (prompt_path, prefix+b'\n\n'+suffix_bytes)):
            with path.open('xb') as stream:
                stream.write(raw)
        prompts[group] = str(prompt_path)
    external = launcher.EXTERNAL
    plan = dict(schema='occluded-scene-transfer-001-plan-v1', task='M4-OCCLUDED-SCENE-TRANSFER-001',
        administrator_plan_sha256='100ad9b15dfc28c7a8efdd77ac6531c418d55d58439931e50d1463efac771214',
        baseline_commit='b0e2fcfe90b7b535105e24dff9c34b36c27a26af',
        product_commit='d12c7ab248452ff253452007d0635f2d662f0191',
        product_source_sha256=launcher.PRODUCT_SHA256, product_install_root='D:/he_view_reuse_001/product',
        external_root=str(external), runtime_root=str(external/'formal'), preparation_root=str(external/'preparation'),
        model_consumer_enabled=True, authentication='existing ChatGPT Pro login',
        formal_batch_attempts=1, qualification_runs=1, qualification_model_consumers=0,
        qualification_status_required='qualified', outer_retries=0,
        preparation_render_cap=12, formal_render_cap=36, total_new_render_cap=48,
        implementation_container_render_cap=48, route_deadline_seconds=450,
        max_tool_calls=12, max_tool_business_admissions=12, max_render_attempts=6,
        requested_model='gpt-6.1-sol', requested_reasoning_effort='medium', requested_service_tier='default',
        inputs=dict(input_manifest=str(HERE/'inputs/SOURCES.json'), prompts=prompts,
            common_suffix=str(suffix), prefixes={g:str(HERE/('inputs/PREFIX_'+g+'.txt')) for g in ('N','P')},
            qualification=str(HERE/'admin/QUALIFICATION.json')),
        expected_suffix_sha256=launcher.sha(suffix),
        expected_prompt_sha256={g:launcher.sha(p) for g,p in prompts.items()},
        sequence=[dict(slot=s,group=g) for s,g in launcher.SEQUENCE],
        paired_slots=[['N1','P1'],['N2','P2'],['N3','P3']],
        shared_dependency=launcher.shared_dependency(),
        ordinary_answer_error_continues=True,
        stop_conditions=['common source/interface failure','changed source','unknown real process state','genuine service/account blocker','in-domain product factual error'],
        quality_before_cost=True,
        decision_registration=dict(quality_gate=dict(N_complete_correct=3,P_complete_correct=3,P_actual_fact_adoption=3),
            complete_time_ratio_median_max=0.90, minimum_faster_pairs=2,
            raw_input_plus_output_P_no_greater_than_N=True,
            comparable_usage_required=True, direct_only='diagnostic'),
        qualification_command=[launcher.runtime_bindings()['base_python']['path'],'-I','-B','-X','utf8',str(HERE/'qual_driver.py'),'--qualify'],
        evidence_scope='CAPTURE_REPLAY synthetic scene; independent geometry and actual qualification-pixel oracle. Limited to this task.',
        pixel_origin='zero-based top-left', prompt_join='exact entry prefix + two LF + exact common suffix')
    launcher.input_checks(plan)
    launcher.save(HERE/'PLAN.json', plan, exclusive=True)
    print(json.dumps(dict(plan=str(HERE/'PLAN.json'), suffix_sha256=launcher.sha(suffix),
        prompt_sha256=plan['expected_prompt_sha256'], limits=[12,36,48])))


if __name__ == '__main__':
    main()
