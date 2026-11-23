"""Exercise actual installed private cache invalidation on sealed static inputs."""

import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys
from time import perf_counter_ns
from types import SimpleNamespace


HERE = Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from replay_host import (BASE, BINDINGS, CONTROL, RUN, RecordedMeshes, check_installed,
                         fixture, pin, require, save)


def request(bench,query,*,limit=64*1024*1024,seconds=30):
    box = query['region']['world_box_m']
    start = len(bench.wire)
    result = bench.connector.capture_source_region_pair(query['region']['object'],query['reference'],
        box,perf_counter_ns()+int(seconds*1e9),limit)
    require(len(bench.wire)==start+1,'one_current_private_transport_required')
    return result,bench.wire[-1]['response'],bench.scope['_request']['params']


def rejection(action,expected):
    try:
        action()
    except (ValueError,RuntimeError) as error:
        require(expected in str(error),'unexpected_invalid_lease_exit/'+str(error))
        return str(error)
    raise ValueError('invalid_lease_was_accepted/'+expected)


def full(three,*,reused_resource=None):
    local,envelope,params = three
    require(envelope['capture'] is not None and local['work']['connector_reused_payload'] is False,
            'known_cold_or_invalidated_response_not_full')
    if reused_resource is not None:
        require((envelope['work']['to_mesh']==0) is reused_resource,'wrong_current_resource_reuse_expected')
    return local,envelope,params


def event_rows(three):
    local,envelope,params = three
    keys = ('mode','fallback_reason','to_mesh','triangulations','world_transforms',
            'box_triangles_scanned','transmitted_vertices','transmitted_triangles',
            'retained_resources','retained_vertices','retained_triangles')
    return {'known':params.get('known'),'lease':envelope['lease'],
            'capture_present':envelope['capture'] is not None,
            'payload_sha256':local['payload_sha256'],
            'work':{name:envelope['work'][name] for name in keys},
            'connector_retained_bytes':local['work']['connector_retained_bytes'],
            'connector_cache_limit_bytes':local['work']['connector_cache_limit_bytes']}


