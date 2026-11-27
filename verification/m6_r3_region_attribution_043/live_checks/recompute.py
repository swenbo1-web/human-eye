"""043 same-original offline functional recomputation; never starts an application."""
from fractions import Fraction as Q
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import sys

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import run as checks
from check_geometry import need,region


def pin(path):
    path=Path(path).resolve(strict=True);b=path.read_bytes()
    return {'path':str(path),'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}


def load(path):return json.loads(Path(path).read_bytes())


def actual_returns(folder):
    index=load(folder/'RETURN_OBSERVER/INDEX.json');need(index['error']is None,'same_original_observer_succeeded')
    packets=[]
    for ref in index['captures']:
        need(pin(ref['path'])==ref,'same_original_capture_bytes');packets.append(load(ref['path']))
    return packets


def revised_lease_facts(packets):
    need(len(packets)==4,'same_four_original_calls_no_replacement')
    captures=[p['capture']for p in packets];reply=[p['residency_reply']for p in packets]
    sha=[c['payload_sha256']for c in captures];work=[c['work']for c in captures]
    need(sha[0]==sha[1]and sha[2]==sha[3]and sha[0]!=sha[2],'current_geometry_payload_replaces_old')
    need(work[1]['connector_reused_payload']is True and reply[1]['capture']is None,'old_actual_lease_hit')
    need(work[2]['connector_reused_payload']is False and reply[2]['capture']is not None and reply[2]['lease']is None,'changed_geometry_old_lease_refused')
    need(work[2]['mode']=='uncached_capture'and work[2]['fallback_reason']=='retained_resource_unavailable'and work[2]['connector_retained_bytes']==0,'documented_uncached_fallback_clears_connector')
    need(work[3]['mode']=='resident_capture'and work[3]['connector_reused_payload']is False and reply[3]['capture']is not None,'repeat_is_full_new_resident_capture_not_hit')
    old,new=reply[1]['lease'],reply[3]['lease']
    need(new is not None and old!=new and new['revision']>old['revision']and new['payload_sha256']==sha[3],'new_actual_lease_bound_to_changed_geometry')
    return {'contract_edit_invalidation':'pass','modes':[w['mode']for w in work],
        'connector_reused_payload':[w['connector_reused_payload']for w in work],
        'fallback_reasons':[w.get('fallback_reason')for w in work],
        'payload_sha256':sha,'old_lease':old,'new_lease':new,
        'extra_immediate_post_edit_lease_hit_assertion':'failed_preserved',
        'last_repeat_is_lease_hit':False,'new_lease_established_on_last_repeat':True,
        'additional_reads_or_GUI_runs':0,
        'basis':'original native full/ack residency replies and original connector materialized return work; never inferred from elapsed time'}


def main(result_path,output):
    path=Path(result_path);data=load(path);plan=load(data['plan']['path']);need(pin(data['plan']['path'])==data['plan'],'frozen_recovered_plan')
    for ref in [*plan['sources'].values(),*plan['reused_sources'].values()]:need(pin(ref['path'])==ref,'same_frozen_sources')
    root=path.parent;cases={c['case']:c for c in data['cases']}
    need(set(cases)==set(plan['case_order']),'all_original_three_cases_present')
    report={'schema':'m6-043-live-same-original-recomputation-v1',
        'status':'contract_functional_pass_with_extra_lease_hit_assertion_failure',
        'original_strict_result':pin(path),'original_status':data['status'],'plan':data['plan'],
        'scene_reads':0,'application_launches':0,'replacement_samples':0,'cases':{},'cleanup':[]}
    for name,case in cases.items():
        need(case['GUI_close']['status']=='pass'and case['GUI_close']['process_reaped']and case['GUI_close']['exit_code']==0,'actual_original_GUI_cleanup')
        need(case['GUI_close']['released_port']['any_listener']is False,'actual_original_port_released')
        close={'case':name,'GUI_pid':case['pid'],'GUI_close_ns':case['GUI_close']['elapsed_ns'],
               'GUI_close':case['GUI_close'],'products':{}}
        for arm,value in case['arms'].items():
            need(not value['errors']and value['close']['exit_code']==0 and value['close']['method']=='eof','actual_original_stdio_cleanup')
            folder=root/name/arm/'client';startup=load(folder/'STARTUP.json');identity=startup['hello']['result']['_meta']['human_eye']
            need(identity['production_mode']is True and identity['source_file_count']==143 and identity['source_sha256']==plan['arms'][arm]['source_sha256'],'actual_original_loaded_production_identity')
            close['products'][arm]={'physical_PID':startup['actual_pid'],'Popen_PID':load(folder/'LAUNCH.json')['popen_pid'],
                'EOF_close_ns':value['close']['wall_ns'],'exit_code':0,'startup':pin(folder/'STARTUP.json')}
        report['cleanup'].append(close)
        if name=='fixed_M4_pair':
            c=[r['result']for r in case['arms']['C']['rows']];a=case['arms']['A']['rows'][0]['result']
            checked=checks.check_m4(plan,[*c,a],[root/name/'C/client',root/name/'A/client'])
            # Independently verify the original exact return points lie on the
            # two frozen canonical native triangles. No full solver is rerun.
            source=load(plan['M4_scene']['snapshot']['path']);objects={o['name']:o for o in source['objects']}
            modpath=checks.VER/'m6_bvh_witness_projection_029/oracle.py'
            spec=importlib.util.spec_from_file_location('m6_043_live_exact_point_membership',modpath);oracle=importlib.util.module_from_spec(spec);sys.modules[spec.name]=oracle;spec.loader.exec_module(oracle)
            membership=[]
            for arm in ('C','A'):
                returns=load(root/name/arm/'client/RETURN_OBSERVER/SURFACE_RETURNS.json')
                for returned in returns:
                    points=[tuple(map(Q,p))for p in returned['exact_world_points']]
                    for side,objname in enumerate(('Obj_014','Obj_003')):
                        obj=objects[objname];vertices=obj['vertices_world'];faces=obj['triangles'];row=plan['M4_independent_truth']['canonical_native_source_triangle_pair'][side]
                        triangle=[tuple(Q(x)for x in vertices[v])for v in faces[row]]
                        need(oracle.point_hull(points[side],oracle.hull(triangle))[0]==0,'independent_actual_point_native_hull_membership')
                    membership.append({'arm':arm,'exact_source_points_valid':True})
            checked.update(independent_actual_exact_point_membership=membership,point_oracle_source=pin(modpath))
            report['cases'][name]=checked
            continue
        frozen=load(plan['low_geometry']['path']if name=='same_asset_low'else plan['high_geometry']['path'])
        packets=actual_returns(root/name/'C/client');apackets=actual_returns(root/name/'A/client')
        c=[r['result']for r in case['arms']['C']['rows']];a=case['arms']['A']['rows'][0]['result'];out=[]
        for i,(packet,public)in enumerate(zip(packets,c)):
            out.append(region(packet['capture'],frozen,public,reference_shift=Q(1,64)if name=='real_Cube_edit'and i>=2 else Q(0)))
        out.append(region(apackets[0]['capture'],frozen,a,reference_shift=Q(1,64)if name=='real_Cube_edit'else Q(0)))
        need(c[-1]==c[-2]==a,'same_original_C_current_warm_A_full_public_geometry')
        checked={'status':'pass','independent_readback':out,'C_and_A_complete_current_public_result_equal':True,
                 'actual_published_bytes':[pin(p)for p in (root/name).rglob('*.RX.bin')]}
        if name=='real_Cube_edit':
            checked['lease_facts']=revised_lease_facts(packets)
            edit=load(root/name/'EDIT.json');need(edit['actual']['delta']==1/64,'same_original_actual_dyadic_edit')
            need(pin(edit['saved_file']['path'])==edit['saved_file'],'actual_saved_private_file_identity')
            checked['actual_edit']=pin(root/name/'EDIT.json');checked['saved_file']=edit['saved_file']
            need(len(case['errors'])==1 and 'actual_lease_invalidated_and_reestablished'in case['errors'][0],'only_preserved_extra_lease_assertion_failed')
        else:need(case['status']=='pass'and not case['errors'],'original_low_case_pass')
        report['cases'][name]=checked
    siteC=Path(plan['arms']['C']['site_packages']);siteA=Path(plan['arms']['A']['site_packages'])
    audited=[]
    for file in ('blender_host.py','blender_mcp_host.py','scene_residency.py'):
        a,b=pin(siteA/'human_eye_plugin'/file),pin(siteC/'human_eye_plugin'/file)
        need(a['sha256']==b['sha256'],'original_host_residency_code_unchanged_A_C');audited.append({'A':a,'C':b})
    report['cache_source_provenance']={'files':audited,
        'host_fallback':'blender_host.capture_source_region_pair: known==prior and resource stamps unavailable sets retained_resource_unavailable and uses uncached capture',
        'connector':'capture_source_region_pair clears _selective_capture before native read; only a returned non-null lease can reestablish it',
        'extra_hit_expectation':'not part of contractual current-geometry/invalidation requirement; remains failed in original receipt'}
    report['closure_cost']={'product_EOF_close_sum_ns':sum(p['EOF_close_ns']for c in report['cleanup']for p in c['products'].values()),
        'GUI_close_sum_ns':sum(c['GUI_close_ns']for c in report['cleanup']),
        'scope':'sum of six sequential recorded product EOF close intervals and three ordinary GUI close intervals; not the full functional window',
        'process_tree_CPU_and_peak_RSS':'not sampled for this functional-only run; raw wrapper-PID counters do not establish whole-process-tree bounds'}
    report['analysis_source']=pin(__file__)
    checks.dump(output,report);print(pin(output));return report


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--result',required=True);parser.add_argument('--output',required=True);a=parser.parse_args();main(a.result,a.output)
