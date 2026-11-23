"""Verify the installed private connector against exact and adversarial packet fixtures."""

import argparse
import ast
from hashlib import file_digest
import json
from pathlib import Path
import sys
import time
from unittest.mock import patch


RUN = Path('D:/he_m2_source_region_selective_residency_001').resolve()
HERE = Path(__file__).resolve().parent
TARGET, REFERENCE = {'name':'A'}, {'name':'B'}
POSITIVE = {'min':[0.,0.,0.], 'max':[0.,1.,1.]}
NEGATIVE = {'min':[-0.,0.,0.], 'max':[0.,1.,1.]}
MATRIX = [[float(i==j) for j in range(4)] for i in range(4)]
ZEROABLE = ('expanded_objects','expanded_vertices','expanded_triangles','transmitted_objects',
            'transmitted_vertices','transmitted_triangles','box_vertices_scanned','box_triangles_scanned',
            'to_mesh','triangulations','world_transforms','world_vertices_transformed')
FULL_WORK = {
    'candidate_objects':3,'expanded_objects':2,'expanded_vertices':6,'expanded_triangles':2,
    'transmitted_objects':2,'transmitted_vertices':6,'transmitted_triangles':2,
    'private_cache_retained_objects':0,'mode':'resident_capture','box_vertices_scanned':3,
    'box_triangles_scanned':1,'to_mesh':2,'triangulations':2,'world_transforms':2,'world_vertices_transformed':6,
    'retained_resources':2,'retained_vertices':6,'retained_triangles':2,'retained_compact_leases':1,
    'fallback_reason':None,
}
ACK_WORK = dict(FULL_WORK,**dict.fromkeys(ZEROABLE,0))
ACK_WORK['mode'] = 'lease_hit'


def pin(path):
    path = Path(path).resolve(strict=True)
    with path.open('rb') as source:
        return {'path':str(path),'bytes':path.stat().st_size,'sha256':file_digest(source,'sha256').hexdigest()}


