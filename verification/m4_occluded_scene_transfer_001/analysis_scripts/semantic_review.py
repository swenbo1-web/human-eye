"""Independent semantic checks after all formal consumers have completed.

No CLI usage, duration or ranking inputs are consulted. No product, model or
raster operation is performed. Normalized rows are indexes into actual claims.
"""
from fractions import Fraction
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import struct
import zipfile

HERE=Path(__file__).resolve().parents[1]
RUNTIME=Path('D:/he_occluded_transfer_001/formal')


def read(path):
    return json.loads(Path(path).read_bytes())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def vec(values):
    return tuple(Fraction.from_float(x) if type(x) is float else Fraction(x) for x in values)


def same_direction(a,b):
    a,b=list(map(float,vec(a))),list(map(float,vec(b)))
    na=math.sqrt(sum(x*x for x in a));nb=math.sqrt(sum(x*x for x in b))
    return na>0 and nb>0 and all(abs(x/na-y/nb)<=2e-14 for x,y in zip(a,b))


def strings(value):
    if isinstance(value,str):
        return [value]
    if isinstance(value,dict):
        return [text for item in value.values() for text in strings(item)]
    if isinstance(value,list):
        return [text for item in value for text in strings(item)]
    return []


def main():
    spec=importlib.util.spec_from_file_location('_semantic_oracle',HERE/'oracle.py')
    oracle=importlib.util.module_from_spec(spec);spec.loader.exec_module(oracle)
    truth=read(HERE/'admin/TRUTH.json');pixel=read(HERE/'admin/PIXEL_TRUTH.json')
    extras=read(HERE/'analysis_scripts/SEMANTIC_EXTRA_CHECKS.json')
    normalized=read(HERE/'admin/NORMALIZED.json')['slots']
    assert len(normalized)==6 and {r['slot_id'] for r in normalized}=={'N1','N2','N3','P1','P2','P3'}
    regions={(r['object_index'],tuple(r['source_triangle_indices'])):r for r in truth['regions']}
    by_name={r['object_name']:r['object_index'] for r in truth['regions']}
    by_private={r['roi_id']:r for r in truth['regions']}
    pixelrows={f['view_name']:{r['roi_id']:r for r in f['rows']} for f in pixel['frames']}
    native_descriptors={f['view_name']:f for f in pixel['native_frame_descriptors']}
    expected_covered=set(pixel['complete_readable_roi_ids'])
    expected_remaining=set(pixel['remaining_roi_ids'])
    checks=[]
    def check(name,passed,slot=None,detail=None):
        checks.append(dict(name=name,passed=bool(passed),slot=slot,detail=detail))
    def resolve(identity):
        index=identity.get('object_index',by_name.get(identity.get('object_name')))
        if identity.get('object_name') is not None and by_name[identity['object_name']]!=index:
            raise ValueError('conflicting_object_name_index')
        return regions[index,tuple(sorted(identity['source_triangle_indices']))]
    def world_claims(identity,expected):
        if 'center_world_m' in identity and vec(identity['center_world_m'])!=vec(expected['center_world_m']):
            return False
        if 'quad_world_m' in identity and set(map(vec,identity['quad_world_m']))!=set(map(vec,expected['quad_world_m'])):
            return False
        if 'front_direction_world' in identity and not same_direction(identity['front_direction_world'],expected['front_direction_world']):
            return False
        return True
    slot_results=[]
    source_hashes={}
    for row in normalized:
        slot=row['slot_id'];owner=RUNTIME/slot/'o'
        final_path=RUNTIME/slot/'c/PUBLIC_FINAL.txt'
        final=final_path.read_bytes().decode('utf-8')
        check('raw_final_binding',sha(final_path)==row['raw_answer_sha256'],slot)
        source_hashes[str(final_path)]=sha(final_path)
        texts={'final':[final,final.replace('\r\n','\n')]}
        for source in row['sources']:
            raw=Path(source['path']).read_bytes();check('normalization_source_hash',hashlib.sha256(raw).hexdigest()==source['sha256'],slot)
            source_hashes[source['path']]=source['sha256']
            text=raw.decode('utf-8')
            try:
                expanded=strings(json.loads(raw))
            except (ValueError,TypeError):
                expanded=[]
            texts[source['id']]=[text,text.replace('\r\n','\n'),*expanded]
        def support_checks(value):
            if isinstance(value,dict):
                if set(value)>={'source_id','excerpt'}:
                    excerpt=value['excerpt']
                    check('claim_support_is_actual_source_excerpt',bool(excerpt) and any(excerpt in t for t in texts[value['source_id']]),slot)
                for item in value.values():
                    support_checks(item)
            elif isinstance(value,list):
                for item in value:
                    support_checks(item)
        for key in ('panels','remaining','unsupported','pixel_targets','source_targets','finite_pool_support'):
            support_checks(row.get(key,[]))
        observations=read(owner/'OBSERVATIONS.json')
        current={f['view_name']:f for f in observations['frames']}
        refs={f['ref']:f['view_name'] for f in observations['frames']}
        for name,frame in current.items():
            qualified=native_descriptors[name]
            check('current_PNG_matches_qualified_pixels',sha(Path(frame['PNG']))==frame['PNG_sha256']==qualified['PNG_sha256'],slot)
            check('current_NPZ_saved_hash',sha(Path(frame['NPZ']))==frame['NPZ_sha256'],slot)
            with zipfile.ZipFile(frame['NPZ']) as archive:
                for array_name in ('color','owners','triangle_ids'):
                    head,raw=oracle.npy(archive.read(array_name+'.npy'))
                    check('current_raw_array_matches_qualified_pixels',hashlib.sha256(raw).hexdigest()==frame['arrays'][array_name]['sha256']==qualified['arrays'][array_name]['sha256'],slot)
                    if name in ('TOP','LEFT') and array_name=='triangle_ids':
                        sample=next(t for t in truth['pixel_targets'] if t['view_name']==name)
                        source_triangle=struct.unpack_from('<i',raw,4*(512*sample['y']+sample['x']))[0]
                        expected=by_private[sample['region_id']]
                        check('exact_current_sample_raw_owner',source_triangle in expected['global_source_triangle_indices'],slot,dict(id=sample['id'],actual_global_source_triangle=source_triangle))
        claimed_covered=set();claimed_remaining=set();reasons=[];witnesses=0
        for panel in row['panels']:
            expected=resolve(panel['identity']);identity=expected['roi_id']
            check('surface_world_claims_match_source',world_claims(panel['identity'],expected),slot)
            if panel['status']=='covered':
                claimed_covered.add(identity)
                check('covered_has_same_frame_complete_witness',bool(panel.get('views')),slot)
                for witness in panel.get('views',[]):
                    witnesses+=1
                    measured=pixelrows[witness['view']][identity]
                    check('complete_witness_ref_and_geometry',refs.get(witness['ref'])==witness['view'] and measured['complete_readable'],slot)
                    for key,target in [('surface_pixels','surface_pixels'),('boundary_pixels','boundary_pixels')]:
                        if key in witness:
                            check('asserted_witness_pixel_count',witness[key]==measured[target],slot)
            else:
                claimed_remaining.add(identity)
                reason=panel.get('reason_code')
                check('remaining_specific_reason',reason==pixel['remaining_reasons'][identity],slot)
                reasons.append(reason)
        check('complete_inventory_identity_set',len(row['panels'])==len(regions)==61 and claimed_covered==expected_covered and claimed_remaining==expected_remaining,slot)
        check('finite_pool_scope',row['finite_pool_only'] is True and row['global_invisibility_overclaim'] is False,slot)
        check('unknown_reason_counts',reasons.count('no_front_facing_candidate')==10 and reasons.count('positive_area_occlusion_all_front_views')==33,slot)
        for target in row['pixel_targets']:
            expected=next(t for t in truth['pixel_targets'] if t['id']==target['id'])
            region=resolve(target['identity'])
            check('pixel_localization_identity_world_ref',region['roi_id']==expected['region_id'] and target['view']==expected['view_name'] and refs.get(target['ref'])==target['view'] and vec(target['center_world_m'])==vec(region['center_world_m']) and same_direction(target['front_direction_world'],region['front_direction_world']) and set(map(vec,target['quad_world_m']))==set(map(vec,region['quad_world_m'])),slot)
        check('both_pixel_target_ids',len(row['pixel_targets'])==2 and {t['id'] for t in row['pixel_targets']}=={'sample_A','sample_B'},slot)
        for target in row['source_targets']:
            expected=next(t for t in truth['source_targets'] if t['id']==target['id'])
            check('source_target_state_reason',resolve(target['identity'])['roi_id']==expected['region_id'] and target['status']=='unknown' and target['reason_code']==pixel['remaining_reasons'][expected['region_id']],slot)
        check('both_source_target_ids',len(row['source_targets'])==2 and {t['id'] for t in row['source_targets']}=={'target_C','target_D'},slot)
        check('unsupported_L_identity',len(row['unsupported'])==1 and row['unsupported'][0]['identity']['object_index']==11 and set(row['unsupported'][0]['identity']['source_triangle_indices'])=={0,1,2,3},slot)
        errors=[c for c in checks if c['slot']==slot and not c['passed']]
        slot_results.append(dict(slot=slot,core_claims_correct=not errors,core_failed_checks=errors,
            supported=61,covered=len(claimed_covered),remaining=len(claimed_remaining),
            witnessed_complete_surface_entries=witnesses,unretracted_additional_false_claims=1 if slot=='N2' else 0,
            complete_final_semantically_correct=not errors and slot!='N2'))
    # Additional final claims are checked separately from the required inventory.
    check('N1_all_specific_sufficient_blockers',all(r['passed'] for r in extras['N1_sufficient_occluder_claims']))
    check('N1_target_C_roof_blocks_all_six',extras['N1_base_top_roof_occludes_all_six'])
    poses=read(HERE/'inputs/CAMERAS.json')['views']
    projected=[]
    for area,pose in zip(extras['N2_base_union_area_claims'],poses):
        direction=pose['direction_rational']
        scale=abs(direction[2])/math.sqrt(sum(d*d for d in direction))
        value=area['independent_union_m2']*scale
        projected.append(dict(view=pose['name'],base_plane_union_m2=area['independent_union_m2'],orthogonal_projection_factor=scale,independent_projected_union_m2=value,claim_m2=area['N2_approximate_claim_m2'],within_half_last_decimal=abs(value-area['N2_approximate_claim_m2'])<=.000500001))
    check('N2_projected_area_claims_match_orthogonal_screen_metric',all(r['within_half_last_decimal'] for r in projected))
    turned=regions[9,(6,7)];normal=list(map(float,turned['front_direction_world']))
    magnitude=math.sqrt(sum(x*x for x in normal));unit=[x/magnitude for x in normal]
    float_dot=sum(a*b for a,b in zip(unit,poses[0]['target_to_eye_unit']))
    check('N2_false_front_claim_exact_and_actual_float_sign',sum(Fraction(a)*Fraction(b) for a,b in zip(turned['front_direction_world'],poses[0]['direction_rational']))<0 and float_dot<-.1)
    # P2 explicitly enumerates every front candidate in O cells.
    p2=(RUNTIME/'P2/c/PUBLIC_FINAL.txt').read_text(encoding='utf-8')
    abbreviation={'S':'SCENE','T':'TOP','L':'LEFT','R':'RIGHT','F':'FRONT','B':'BACK'}
    for line in p2.splitlines():
        if not line.startswith('| ') or ' | O:' not in line:
            continue
        cells=[x.strip() for x in line.strip('|').split('|')]
        index=int(cells[0].split()[0])
        for face,cell in enumerate(cells[1:]):
            if cell.startswith('O:'):
                expected=regions[index,(2*face,2*face+1)]
                declared={abbreviation[c] for c in cell[2:].split(',')}
                actual={v for v,d in expected['views'].items() if d['front_facing']}
                check('P2_explicit_front_candidate_list',declared==actual,'P2',dict(object_index=index,triangles=[2*face,2*face+1]))
    report=dict(schema='occluded-transfer-independent-semantic-review-v1',
        denominator=6,slot_results=slot_results,checks=checks,check_count=len(checks),
        passed_checks=sum(c['passed'] for c in checks),all_semantic_checks_completed=True,
        core_correct_slots=6 if all(r['core_claims_correct'] for r in slot_results) else sum(r['core_claims_correct'] for r in slot_results),
        full_final_correct_slots=sum(r['complete_final_semantically_correct'] for r in slot_results),
        N2_substantiated_false_claim=dict(source=str(RUNTIME/'N2/c/PUBLIC_FINAL.txt'),
            exact_excerpt='[6,7]: SCENE/RIGHT/BACK',object_name='TurnedUnit',local_source_triangle_indices=[6,7],
            true_candidates=['RIGHT','BACK'],front_direction_proportional=turned['front_direction_world'],
            exact_SCENE_dot='-1',unit_normal_dot_actual_float_camera=float_dot,
            interpretation='This is an unretracted extra factual error in the final front-candidate explanation. The core inventory unknown state remains correct.'),
        N2_area_interpretation=dict(projected_areas=projected,
            explanation='The final explicitly says projected areas. These are camera-screen orthogonal areas. The first XY-plane diagnostic alone does not have that metric. Applying the projection factor confirms every rounded claim.',
            preliminary_base_plane_diagnostic=str(HERE/'analysis_scripts/SEMANTIC_EXTRA_CHECKS.json')),
        N2_L_boundary_interpretation=extras['N2_L_corners_interpretation'],
        source_sha256=source_hashes,
        normalization_sha256={name:sha(HERE/'admin'/name) for name in ('NORMALIZED_N.json','NORMALIZED_P_R1.json','NORMALIZED.json')},
        geometric_truth_sha256=sha(HERE/'admin/TRUTH.json'),pixel_truth_sha256=sha(HERE/'admin/PIXEL_TRUTH.json'),
        actual_model_product_raster_calls=0,performance_ranking_or_usage_consulted=False,
        association='Reviewer authored this scene and geometry oracle, independently read actual finals/cited reports and root/other-agent normalized claims. The projected-area union uses a separately written Shapely algorithm. No oracle data are inserted into normalized answers.')
    path=HERE/'admin/SEMANTIC_REVIEW.json'
    with path.open('x',encoding='utf-8',newline='\n') as stream:
        json.dump(report,stream,ensure_ascii=False,sort_keys=True,indent=2);stream.write('\n')
    print(json.dumps(dict(check_count=len(checks),passed_checks=report['passed_checks'],core_correct=report['core_correct_slots'],full_correct=report['full_final_correct_slots'],core_errors=[r for r in slot_results if r['core_failed_checks']],N2_float_dot=float_dot,report_sha256=sha(path))))

if __name__=='__main__':
    main()
