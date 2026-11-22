"""Bind captured requests and original artifacts to the preceding accepted batch."""

from copy import deepcopy
import json
from pathlib import Path
from runpy import run_path


HERE = Path(__file__).resolve().parent
V = HERE.parents[1]
PREVIOUS = V/'m2_source_region_normalization_triangle_list_001'
PREVIOUS_INPUTS = PREVIOUS/'harness/inputs.py'
old = run_path(str(PREVIOUS_INPUTS))
FIXTURES = (*old['FIXTURES'],'paired_image','bad_edge')
BASE = PREVIOUS/'install/PRODUCT_RUN_BINDING.json'
BASE_GIT = '31e9b46a68e5f791df9a75a1bad11caa8a6e8410'
RUN = Path('D:/he_m2_source_region_shared_normalization_001')
OLD_RUN = Path('D:/he_m2_source_region_normalization_triangle_list_001')
OLD_GIT = 'c5f987efafc5af3607497307baf0b6ccd30f23f5'
read, write, pin, digest, require, committed, verify_geometry, archived, indexed_archive = (
    old[key] for key in ('read','write','pin','digest','require','committed','verify_geometry',
                         'archived','indexed_archive')
)
CATALOGUE, PRIOR, SEAL, PRIOR_INPUTS, GLOBAL_INPUTS = (
    old[key] for key in ('CATALOGUE','PRIOR','SEAL','PRIOR_INPUTS','GLOBAL_INPUTS')
)


def prior_replay(fixture, arm_name, call_positions, producers):
    """Verify the previous actual installed arm against the sealed receipt."""
    result_path = PREVIOUS/'RESULT.json'
    require(result_path.read_bytes()==committed(result_path,OLD_GIT),'preceding_report_changed')
    registered = read(result_path)['raw_evidence_local']
    index_path = OLD_RUN/'sealed/RAW_INDEX.json'
    index = read(index_path)
    require(index['archive']==registered['archive'] and index['member_count']==registered['member_count'],
            'preceding_archive_not_bound_to_Git')
    pins = [pin(result_path),pin(index_path)]
    archive_path = OLD_RUN/'sealed'/index['archive']['name']
    with indexed_archive(archive_path,index['archive'],pins) as bundle:
        arm = OLD_RUN/'arms'/arm_name
        member = lambda path:archived(OLD_RUN,path,index['members'],bundle,'runtime/',pins)
        summary = json.loads(member(arm/'SUMMARY.json'))
        close = json.loads(member(arm/'mcp/HELD_CLOSE.json'))
        worker = json.loads(member(arm/'REPLAY_CLOSE.json'))
        require(summary['passed'] and summary['product']['preparation_git']==BASE_GIT
                and close['confirmed'] and close['production_eof_and_exit_verified']
                and close['exit_code']==0 and worker['old_sources_unchanged']
                and worker['actual_Blender_starts']==worker['actual_models']==0,
                'preceding_actual_installed_slot_not_safely_closed')
        for req,number,historical in zip(fixture['calls'],call_positions,producers,strict=True):
            wire = arm/'mcp'/f'rpc_{number+3:02d}'
            request,reply = [json.loads(member(wire/n)) for n in ('TX.bin','RX.bin')]
            require(request==req and reply['result']['isError'] is False,
                    'preceding_replay_request_or_actual_reply_changed')
            capture = json.loads(member(arm/f'CAPTURE_{number:02d}.json'))
            verify_geometry(capture,fixture['terminal'])
            delta = fixture['deltas'][int(number!=1)]
            require(capture['capture_state']==delta['capture']['capture_state']
                    and capture['display_snapshot']==delta['capture']['display_snapshot'],
                    'preceding_replay_capture_identity_changed')
            producer = json.loads(member(arm/'product_full'/f'call_{number:03d}'/'SERVICE_RESULT.json'))
            require(producer['region_ref']==historical['region_ref']
                    and producer['task_result']['facts']==historical['task_result']['facts'],
                    'preceding_replay_selected_measurement_changed')
        for row,original in zip(summary['construct_frames'],fixture['frames'],strict=True):
            require(row['view_name']==original['view_name']
                    and all(digest(member(Path(row[k]['path'])))==original[k] for k in ('png','arrays')),
                    'preceding_replay_original_frame_changed')
    return {**fixture,'source_pins':fixture['source_pins']+pins}


