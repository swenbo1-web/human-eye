"""Compare quality across three fixed first-version/optimized saved pairs."""

import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'oracle'))
import check_saved as shared


def evaluate(runtime):
    audit = shared.Audit()
    pairs = []
    array_names = ('color','depth','owners','triangle_ids','patch_owners','face_patch_offsets','face_patch_ids','patch_roi_ids')
    world_fields = ('roi_id','object_index','object_name','status','reason','center_world_m','half_edge_u_world_m',
                    'half_edge_v_world_m','front_direction_world','source_triangle_indices','view_reasons')
    for index in (1,2,3):
        labels = ['pair'+str(index)+'_'+version for version in ('R0','R1')]
        reports = [audit.read(HERE/(label+'_QUALITY.json')) for label in labels]
        audit.check(all(report['passed_checked_scope'] is True for report in reports), 'pair_both_independent_quality_passed')
        originals = [audit.read(runtime/'sessions'/label/'product_full/call_001/SERVICE_RESULT.json') for label in labels]
        captures = [report['current_capture'] for report in reports]
        source_geometry = [[dict(name=mesh['name'],vertices=mesh['vertices'],faces=mesh['faces']) for mesh in capture['meshes']]
                           for capture in captures]
        audit.check(source_geometry[0]==source_geometry[1], 'pair_same_ordered_full_source_geometry')
        tasks = [value['facts']['region_task'] for value in originals]
        audit.check(tasks[0]['conditions']==tasks[1]['conditions'], 'pair_same_public_task_conditions')
        regions = [{row['object_name']:row for row in task['rows']} for task in tasks]
        audit.check(set(regions[0])==set(regions[1])=={'Obj_02','Obj_06','Obj_09'}, 'pair_same_three_independent_regions')
        for name in regions[0]:
            audit.check(all(regions[0][name][field]==regions[1][name][field] for field in world_fields), 'pair_task_geometry_and_outcome/' + name)
        scope_maps = [{scope['scope_id']:scope for scope in value['scopes']} for value in originals]
        comparisons = []
        for name in ('overview','Obj_02','Obj_09'):
            frames = []
            for position in (0,1):
                if name=='overview':
                    frame = originals[position]['frames'][0]
                else:
                    witness = regions[position][name]['complete_witness']
                    frame = next(frame for frame in originals[position]['constructed_frames'] if frame['frame_identity']==witness['frame_identity'])
                frames.append(frame)
            audit.check(frames[0]['pose']==frames[1]['pose'] and frames[0]['view_name']==frames[1]['view_name']=='SCENE', 'pair_same_actual_camera/' + name)
            audit.check(frames[0]['image_sha256']==frames[1]['image_sha256'], 'pair_same_encoded_RGB/' + name)
            for frame in frames:
                audit.file(frame['image_path'],frame['image_sha256'])
                audit.file(frame['arrays_path'],frame['arrays_sha256'])
            with shared.np.load(frames[0]['arrays_path'],allow_pickle=False) as first, shared.np.load(frames[1]['arrays_path'],allow_pickle=False) as second:
                for field in array_names:
                    audit.check(shared.np.array_equal(first[field],second[field]), 'pair_exact_array/' + name + '/' + field)
            comparisons.append(dict(role=name,PNG_sha256=frames[0]['image_sha256'],
                                    array_byte_identity={field:True for field in array_names}))
        audit.check(len(originals[0]['constructed_frames'])==8 and len(originals[1]['constructed_frames'])==3
                    and len(originals[0]['frames'])==len(originals[1]['frames'])==3,
                    'construction_reduction_preserves_three_selected_images')
        pairs.append(dict(pair=index,labels=labels,passed_checked_scope=True,selected_images=comparisons,
                          first_constructed=8,optimized_constructed=3))
    return dict(schema='cross-scale-independent-paired-quality-v1',passed_checked_scope=True,pair_denominator=3,
                pairs=pairs,check_count=len(audit.checks),checks=audit.checks,input_pins=list(audit.pins.values())+[shared.expected.EXACT.pin(__file__)],
                performance_ranking_performed=False,new_operations=dict(Blender=0,MCP=0,raster=0,model=0))


if __name__=='__main__':
    runtime = Path(sys.argv[1]) if len(sys.argv)>1 else Path('D:/he_m4_cross_scale_001')
    report = evaluate(runtime)
    with (HERE/'PAIRED_QUALITY.json').open('x',encoding='utf8',newline='\n') as stream:
        json.dump(report,stream,sort_keys=True,indent=2)
        stream.write('\n')
    print(json.dumps(dict(passed=True,pairs=3,checks=report['check_count'])))
