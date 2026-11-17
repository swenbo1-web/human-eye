"""Freeze the corrected local-view baseline before its single optimization trial."""

import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
SESSION=Path('D:/he_m4_m5_source_region_001/sessions/pair1_R0')


def pin(path):
    raw=path.read_bytes()
    return dict(path=str(path),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())


def main():
    quality=HERE/'checks_saved/pair1_R0.json'
    if json.loads(quality.read_bytes())['passed'] is not True:
        raise ValueError('corrected_local_quality_required')
    paths=[SESSION/'product_full'/('call_'+str(i).zfill(3))/'SERVICE_RESULT.json' for i in (1,2)]
    rows=[json.loads(path.read_bytes()) for path in paths]
    first,second=rows
    value=dict(schema='source-region-corrected-hotspot-v1',quality=pin(quality),originals=[pin(path) for path in paths],
        first_service_ns=first['stages']['service_total']['elapsed_ns'],second_service_ns=second['stages']['service_total']['elapsed_ns'],
        actual_region_span_m=first['frames'][0]['pose']['view_span_m'],selected_pixels=first['facts']['visibility']['selected_surface_pixels'],
        first_frame_stages=first['frames'][0]['stages'],first_validation_ns=first['stages']['frame_validation_and_selected_pixels']['elapsed_ns'],
        second_preparation_cache_hit=second['work']['prepare_cache_hit'],second_frame_reuses=second['work']['frame_reuses'],
        no_repeated_region_preparation_or_frame_to_remove=True,
        one_candidate='Reuse integrity-checked producer-owned in-memory arrays during fresh-frame validation to remove the redundant NPZ decode. Retain current PNG/NPZ bytes, hash, binding and mutable-buffer validation.',
        source_correctness_fix='R0 full-scene camera is retained as a failed local-view qualification. R0F is the corrected same-quality timing baseline.',
        actual_operations_added=0)
    with (HERE/'FIRST_CORRECTED_HOTSPOT.json').open('x',encoding='utf8',newline='\n') as stream:
        json.dump(value,stream,sort_keys=True,indent=2)
        stream.write('\n')
    print(json.dumps(dict(qualified=True,selected_pixels=value['selected_pixels'],validation_ms=value['first_validation_ns']/1e6)))


if __name__=='__main__':
    main()
