"""Bind independent quality to the predeclared paired performance decision."""

import hashlib
import json
from pathlib import Path
import statistics
import time

HERE=Path(__file__).resolve().parent


def read(path):
    return json.loads(Path(path).read_bytes())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    quality=read(HERE/'checks_saved/QUALITY_REVIEW.json')
    runtime=read(HERE/'RUNTIME_REVIEW.json')
    pins={}
    for document in (quality,runtime):
        for row in document['input_pins']:
            path=Path(row['path'])
            if sha(path)!=row['sha256'] or path.stat().st_size!=row['bytes']:
                raise ValueError('direct_review_input_changed/'+str(path))
            previous=pins.setdefault(str(path),row['sha256'])
            if previous!=row['sha256']:
                raise ValueError('conflicting_review_inputs')
    quality_passed=(quality['passed_checked_scope'] is True and quality['first_version_qualification'] is True
        and quality['formal_quality_passed']==quality['formal_quality_denominator']==6
        and quality['paired_quality_passed']==quality['paired_quality_denominator']==3
        and quality['state_quality_passed'] is True and runtime['passed_checked_scope'] is True)
    gate=read(HERE/'BASELINE.json')['performance_gate']
    performance=(runtime['service_paired_median_reduction']>=gate['service_paired_median_reduction_at_least']
        and runtime['owned_faster_pairs']>=gate['owned_faster_pairs_at_least']
        and runtime['optimized_owned_median_ms']<runtime['initial_owned_median_ms'])
    if quality_passed and performance!=runtime['performance_gate_passed']:
        raise ValueError('performance_gate_recalculation')
    selected='R1' if quality_passed and performance else 'R0'
    binding=read(HERE/(selected+'_RUN_BINDING.json'))
    root=HERE.parents[1]
    for row in binding['source_manifest']:
        if sha(root/row['path'])!=row['sha256']:
            raise ValueError('selected_generation_workspace_mismatch/'+row['path'])
    names=('checks_saved/QUALITY_REVIEW.json','checks_saved/STATE_QUALITY.json','checks_saved/PAIRED_QUALITY.json',
        'RUNTIME_REVIEW.json','FIRST_VERSION_HOTSPOT.json','SOURCE_FREEZE_R0.json','SOURCE_FREEZE_R1.json',
        'R0_RUN_BINDING.json','R1_RUN_BINDING.json','core_tests/R0_CHECKS.json','core_tests/R1_CHECKS.json',
        'transport_tests/R0_CHECKS.json','transport_tests/R1_READONLY_CONTROLS.json')
    decision=dict(schema='cross-scale-root-decision-v1',accepted_capability=quality_passed,
        accepted_performance_candidate=quality_passed and performance,selected_generation=selected,
        selected_source_sha256=binding['source_sha256'],selected_isolated_install=binding['install_root'],
        administrator_review='pending',report_pins={name:sha(HERE/name) for name in names},direct_verified_inputs=len(pins),
        quality_checks=quality['independent_check_count'],runtime_checks=len(runtime['checks']),
        actual_public_requests=quality['actual_public_requests'],actual_constructed_frames=quality['actual_constructed_frames'],
        actual_native_image_blocks=quality['actual_native_image_blocks'],budget=runtime['budget'],
        service_paired_median_reduction=runtime['service_paired_median_reduction'],
        owned_faster_pairs=runtime['owned_faster_pairs'],
        owned_median_reduction=1-runtime['optimized_owned_median_ms']/runtime['initial_owned_median_ms'],
        paired_costs=runtime['paired_costs'],
        retained_limits=['One fixed external qualification asset with exact rectangular task regions.',
            'Edge and near-equal-depth triangle ownership ambiguity remains reported.',
            'Source unit tests include synthetic PNG/NPZ encoding, earlier unprofiled image counts are explicitly unmeasured.',
            'Seven historical schema assertions fail on the accepted baseline as recorded.',
            'Current chat Agent Learning task binding remains pending.',
            'Model task quality and total model consumption have no new measurement in this batch.'],
        next_candidate='Use one explicit nonrectangular source-triangle region for a bounded read-only local observation and measurement task, reusing the current frame buffers and current-source mapping.',
        new_model_consumers=0,new_paid_API_calls=0,closed_ns=time.perf_counter_ns())
    with (HERE/'DECISION.json').open('x',encoding='utf8',newline='\n') as stream:
        json.dump(decision,stream,sort_keys=True,ensure_ascii=False,indent=2)
        stream.write('\n')
    print(json.dumps(dict(capability=quality_passed,performance=performance,selected=selected,
        service_median_reduction=decision['service_paired_median_reduction'],owned_median_reduction=decision['owned_median_reduction'],
        input_pins=len(pins))))


if __name__=='__main__':
    main()
