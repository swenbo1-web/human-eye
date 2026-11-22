"""Verify the closed baseline ingress and freeze the newly derived image evidence."""

from pathlib import Path
from runpy import run_path
import sys


HERE = Path(__file__).resolve().parent
R = run_path(str(HERE/'replay.py'))
RUN, pin, read, require, write = (R[key] for key in ('RUN','pin','read','require','write'))


def collect():
    root = RUN/'preflight'
    expected = {'dual':(2,0,0),'paired_image':(2,2,0),'bad_edge':(3,0,1),
                'main':(3,1,0),'holdout':(2,1,0),'rectangle':(2,2,0),'stale':(3,0,1),'defaults':(3,10,0)}
    pins = {}

    def admit(row):
        current = pin(row['path'])
        path = current['path']
        require(current['sha256']==row['sha256'] and current['bytes']==row.get('bytes',current['bytes'])
                and pins.get(path,current)==current,'preflight_source_pin_changed/'+path)
        pins[path] = current
        return current

    arms={}
    for label,(calls,rasters,errors) in expected.items():
        slot = root/label
        summary_path = slot/'SUMMARY.json'
        summary = read(summary_path)
        worker = slot/'REPLAY_CLOSE.json'
        close = summary['closure']
        require(summary['arm']==label and summary['preflight'] and summary['passed']
                and summary['product']['preparation_git']==R['BASE_GIT']
                and len(summary['requests'])==calls
                and sum(row['raster_attempts'] for row in summary['requests'])==rasters
                and sum(row['is_error'] for row in summary['requests'])==errors
                and close['confirmed'] and close['exit_code']==0 and close['production_eof_and_exit_verified']
                and close['process_handle_closed'] and read(worker)['old_sources_unchanged']
                and summary['actual_Blender_starts']==summary['actual_models']==0,
                'baseline_actual_preflight_not_safely_closed/'+label)
        for row in [*summary['source_pins'],summary['held_close'],close['worker_eof'],close['worker_exit']]:
            admit(row)
        for path in (summary_path,worker,slot/'mcp_io/MCP_IO.jsonl'):
            admit(pin(path))
        arms[label]={'summary':pin(summary_path),'work':list(expected[label]),
                     'capture_resource_counts':summary['resource_count']}
    fixture=R['sealed_inputs']('paired_image')
    for row in fixture['source_pins']:
        admit(row)
    for path in (Path(__file__),HERE/'inputs.py',HERE/'replay.py',HERE/'defaults.py'):
        admit(pin(path))

    binding=read(R['V']/'m2_source_region_normalization_triangle_list_001/install/PRODUCT_RUN_BINDING.json')
    installed=Path(binding['install_root']).resolve(strict=True)
    sys.path[:0]=[str(installed),binding['dependency_root']]
    from human_eye_plugin.active_observation_host import source_binding
    from human_eye_plugin.source_region import ordered_geometry_identity
    from human_eye_plugin.scene_cache import _validate_scene
    captured=[]
    for i in range(1,4):
        path=root/'bad_edge'/f'CAPTURE_{i:02d}.json'
        admit(pin(path))
        data=read(path)
        source=source_binding(data)
        captured.append((source['source_binding_sha256'],ordered_geometry_identity(data,source)))
        try:
            _validate_scene(data)
        except ValueError as error:
            require(i==2 and str(error)=='invalid topology indices','wrong_frozen_bad_edge_validation_reason')
        else:
            require(i!=2,'injected_edge_never_reached_complete_scene_validation')
    require(len(set(captured))==1,'bad_edge_probe_did_not_hold_binding_and_ordered_identity')
    return {'passed':True,'formal_slots_used':0,'actual_blender_starts':0,'models':0,
            'arms':arms,'cold_slots':len(arms),'business_calls':sum(w[0] for w in expected.values()),
            'raster_calls':sum(w[1] for w in expected.values()),'expected_errors':sum(w[2] for w in expected.values()),
            'lower_image_derived_on_frozen_capture_not_historical':fixture['lower_image_frames'],
            'same_binding_and_ordered_identity_bad_edge_qualified':captured[0],
            'source_pins':[pins[key] for key in sorted(pins)]}


if __name__=='__main__':
    if not sys.flags.isolated or not sys.dont_write_bytecode:
        raise ValueError('fixed_isolated_interpreter_required')
    report=collect()
    write(RUN/'preflight/RUNTIME_PREFLIGHT.json',report)
    print('Passed baseline preflight',report['cold_slots'],'closed slots',
          report['business_calls'],'actual calls',report['raster_calls'],'rasters')
