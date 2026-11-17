"""Record the successful first real capability before choosing its one optimization."""

import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
SESSION=Path('D:/he_m4_cross_scale_001/sessions/qualification_R0')


def main():
    quality=json.loads((HERE/'checks_saved/qualification_R0.json').read_bytes())
    if quality['passed_checked_scope'] is not True:
        raise ValueError('first_real_quality_required')
    source=SESSION/'product_full/call_001/SERVICE_RESULT.json'
    data=json.loads(source.read_bytes())
    stages=data['stages']
    render=sum(row['elapsed_ns'] for name,row in stages.items() if name.startswith('render_and_publish_global_'))
    feedback=sum(row['elapsed_ns'] for name,row in stages.items() if name.startswith('feedback_global_'))
    value=dict(schema='cross-scale-first-hotspot-v1',quality_passed=True,quality_sha256=hashlib.sha256((HERE/'checks_saved/qualification_R0.json').read_bytes()).hexdigest(),
        original_service_result=str(source),original_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        service_total_ns=stages['service_total']['elapsed_ns'],global_render_publish_ns=render,global_feedback_ns=feedback,
        work=data['work'],task_summary=data['facts']['region_task']['summary'],
        one_optimization='Conservative pixel-center upper bounds skip unconstructed global directions only when all unresolved task regions cannot meet the original 16-pixel threshold.',
        quality_thresholds_unchanged=True,new_actual_calls=0)
    with (HERE/'FIRST_VERSION_HOTSPOT.json').open('x',encoding='utf8',newline='\n') as stream:
        json.dump(value,stream,sort_keys=True,indent=2)
        stream.write('\n')
    print(json.dumps(dict(qualified=True,global_render_publish_ms=render/1e6,global_feedback_ms=feedback/1e6)))


if __name__=='__main__':
    main()
