"""Exact installed host replay with the admitted first request and current receipt."""
from argparse import ArgumentParser
import ast
from hashlib import sha256
import json
from pathlib import Path
from runpy import run_path
import sys
from time import perf_counter_ns


HERE = Path(__file__).resolve().parent
PRIOR = HERE.parent/'m4_source_region_selective_visual_capture_001'
ROOT = Path('D:/he_m4_source_region_visual_wire_reuse_001').resolve()
SAME_BOX = ROOT/'preflight/same-box/slots/B/native'
WIRE_SCHEMA = 'human-eye-source-region-visual-wire-v1'


def acknowledged_proof(prior, workspace):
    first = workspace/'call_1/stdout.txt'
    if not first.is_file():
        return {}
    stdout = first.read_text(encoding='utf8')
    start = prior['RPC_PREFIX']
    envelope, = [json.loads(line[len(start):]) for line in stdout.splitlines() if line.startswith(start)]
    packet = envelope['result']
    prior['require'](packet['schema']==WIRE_SCHEMA,'offline_previous_wire_schema')
    proof = packet['proof']
    if proof['generation'] is None:
        return {}
    return {'generation':proof['generation'],
            'receipt_sha256':sha256(prior['signed']([proof]).encode('utf8')).hexdigest()}


def wire_script(prior, original, workspace):
    """Recompute the exact installed code from its one permitted request."""
    require = prior['require']

    def check(request,connector,expected,deadline):
        if expected is None:
            return original(request,connector,expected,deadline)
        require(type(request) is dict and set(request)=={'type','params'}
                and request['type']=='execute_code' and type(request['params']) is dict
                and set(request['params'])=={'code'} and type(request['params']['code']) is str,
                'replay_fixed_execute_request')
        code = request['params']['code']
        assignments = [row.value for row in ast.parse(code).body if isinstance(row,ast.Assign)
                       and len(row.targets)==1 and isinstance(row.targets[0],ast.Name)
                       and row.targets[0].id=='_request']
        require(len(assignments)==1,'replay_generated_assignment')
        assignment, = assignments
        require(isinstance(assignment,ast.Call) and len(assignment.args)==1 and not assignment.keywords
                and ast.unparse(assignment.func)=='_json.loads','replay_generated_literal')
        envelope = json.loads(ast.literal_eval(assignment.args[0]))
        require(set(envelope)=={'id','command','params'} and type(envelope['id']) is str
                and len(envelope['id'])==32 and all(c in '0123456789abcdef' for c in envelope['id'])
                and type(envelope['params']) is dict,'replay_inner_envelope')
        command, params = envelope['command'], envelope['params']
        require(command=='capture_source_region_visual'
                and set(params)=={'query','deadline_ns','max_response_bytes','known'}
                and prior['signed'](params['query'])==prior['signed'](expected)
                and type(params['deadline_ns']) is int and perf_counter_ns()<params['deadline_ns']<=deadline
                and type(params['max_response_bytes']) is int and 1<=params['max_response_bytes']<=64*1024*1024
                and params['known']==acknowledged_proof(prior,workspace),
                'replay_private_closed_box_or_acknowledgment_mismatch')
        require(code==connector._observation_code(command,params,envelope['id']),
                'replay_host_dispatch_not_byte_exact')
        return code,envelope

    return check


def run(args):
    sys.path.insert(0,str(HERE))
    prior = run_path(str(PRIOR/'replay.py'))
    invoke = prior['run']
    prior = invoke.__globals__
    prior['ROOT'] = ROOT
    original = prior['exact_script']
    prior['exact_script'] = wire_script(prior,original,args.workspace)
    if args.workspace==SAME_BOX:
        prior['require'](args.label=='B','same_box_candidate_only')
        fixture = prior['frozen_inputs']

        def same_box(args):
            source, mesh, queries = fixture(args)
            return source,mesh,(queries[0],queries[0])

        prior['frozen_inputs'] = same_box
    return invoke(args)


if __name__=='__main__':
    parser = ArgumentParser(description=__doc__)
    for name in ('terminal','workspace','asset','binding'):
        parser.add_argument('--'+name,required=True,type=lambda text:Path(text).resolve())
    parser.add_argument('--asset-sha256',required=True)
    parser.add_argument('--deadline-ns',required=True,type=int)
    parser.add_argument('--label',required=True,choices=('A','B'))
    run(parser.parse_args())
