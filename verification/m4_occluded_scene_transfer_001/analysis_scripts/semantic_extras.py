"""Post-performance semantic second algorithm. No model/product/raster calls."""
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parents[1]
sys.path.insert(0,'D:/he_occluded_transfer_001/shared_dependencies')
sys.path.insert(0,'D:/he_anchor_001/venv/Lib/site-packages')
from shapely.geometry import Polygon
from shapely.ops import unary_union
import shapely


def read(path):
    return json.loads(Path(path).read_bytes())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def strictly_above_zero_part(points):
    if max(p[2] for p in points)<=0:
        return []
    result=[]
    previous=points[-1]
    for current in points:
        if (previous[2]>=0)!=(current[2]>=0):
            ratio=previous[2]/(previous[2]-current[2])
            result.append(tuple(previous[k]+ratio*(current[k]-previous[k]) for k in range(3)))
        if current[2]>=0:
            result.append(current)
        previous=current
    return result


def base_occluded_union(scene,direction):
    base=Polygon([(-7,-6),(7,-6),(7,6),(-7,6)])
    polygons=[]
    for obj in scene['objects']:
        points=[tuple(Fraction(value) for value in point) for point in obj['vertices']]
        for face in obj['triangles']:
            clipped=strictly_above_zero_part([points[i] for i in face])
            if len(clipped)<3:
                continue
            projected=[(float(p[0]-p[2]*direction[0]/direction[2]),float(p[1]-p[2]*direction[1]/direction[2])) for p in clipped]
            polygon=Polygon(projected)
            if polygon.area>0:
                polygons.append(polygon.intersection(base))
    return unary_union(polygons).area


def main():
    truth=read(HERE/'admin/TRUTH.json')
    scene=read(HERE/'inputs/SCENE_GEOMETRY_RATIONAL.json')
    poses=read(HERE/'inputs/CAMERAS.json')['views']
    claims=[59.958,168,114.551,114.551,85.383,71.153]
    areas=[]
    for pose,claim in zip(poses,claims):
        area=base_occluded_union(scene,tuple(Fraction(value) for value in pose['direction_rational']))
        areas.append(dict(view=pose['name'],independent_union_m2=area,N2_approximate_claim_m2=claim,
                          absolute_error=abs(area-claim),within_half_last_decimal=abs(area-claim)<=.000500001))
    by_key={(r['object_index'],tuple(r['source_triangle_indices'])):r for r in truth['regions']}
    exceptions={(3,(6,7)):11,(4,(10,11)):2,(7,(10,11)):2,(8,(10,11)):2}
    blocker_results=[]
    for r in truth['regions']:
        key=(r['object_index'],tuple(r['source_triangle_indices']))
        if not any(v['front_facing'] for v in r['views'].values()) or any(v['complete'] for v in r['views'].values()):
            continue
        for name,view in r['views'].items():
            if not view['front_facing']:
                continue
            expected=exceptions.get(key,1)
            if key==(6,(4,5)) and name=='SCENE':
                expected=8
            blockers={s['object_index'] for s in view['shadows'] if Fraction(s['positive_overlap_parameter_area'])>0}
            blocker_results.append(dict(region_id=r['region_id'],view=name,
                claimed_sufficient_blocker=scene['objects'][expected]['name'],
                actual_blocker_objects=[scene['objects'][i]['name'] for i in sorted(blockers)],passed=expected in blockers))
    target=by_key[(0,(2,3))]
    roof_all=all(any(s['object_index']==1 for s in v['shadows']) for v in target['views'].values())
    turned=by_key[(9,(6,7))]
    normal=tuple(Fraction(x) for x in turned['front_direction_world'])
    candidate=tuple(Fraction(x) for x in poses[0]['direction_rational'])
    dot=sum(a*b for a,b in zip(normal,candidate))
    result=dict(schema='occluded-transfer-semantic-extra-checks-v1',
        shapely_version=shapely.__version__,source_sha256=sha(HERE/'inputs/SCENE_GEOMETRY_RATIONAL.json'),
        truth_sha256=sha(HERE/'admin/TRUTH.json'),
        algorithm='Independent Fraction clipping at base z=0 followed by Shapely projected polygon union intersected with the base XY rectangle. No oracle summed areas are used.',
        N2_base_union_area_claims=areas,N1_sufficient_occluder_claims=blocker_results,
        N1_base_top_roof_occludes_all_six=roof_all,
        N2_turned_right_front_candidates=dict(claimed=['SCENE','RIGHT','BACK'],
            actual=[v for v,d in turned['views'].items() if d['front_facing']],
            normalized_front=list(map(str,normal)),SCENE_dot=str(dot),
            finding='SCENE is back-facing to TurnedUnit [6,7]. N2 includes it among front candidates.',
            claim_is_correct=dot>0),
        N2_L_corners_interpretation='The final calls these boundary corners and gives a +Z front. It does not explicitly claim the listed order supplies the normal. Reversed boundary order alone is not a substantiated geometry error.',
        actual_model_product_raster_calls=0,performance_values_read=False)
    output=HERE/'analysis_scripts/SEMANTIC_EXTRA_CHECKS.json'
    with output.open('x',encoding='utf-8',newline='\n') as stream:
        json.dump(result,stream,ensure_ascii=False,sort_keys=True,indent=2)
        stream.write('\n')
    print(json.dumps(dict(areas=areas,N1_sufficient_occluders_all_correct=all(r['passed'] for r in blocker_results),
        blocker_claim_checks=len(blocker_results),N1_base_top_roof_all_six=roof_all,
        N2_actual_turned_right_candidates=result['N2_turned_right_front_candidates']['actual'],
        source='analysis_scripts/SEMANTIC_EXTRA_CHECKS.json')))

if __name__=='__main__':
    main()
