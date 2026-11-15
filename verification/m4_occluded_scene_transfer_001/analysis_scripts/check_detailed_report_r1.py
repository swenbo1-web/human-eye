"""Additional read-only semantic claims in explicitly cited complete JSON reports."""
from fractions import Fraction
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parents[1]
RUNTIME=Path('D:/he_occluded_transfer_001/formal')


def read(path):
    return json.loads(path.read_bytes())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    truth=read(HERE/'admin/TRUTH.json');pixel=read(HERE/'admin/PIXEL_TRUTH.json');cameras=read(HERE/'inputs/CAMERAS.json')
    regions={(r['object_index'],tuple(r['source_triangle_indices'])):r for r in truth['regions']}
    pixelrows={f['view_name']:{r['roi_id']:r for r in f['rows']} for f in pixel['frames']}
    checks=[]
    def check(name,value,slot,identity,view=None):
        checks.append(dict(name=name,passed=bool(value),slot=slot,identity=identity,view=view))
    reports=[('N3','equipment_rack_inspection.json'),('P1','supported_surface_inspection.json'),('P3','equipment_rack_inspection.json')]
    for slot,name in reports:
        report=read(RUNTIME/slot/'o/scratch'/name)
        for item in report['surfaces']+report['pixel_targets']+report['source_targets']:
            local=item.get('local_source_triangle_indices',item.get('source_triangle_indices'))
            region=regions[item['object_index'],tuple(local)]
            label=region['roi_id']
            if 'global_source_triangle_indices' in item:
                check('additional_global_source_identity',item['global_source_triangle_indices']==region['global_source_triangle_indices'],slot,label)
            for view in item.get('finite_pool_view_evidence',[]):
                name=view['view'];geometry=region['views'][name];actual=pixelrows[name][label]
                check('additional_view_front',view['front_facing']==geometry['front_facing'],slot,label,name)
                check('additional_view_frustum',view['fully_in_frame']==geometry['fully_in_view'],slot,label,name)
                check('additional_view_visible_pixels',view['visible_surface_pixels']==actual['surface_pixels'],slot,label,name)
                check('additional_view_boundary_pixels',view['contrasting_boundary_pixels']==actual['boundary_pixels'],slot,label,name)
                check('additional_view_complete_readable',view['complete_readable']==actual['complete_readable'],slot,label,name)
                if 'positive_area_occlusion' in view:
                    check('additional_view_positive_occlusion',view['positive_area_occlusion']==(Fraction(geometry['positive_shadow_area'])>0),slot,label,name)
                if 'occluding_source_faces' in view:
                    claimed={(r['object_index'],r['local_source_triangle_index']) for r in view['occluding_source_faces']}
                    expected={(r['object_index'],r['source_triangle_index']) for r in geometry['shadows']}
                    check('additional_view_occluder_source_set',claimed==expected,slot,label,name)
            for view,reason in item.get('finite_pool_view_reasons',{}).items():
                actual=region['views'][view]
                direction=next(p['direction_rational'] for p in cameras['views'] if p['name']==view)
                dot=sum(Fraction(a)*Fraction(b) for a,b in zip(region['front_direction_world'],direction))
                expected=('edge_on' if dot==0 else 'back_facing') if not actual['front_facing'] else ('positive_area_occlusion' if Fraction(actual['positive_shadow_area'])>0 else 'geometrically_complete')
                check('additional_view_specific_reason',reason==expected,slot,label,view)
    output=HERE/'analysis_scripts/DETAILED_REPORT_CHECKS_R1.json'
    result=dict(schema='occluded-transfer-additional-report-semantic-checks-v1',
        checks=checks,check_count=len(checks),passed_checks=sum(c['passed'] for c in checks),
        passed=all(c['passed'] for c in checks),
        inputs_sha256={str(RUNTIME/slot/'o/scratch'/name):sha(RUNTIME/slot/'o/scratch'/name) for slot,name in reports},
        main_semantic_review_sha256=sha(HERE/'admin/SEMANTIC_REVIEW.json'),
        final_normalized_sha256=sha(HERE/'admin/NORMALIZED.json'),
        actual_model_product_raster_calls=0,performance_usage_or_ranking_consulted=False)
    with output.open('x',encoding='utf-8',newline='\n') as stream:
        json.dump(result,stream,ensure_ascii=False,sort_keys=True,indent=2);stream.write('\n')
    print(json.dumps(dict(checks=len(checks),passed=result['passed_checks'],failed_count=sum(not c['passed'] for c in checks),first_failures=[c for c in checks if not c['passed']][:5],report_sha256=sha(output))))

if __name__=='__main__':
    main()