def controls(bench,queries):
    result = {}
    first,second = queries
    cold = full(request(bench,first),reused_resource=False)
    ack = request(bench,first)
    require(ack[1]['capture'] is None and ack[2]['known']==ack[1]['lease']==cold[1]['lease']
            and ack[0]['payload_sha256']==cold[0]['payload_sha256']
            and ack[0]['work']['connector_reused_payload'] is True
            and not any(ack[1]['work'][key] for key in
                        ('to_mesh','triangulations','box_triangles_scanned','transmitted_triangles')),
            'exact_hot_lease_did_not_settle_without_geometry')
    result['control_cold_and_confirmed_hot'] = [event_rows(value) for value in (cold,ack)]

    bench.connector._selective_capture = None
    unheld = full(request(bench,first),reused_resource=True)
    require('known' not in unheld[2],'lost_connector_payload_still_offered')
    result['lost_connector_payload'] = event_rows(unheld)

    key,lease,contents = bench.connector._selective_capture
    stale = {**lease,'payload_sha256':'0'*64}
    bench.connector._selective_capture = key,stale,contents
    stale_recover = full(request(bench,first),reused_resource=True)
    require(stale_recover[2]['known']==stale and stale_recover[1]['lease']['payload_sha256']!='0'*64,
            'different_lease_digest_accepted')
    result['wrong_known_digest'] = event_rows(stale_recover)

    changed_box = deepcopy(first)
    require(changed_box['region']['world_box_m']['min'][2]==0,'signed_zero_world_box_fixture_changed')
    changed_box['region']['world_box_m']['min'][2] = -0.
    signed = full(request(bench,changed_box),reused_resource=True)
    require('known' not in signed[2] and signed[0]['region']==cold[0]['region']
            and signed[0]['payload_sha256']!=cold[0]['payload_sha256'],
            'signed_zero_request_merged_or_geometry_changed')
    result['signed_zero_box_not_same_lease'] = event_rows(signed)

    swapped = full(request(bench,second),reused_resource=True)
    once_back = full(request(bench,changed_box),reused_resource=True)
    require('known' not in swapped[2] and 'known' not in once_back[2],
            'connector_retained_more_than_one_offer')
    result['single_entry_lease_replaced_and_whole_resources_reused'] = [event_rows(v) for v in (swapped,once_back)]

    target = next(obj for obj in bench.objects if obj.name==first['region']['object']['name'])
    reference = next(obj for obj in bench.objects if obj.name==first['reference']['name'])
    require(reference._fixture_visible is False,'hidden_reference_fixture_changed')
    reference._fixture_visible = True
    displayed = full(request(bench,changed_box),reused_resource=True)
    require(displayed[2]['known']==once_back[1]['lease']
            and displayed[1]['lease']['selection_sha256']!=once_back[1]['lease']['selection_sha256']
            and displayed[0]['region']==once_back[0]['region'],
            'changed_reference_display_confirmed_stale_offer')
    result['display_flag_revision_revalidated'] = event_rows(displayed)

    target.matrix_world[0][3] += 1e-6
    moved = full(request(bench,changed_box))
    require(moved[0]['binding']['world_matrices']['target']==target.matrix_world
            and moved[0]['payload_sha256']!=displayed[0]['payload_sha256'],
            'changed_world_pose_confirmed_stale_offer')
    result['changed_evaluated_world_pose'] = event_rows(moved)

    # Test the real registered invalidators, leaving source geometry arrays
    # unchanged so that lease identity, not numeric result changes, is proven.
    handlers = bench.scope['bpy'].app.handlers
    graph = SimpleNamespace(updates=(SimpleNamespace(id=target.data,is_updated_geometry=True),))
    before = full(request(bench,changed_box))
    for callback in handlers.depsgraph_update_post:
        callback(bench.scene,graph)
    invalidated = full(request(bench,changed_box),reused_resource=False)
    require(invalidated[2]['known']==before[1]['lease'],'derived_geometry_event_not_sent_with_old_offer')
    result['depgraph_update_invalidated'] = event_rows(invalidated)

    before_reset = full(request(bench,changed_box))
    bench.scope['bpy'].app.driver_namespace.clear()
    for callback in handlers.load_post:
        callback(None)
    reloaded = full(request(bench,changed_box),reused_resource=False)
    fresh = reloaded if reloaded[1]['lease'] is not None else full(request(bench,changed_box))
    require(reloaded[2]['known']==before_reset[1]['lease'] and fresh[1]['lease'] is not None
            and fresh[1]['lease']['epoch']>before_reset[1]['lease']['epoch']
            and fresh[1]['lease']['document_epoch']!=before_reset[1]['lease']['document_epoch'],
            'loaded_document_or_resource_generation_accepted_old_offer')
    result['document_reload_invalidated'] = [event_rows(v) for v in (reloaded,fresh)]

    # A connecting client remains truthful about a cached compact response,
    # but the host loses one of the whole resources that justified its lease.
    state = bench.host._residency
    key = bench.host._residency_module.identity(target)
    require(state.resources.pop(key) is not None,'expected_live_whole_resource_to_drop')
    lost = full(request(bench,changed_box),reused_resource=False)
    require(lost[1]['work']['fallback_reason']=='retained_resource_unavailable' and lost[1]['lease'] is None,
            'missing_truth_resource_kept_old_generation_authority')
    result['whole_resource_loss_uncached_path'] = event_rows(lost)

    require(len(handlers.undo_post)==1,'host_invalidation_hook_count_changed')
    hooks = tuple(handlers.undo_post)
    handlers.undo_post.clear()
    no_invalidator = full(request(bench,first),reused_resource=False)
    require(no_invalidator[1]['work']['fallback_reason']=='residency_invalidation_unavailable'
            and no_invalidator[1]['lease'] is None,'unmanaged_device_emitted_a_lease')
    handlers.undo_post.extend(hooks)
    result['missing_invalidation_hook_uncached_path'] = event_rows(no_invalidator)

    absent = deepcopy(first)
    absent['region']['world_box_m'] = {'min':[100.,100.,100.],'max':[101.,101.,101.]}
    result['empty_box'] = rejection(lambda:request(bench,absent),'source_region_pair_empty_world_box')
    result['expired_before_dispatch'] = rejection(lambda:request(bench,first,seconds=-1),'selective_source_region_deadline')
    return result