class ExchangeFixture:
    """Replace the connection only; the installed request assembly and decoder run unchanged."""

    def __init__(self, project, mcp, digest, error, unavailable):
        self.host = mcp.BlenderMCPHost(project)
        self.host._exchange = self.exchange
        self.mcp, self.digest, self.error, self.unavailable = mcp,digest,error,unavailable
        self.requests = []
        self.mode = self.lease = self.previous_id = None

    def full(self, args):
        left = {'object_id':'left','instance_id':'left-instance','name':'A'}
        right = {'object_id':'right','instance_id':'right-instance','name':'B'}
        source_sha = self.host._readonly_host_source_sha256
        binding = {
            'capture_scope':'selected_source_region_and_reference','document_epoch':'1'*64,
            'host_source_sha256':source_sha,'target_selector':args['target'],'reference_selector':args['reference'],
            'world_box_m':POSITIVE if self.mode=='wrong_zero' else args['world_box_m'],
            'target':left,'reference':right,'unit':'m','coordinate_frame':'world',
            'source_frame':{'frame':1,'subframe':0.,'scale_length':1.,'view_layer':'layer'},
            'world_matrices':{'target':MATRIX,'reference':MATRIX},
        }
        region = {
            'vertices':[[0.,0.,0.],[0.,1.,0.],[0.,0.,1.]],'faces':[[0,1,2]],
            'source_triangle_indices':[0],'source_vertex_indices':[0,1,2],
            'source_triangle_vertices':[[0,1,2]],'source_triangle_count':1,'source_vertex_count':3,
        }
        whole = {'vertices':[[2.,0.,0.],[2.,1.,0.],[2.,0.,1.]],'faces':[[0,1,2]]}
        capture = {'schema':'human-eye-selective-source-region-capture-v1',
                   'binding':binding,'region':region,'reference':whole}
        capture['payload_sha256'] = self.digest(capture)
        self.lease = {'document_epoch':'1'*64,'instance_id':'2'*32,'epoch':1,
                      'revision':2 if self.mode=='cache_loss' else 1,'payload_sha256':capture['payload_sha256'],
                      'selection_sha256':'3'*64}
        capture.update(work=FULL_WORK,stages={})
        return {'lease':self.lease,'capture':capture,'work':FULL_WORK}

    def exchange(self, payload, *, deadline_ns, max_response_bytes):
        script = json.loads(payload)['params']['code']
        assignment, = (line for line in script.splitlines() if line.startswith('_request = '))
        request = json.loads(ast.literal_eval(ast.parse(assignment).body[0].value.args[0]))
        args = request['params']
        assert request['command']=='capture_source_region_pair'
        assert args['deadline_ns']==deadline_ns and args['max_response_bytes']==max_response_bytes
        self.requests.append(args)
        known = args.get('known')
        old_id,self.previous_id = self.previous_id,request['id']
        if self.mode=='disconnect':
            raise self.unavailable('controlled preconnect refusal')
        reply = {'schema':'human-eye-private-source-region-residency-v1',
                 'host_source_sha256':self.host._readonly_host_source_sha256,'stages':{}}
        if (known is not None and self.mode!='cache_loss') or self.mode=='forced_ack':
            lease = known if known is not None else self.lease
            if self.mode=='wrong_lease':
                lease = dict(lease,selection_sha256='9'*64)
            work = dict(ACK_WORK)
            if self.mode=='ack_work':
                work['box_triangles_scanned'] = 1
            reply.update(lease=lease,capture=None,work=work)
        else:
            reply.update(self.full(args))
        if self.mode=='wrong_source':
            reply['host_source_sha256'] = '4'*64
        encoded = json.dumps({'protocol_version':'1.0','id':old_id if self.mode=='old_id' else request['id'],
                              'result':reply})
        if self.mode=='duplicate':
            encoded = encoded.replace('"result":','"result": {}, "result":',1)
        return {'status':'success','result':{'executed':True,'result':self.mcp.RPC_PREFIX+encoded+'\n'}}

    def call(self, box=POSITIVE, budget=64*1024*1024):
        with self.host.observation_transaction():
            return self.host.capture_source_region_pair(TARGET,REFERENCE,box,
                time.perf_counter_ns()+5_000_000_000,budget)

    def reject(self, expected, **call_args):
        try:
            self.call(**call_args)
        except self.error as error:
            assert expected in str(error) and self.host._selective_capture is None
            return str(error)
        raise AssertionError('a private reply was accepted unexpectedly/'+expected)


