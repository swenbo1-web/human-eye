"""Conjoin corrected region quality, real repeated-work reduction and fixed costs."""

import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]


def read(path):
    return json.loads(Path(path).read_bytes())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    quality=read(HERE/'checks_saved/QUALITY_REVIEW.json')
    runtime=read(HERE/'RUNTIME_REVIEW.json')
    pins={}
    for report in (quality,runtime):
        for row in report['input_pins']:
            path=Path(row['path'])
            if sha(path)!=row['sha256'] or path.stat().st_size!=row['bytes']:
                raise ValueError('review_input_changed/'+str(path))
            previous=pins.setdefault(str(path),row['sha256'])
            if previous!=row['sha256']:
                raise ValueError('review_input_conflict')
    quality_passed=(quality['passed'] is True and quality['corrected_formal_quality']['all_passed'] is True
        and quality['corrected_formal_quality']['fresh_owned_slots']==6 and quality['state']['passed'] is True
        and runtime['passed'] is True)
    reduced=(quality['optimization']['cold_actual_frame_array_decodes']==0
        and quality['optimization']['cold_actual_fresh_payload_reuses']==1)
    accepted=quality_passed and reduced and runtime['performance_timing_gate'] is True
    selected='R1' if accepted else 'R0F'
    binding=read(HERE/(selected+'_RUN_BINDING.json'))
    for row in binding['source_manifest']:
        if sha(ROOT/row['path'])!=row['sha256']:
            raise ValueError('workspace_differs_from_selected_generation/'+row['path'])
    reports=['checks_saved/QUALITY_REVIEW.json','checks_saved/THREE_PAIR_QUALITY.json','checks_saved/state.json',
        'RUNTIME_REVIEW.json','FIRST_CORRECTED_HOTSPOT.json','LOCAL_CAMERA_CORRECTION.json',
        'SOURCE_FREEZE_R0.json','SOURCE_FREEZE_R0F.json','SOURCE_FREEZE_R1.json',
        'R0_RUN_BINDING.json','R0F_RUN_BINDING.json','R1_RUN_BINDING.json','transport_tests/SOURCE_REVIEW.json']
    result=dict(schema='source-region-root-decision-v1',accepted_capability=quality_passed,
        accepted_optimization=accepted,selected_generation=selected,selected_source_sha256=binding['source_sha256'],
        selected_install=binding['install_root'],administrator_review='pending',
        failed_initial_local_qualification_retained=True,first_corrected_local_qualification='pair1_R0',
        report_pins={name:sha(HERE/name) for name in reports},direct_verified_review_inputs=len(pins),
        budget=runtime['budget'],paired_costs=runtime['pairs'],
        median_two_request_service_reduction=runtime['paired_service_reduction_median'],
        median_owned_reduction=runtime['complete_owned_reduction'],
        source_domain='Object-local current evaluated capture triangle rows. Native vertex/polygon ordering was qualified on this fixed asset.',
        region_ref_contract='Self-contained document/host instance/current complete-scene generation/ordered geometry/selected triangle set. Reference object is independent of region identity.',
        observations='Actual selected-triangle pixel samples with complete selected-set measurement. General complete-surface visibility remains unknown.',
        repeated_work_evidence='R1 cold fresh_payload_reuses=1 and frame_array_decodes=0 are instrumented. R0F one NPZ decode is inferred from its frozen successful source path and original frame, with no retroactive instrument claim.',
        retained_limits=['Initial full-scene camera yielded 13 pixels, retained as failed local-view qualification.',
            'Fresh-payload trial initial publication window failed synthetic review and was corrected before any R1 live test.',
            'Fixture and product-independent saved oracle share an author.',
            'Earlier legacy test expectations and mock image encoding costs are recorded separately.',
            'Compressed temporary bytes are counted. Allocator overhead, peak RSS and background machine load were not measured.',
            'Current chat Agent Learning binding remains pending.',
            'No model consumer, training or paid task API call was added.'],
        next_candidate='Qualify native-to-current-evaluated source correspondence for one fixed real rigged asset, then run the same bounded read-only region observation and measurement on a small declared region.')
    with (HERE/'DECISION.json').open('x',encoding='utf8',newline='\n') as stream:
        json.dump(result,stream,sort_keys=True,ensure_ascii=False,indent=2)
        stream.write('\n')
    print(json.dumps(dict(capability=quality_passed,optimization=accepted,selected=selected,input_pins=len(pins),
        service_median_reduction=result['median_two_request_service_reduction'],owned_median_reduction=result['median_owned_reduction'])))


if __name__=='__main__':
    main()
