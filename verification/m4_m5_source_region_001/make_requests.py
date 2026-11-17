"""Freeze the two-request task and the finite owned state controls."""

import copy
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent


def main():
    base=dict(session_id='source-region-001',include_image=True,query=dict(mode='source_region',
        region=dict(object=dict(name='Obj_07'),source_triangle_indices=[0,1,2,3]),
        reference=dict(name='Ref_B'),requested_facts=['surface_proximity']))
    requests={name:copy.deepcopy(base) for name in ('initial','repeat','switch_C','subset','moved_old','moved_current','restored_old','restored_current')}
    requests['repeat']['response_detail']='full'
    requests['switch_C']['query']['reference']['name']='Ref_C'
    requests['subset']['query']['region']['source_triangle_indices']=[0,1,2]
    requests['default']=dict(session_id='source-region-001',include_image=True,query=dict(mode='active_observation'))
    for name,reference in (('whole_B','Ref_B'),('whole_C','Ref_C')):
        requests[name]=dict(session_id='source-region-001',include_image=False,query=dict(mode='task',
            objects=[dict(name='Obj_07'),dict(name=reference)],requested_facts=['surface_proximity']))
    value=dict(schema='source-region-request-sequence-v1',requests=requests,
        main_order=['initial','switch_C'],
        state_order=['default','initial','repeat','switch_C','subset','moved_old','moved_current','restored_old','restored_current','whole_B','whole_C'],
        use_initial_public_region_ref=['repeat','switch_C','moved_old','restored_old'],
        expected_error_stages=['moved_old','restored_old'],
        fixture_change=dict(target='Obj_07',world_translation_m=[.25,0,0],restore='identity',save=False),
        expected_total_rasters_nominal=17,state_raster_nominal=10,max_total_rasters=24,
        external_answers_supplied_to_product=False)
    with (HERE/'REQUESTS.json').open('x',encoding='utf8',newline='\n') as stream:
        json.dump(value,stream,sort_keys=True,indent=2)
        stream.write('\n')


if __name__=='__main__':
    main()