def corrupt_controls(root,original,first):
    results = {}
    variants = (
        ('reply_with_wrong_lease_digest',
         lambda reply: reply['lease'].__setitem__('payload_sha256','0'*64),
         'selective_source_region_ack_without_exact_capture',False),
        ('fake_ack_after_lost_payload',
         lambda reply: reply.update(capture=None,work={**reply['work'],'mode':'lease_hit'}),
         'selective_source_region_ack_without_exact_capture',True),
        ('ack_missing_host_binding',lambda reply: reply.pop('host_source_sha256'),
         'selective_source_region_residency_envelope',False),
    )
    for label,mutate,reason,drop in variants:
        bench = RecordedMeshes(root,original)
        try:
            full(request(bench,first),reused_resource=False)
            if drop:
                bench.connector._selective_capture = None
            bench.mutate_response = mutate
            results[label] = rejection(lambda:request(bench,first),reason)
            require(not bench.connector.is_alive,'incompatible_ack_did_not_invalidate_connector')
        finally:
            bench.close()

    bench = RecordedMeshes(root,original)
    try:
        full(request(bench,first),reused_resource=False)
        key,lease,stored = bench.connector._selective_capture
        value = json.loads(stored)
        value['region']['source_triangle_vertices'][0][0] = 999_999
        bench.connector._selective_capture = key,lease,json.dumps(value,separators=(',',':')).encode('utf8')
        results['materialization_bytes_corrupted'] = rejection(lambda:request(bench,first),
            'selective_source_region_source_vertices_mismatch')
        require(not bench.connector.is_alive,'corrupt_client_payload_did_not_invalidate_connector')
    finally:
        bench.close()
    return results


def capacity(root,original,first):
    # The closed-box target Cube is tiny. Its whole reference is the measured
    # historical 53K-face mesh. This exceeds the unmodified cache byte cap.
    reversed_query = deepcopy(first)
    reversed_query['region']['object'],reversed_query['reference'] = (
        reversed_query['reference'],reversed_query['region']['object'])
    reversed_query['region']['world_box_m'] = {'min':[-10.,-10.,-10.],'max':[10.,10.,10.]}
    bench = RecordedMeshes(root,original)
    try:
        large = full(request(bench,reversed_query),reused_resource=False)
        same = full(request(bench,reversed_query),reused_resource=True)
        require(large[0]['work']['connector_retained_bytes']==same[0]['work']['connector_retained_bytes']==0
                and 'known' not in same[2] and len(same[0]['reference']['faces'])==53264,
                'genuinely_large_reference_retained_beyond_connector_bound')
        return [event_rows(value) for value in (large,same)]
    finally:
        bench.close()


def run(output):
    installed,root,pins = check_installed(BINDINGS['B'])
    baseline,baseline_root,base_pins = check_installed(CONTROL['BASE'])
    require(installed['historical_preparation_git']==BASE
            and baseline['preparation_git']==CONTROL['BASE_GIT'],'fixed_installed_identity_changed')
    original = fixture('yanyite',baseline_root)
    queries,source_pins = original[3],original[5]
    sys.path[:0] = [str(root),installed['dependency_root']]
    bench = RecordedMeshes(root,original)
    try:
        checks = controls(bench,queries)
    finally:
        bench.close()
    checks.update(corrupt_controls(root,original,queries[0]))
    checks['actual_byte_capacity'] = capacity(root,original,queries[0])
    pins = [*pins,*base_pins,*source_pins,pin(__file__),pin(HERE/'replay_host.py')]
    save(output,{'passed':True,'scope':'actual_installed_connector_and_host_offline_adversarial_replay',
                 'product_git':installed['preparation_git'],'checks':checks,
                 'source_pins':list({row['path']:row for row in pins}.values()),
                 'actual_Blender':0,'actual_models':0,'actual_rasters':0})


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True,type=Path)
    args = parser.parse_args()
    require(sys.flags.isolated and sys.dont_write_bytecode
            and args.output.resolve().is_relative_to(RUN/'preflight'),'isolated_residency_control_output_required')
    run(args.output.resolve())