def controls(project, mcp, source, host_module, process):
    def fixture():
        return ExchangeFixture(project,mcp,host_module._digest,
            process.HostTransportError,mcp._ReadonlyPreconnectUnavailable)

    results = {}
    trial = fixture()
    first = trial.call()
    initial = source.measure_selective_region(first,TARGET,REFERENCE,POSITIVE,trial.host._readonly_host_source_sha256)
    assert first['work']['connector_reused_payload'] is False
    assert first['work']['connector_retained_bytes']>0
    first['region']['vertices'][0][0] = 99.  # Returned tree cannot change retained serialized geometry.
    second = trial.call()
    resumed = source.measure_selective_region(second,TARGET,REFERENCE,POSITIVE,trial.host._readonly_host_source_sha256)
    assert resumed['facts']==initial['facts'] and resumed['source_mapping']==initial['source_mapping']
    assert second['work']['connector_reused_payload'] is True and second['region']['vertices'][0][0]==0.
    assert all(second['work'][key]==0 for key in ZEROABLE)
    results['cold_ack_current_work_and_mutation_isolation'] = {
        'work':second['work'],'distance_m':resumed['facts']['surface_proximity']['value']['distance_m']}
    trial.mode = 'cache_loss'
    fallback = trial.call()
    assert fallback['work']['connector_reused_payload'] is False
    assert trial.requests[-1]['known']['revision']==1 and trial.host._selective_capture[1]['revision']==2
    results['lost_host_cache_full_fallback'] = {'old_revision':1,'new_revision':2}

    trial.mode = None
    assert not trial.call(NEGATIVE)['work']['connector_reused_payload'] and 'known' not in trial.requests[-1]
    assert trial.call(NEGATIVE)['work']['connector_reused_payload']
    assert not trial.call(POSITIVE)['work']['connector_reused_payload'] and 'known' not in trial.requests[-1]
    results['signed_zero_distinct_cache_key'] = {'same_negative_ack':True,'changed_sign_known_sent':False}
    trial.mode = 'wrong_zero'
    results['rehashed_wrong_signed_box'] = {'error':trial.reject('selective_source_region_box_binding',box=NEGATIVE)}

    for name,mode,reason in (
        ('wrong_host_source','wrong_source','residency_envelope'),
        ('wrong_lease','wrong_lease','ack_without_exact_capture'),
        ('old_response_request_id','old_id','identity or protocol'),
        ('duplicate_json_response_field','duplicate','Duplicate JSON key'),
        ('ack_lies_about_host_scan','ack_work','capture_accounting'),
    ):
        trial = fixture()
        trial.call()
        trial.mode = mode
        results[name] = {'error':trial.reject(reason)}
        assert not trial.host.is_alive

    trial = fixture()
    trial.call()
    trial.mode = 'disconnect'
    error = trial.reject('controlled preconnect refusal')
    assert trial.host.is_alive
    trial.mode = None
    assert not trial.call()['work']['connector_reused_payload'] and 'known' not in trial.requests[-1]
    trial.host.close()
    assert trial.host._selective_capture is None
    results['preconnect_disconnect_no_reuse_then_close'] = {'error':error,'retried_immediately':False}

    trial = fixture()
    with patch.object(mcp,'_SELECTIVE_CAPTURE_CACHE_BYTES',2):
        trial.call()
    assert trial.host._selective_capture is None
    trial.mode = 'forced_ack'
    results['bounded_cache_eviction'] = {'error':trial.reject('ack_without_exact_capture'),'cache_limit':2}

    trial = fixture()
    trial.call()
    trial.mode = 'forced_ack'
    error = trial.reject('ack_without_exact_capture',budget=1)
    assert 'known' not in trial.requests[-1]
    results['lower_request_budget_blocks_old_lease'] = {'error':error,'known_sent':False}

    assert len(results)==12
    return {name:{'passed':True,**row} for name,row in results.items()}


def run(binding_path):
    binding_path = binding_path.resolve(strict=True)
    binding = json.loads(binding_path.read_bytes())
    installed = Path(binding['install_root']).resolve(strict=True)
    wheel = pin(binding['wheel_path'])
    assert wheel['sha256']==binding['wheel_sha256']
    sys.path[:0] = [str(installed),binding['dependency_root']]
    from human_eye_plugin import blender_mcp_host, blender_host, source_region, blender_process

    manifests = {row['path']:row['sha256'] for row in binding['source_manifest']}
    consumed = []
    for module in (blender_mcp_host,blender_host,source_region,blender_process):
        proof = pin(module.__file__)
        relative = Path(proof['path']).relative_to(installed).as_posix()
        assert manifests[relative]==proof['sha256']
        consumed.append(proof)
    checked = controls(installed,blender_mcp_host,source_region,blender_host,blender_process)
    return {'passed':True,'case_count':len(checked),'cases':checked,
            'kind':'actual_installed_connector_with_deterministic_exchange_fixture',
            'product_git':binding['preparation_git'],'source_sha256':binding['source_sha256'],
            'actual_Blender':0,'actual_models':0,'actual_rasters':0,'actual_sockets':0,
            'source_pins':[pin(__file__),pin(sys.executable),pin(binding_path),wheel,*consumed]}


if __name__=='__main__':
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--binding',type=Path,default=HERE/'install/PRODUCT_RUN_BINDING.json')
    cli.add_argument('--output',type=Path,default=RUN/'preflight/PACKET_CONTROLS.json')
    args = cli.parse_args()
    assert sys.flags.isolated and sys.dont_write_bytecode
    output = RUN/'preflight/PACKET_CONTROLS.json'
    assert args.output.resolve()==output and not output.exists()
    proof = run(args.binding)
    with output.open('x',encoding='utf8',newline='\n') as dst:
        json.dump(proof,dst,ensure_ascii=False,allow_nan=False,sort_keys=True,indent=2)
        dst.write('\n')
    print('Verified',proof['case_count'],'installed connector packet controls',flush=True)
