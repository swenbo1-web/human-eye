"""Freeze task-only inputs and the single unsaved state-control sequence."""

import copy
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent


def main():
    main_request=dict(session_id='m4-cross-scale-001',include_image=True,query=dict(mode='active_observation',
        region_task=dict(area_min_m2=1/128,area_max_m2=1/32,normal_z_min=.75)))
    requests={name:copy.deepcopy(main_request) for name in ('main','initial','repeat','full','conditions','moved','restored')}
    requests['full']['response_detail']='full'
    requests['conditions']['query']['region_task']['normal_z_min']=1
    requests['default']=dict(session_id='m4-cross-scale-001',include_image=True,query=dict(mode='active_observation'))
    value=dict(schema='m4-cross-scale-requests-v1',requests=requests,
        state_order=['default','initial','full','repeat','conditions','moved','restored'],
        fixture_change=dict(object_name='Obj_02',world_matrix_translation_m=[.25,0,0],restore='identity',save=False),
        expected_state_rasters_upper=23,expected_state_rasters_nominal=17,
        main_input_has_object_names=False,main_detail='default brief')
    with (HERE/'REQUESTS.json').open('x',encoding='utf8',newline='\n') as stream:
        json.dump(value,stream,sort_keys=True,indent=2)
        stream.write('\n')


if __name__=='__main__':
    main()