def dual_inputs():
    fixture = old['sealed_inputs']('dual')
    return prior_replay(fixture,'DP',(1,2),fixture['producers'])


def main_inputs():
    fixture = old['sealed_inputs']('main')
    original_lower = json.loads(Path(fixture['original_slot']).joinpath(
        'product_full/call_001/SERVICE_RESULT.json').read_bytes())
    path = Path(fixture['original_slot']).joinpath('product_full/call_001/SERVICE_RESULT.json').resolve()
    receipt, = [row for row in fixture['source_pins'] if Path(row['path'])==path]
    require(pin(path)==receipt,'pinned_original_lower_producer_changed')
    producers = (fixture['producer'],original_lower)
    return {**prior_replay(fixture,'P1',(1,3),producers),'producers':producers}


def paired_image_inputs():
    source = main_inputs()
    upper,lower = source['calls']
    derived = deepcopy(lower)
    derived['id'] = 'upper_camera_independent_lower_image'
    derived['params']['arguments']['include_image'] = True
    # This is a new second image from the already frozen scene, with the same
    # lower source rows, reference and capture state as the original no-image request.
    guide = RUN/'preflight/paired_image/SUMMARY.json'
    if not guide.is_file():
        return {**source,'name':'paired_image','calls':[upper,derived]}
    guide = guide.resolve(strict=True)
    verified = read(guide)
    require(verified['passed'] and verified['preflight'] and verified['fixture']=='paired_image'
            and verified['product']['preparation_git']==BASE_GIT
            and verified['closure']['confirmed'] and verified['closure']['exit_code']==0,
            'derived_lower_image_requires_the_same_closed_baseline_capture')
    pins = [pin(guide)]
    frames = []
    for frame in verified['constructed_frames_by_request'][1]:
        row = {'view_name':frame['view_name']}
        for field in ('png','arrays'):
            item = pin(frame[field]['path'])
            require(item==frame[field] and Path(item['path']).is_relative_to(guide.parent),
                    'derived_lower_baseline_frame_pin_mismatch')
            pins.append(item)
            row[field] = {key:item[key] for key in ('bytes','sha256')}
        frames.append(row)
    require(bool(frames),'baseline_paired_image_did_not_create_lower_frame')
    return {**source,'name':'paired_image','calls':[upper,derived],'lower_image_frames':frames,
            'source_pins':source['source_pins']+pins}


def bad_edge_inputs():
    source = dual_inputs()
    upper,lower = source['calls']
    bad = deepcopy(source['deltas'][0])
    largest = max(bad['resources'],key=lambda obj:len(obj['vertices_local']))
    require(bool(largest['edges']),'expected_existing_edge_to_corrupt')
    largest['edges'][0][1] = len(largest['vertices_local'])
    rejection = {**lower,'id':'same_state_invalid_edge_for_fresh_lower'}
    recovery = {**lower,'id':'same_state_restored_edge_for_fresh_lower'}
    # A complete resend is needed to replace the one edge on the real decoder.
    return {**source,'name':'bad_edge','calls':[upper,rejection,recovery],
            'capture_plan':[(delta,{'command':'capture','params':{}},source['terminal'])
                            for delta in (source['deltas'][0],bad,source['deltas'][0])],
            'bad_mesh_resource':largest['id'],'bad_edge':largest['edges'][0]}


def sealed_inputs(name):
    handlers = {'main':main_inputs,'dual':dual_inputs,'paired_image':paired_image_inputs,'bad_edge':bad_edge_inputs}
    return handlers[name]() if name in handlers else old['sealed_inputs'](name)
