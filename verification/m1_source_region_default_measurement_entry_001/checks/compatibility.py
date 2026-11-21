"""Compare installed MCP replies over frozen producer data and stale host captures."""

import argparse
from copy import deepcopy
from hashlib import sha256
from io import StringIO
import json
from pathlib import Path
from runpy import run_path
import subprocess
import sys
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
V = HERE.parents[1]
PRIOR = V/'m1_sampled_image_path_producer_reuse_001'
MATRIX = PRIOR/'checks/controls.py'
BASE = PRIOR/'install/PRODUCT_RUN_BINDING.json'
CANDIDATE = HERE.parent/'install/PRODUCT_RUN_BINDING.json'
BASE_SOURCE = '9d1644804c13e30b05a81f5186c5b51e51b06dd6bef4d23ee8a08f57c77c0529'
STATE_NAMESPACE = V/'m4_m5_source_region_001'
STATE_ROOT = Path('D:/he_m4_m5_source_region_001')
SESSION = STATE_ROOT/'sessions/state'
STALE = ((6,7,2),(8,10,3))
EXPECTED_STALE = 'source_region_ref_capture_generation_changed'


def require(value, reason):
    if not value:
        raise ValueError(reason)


def read(path):
    return json.loads(path.read_bytes())


def pin(path):
    relative = path.resolve(strict=True)
    raw = relative.read_bytes()
    return {'path':str(relative),'bytes':len(raw),'sha256':sha256(raw).hexdigest()}


def write(path, value):
    with path.open('xb') as stream:
        stream.write((json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode())


def read_lines(path):
    return [json.loads(line) for line in path.read_bytes().splitlines() if line.strip()]


def frozen_stale_requests():
    archive = STATE_NAMESPACE/'RUNTIME_ARCHIVE.json'
    index = {row['relative']:row for row in read(archive)['files']}
    binding = STATE_NAMESPACE/'R1_RUN_BINDING.json'
    original_calls = SESSION/'PUBLIC_REQUESTS.jsonl'
    original_events = SESSION/'native/WORKER_EVENTS.jsonl'
    decoder_path = STATE_NAMESPACE/'oracle/check_saved.py'
    pins = [pin(path) for path in (archive,binding,decoder_path,Path(__file__))]

    def check_archive(path, checksum=None):
        row = index[path.relative_to(STATE_ROOT).as_posix()]
        a = pin(path)
        b = pin(STATE_NAMESPACE/row['copy'])
        require(a['sha256']==b['sha256']==row['sha256'] and a['bytes']==b['bytes']==row['bytes']
                and (checksum is None or a['sha256']==checksum), 'stale_raw_archive_pin_changed/'+path.name)
        pins.extend((a,b))

    for source in (original_calls,original_events):
        check_archive(source)
    for directory in sorted((SESSION/'native/WIRE').glob('[0-9]*')):
        for filename in ('REQUEST.bin','RESPONSE.bin'):
            check_archive(directory/filename)
    decoder = run_path(str(decoder_path))
    captures, commands = decoder['decode_captures'](SESSION,read(binding),decoder['Audit']())
    require(len(captures)==len(commands)==11 and commands[0]['wire_sequence']==1,
            'frozen_capture_sequence_changed')
    by_sequence = {row['wire_sequence']:(capture,row['command'])
                   for row,capture in zip(commands,captures,strict=True)}
    calls = read_lines(original_calls)
    events = {row['sequence']:row for row in read_lines(original_events)}
    result = []
    old_binding = calls[1]['response']['result']['content'][0]['text']
    old_ref = json.loads(old_binding)['region_ref']
    for ordinal, sequence, generation in STALE:
        call = calls[ordinal-1]
        capture, command = by_sequence[sequence]
        event = events[sequence]
        tx = Path(call['actual_TX_path'])
        rx = Path(call['actual_RX_path'])
        check_archive(tx,call['actual_TX_sha256'])
        check_archive(rx,call['actual_RX_sha256'])
        request = read(tx)
        original = read(rx)
        region = request['params']['arguments']['query']['region_ref']
        require(call['id']==request['id']==original['id']==f'observe-{ordinal}'
                and request==call['request'] and original==call['response']
                and command['command']=='capture' and call['started_ns']<=event['started_ns']<call['closed_ns']
                and capture['capture_state']['revision']==generation and region==old_ref
                and region['capture_generation']['revision']==1
                and call.get('producer_archive') is None and original['result']['isError']
                and len(original['result']['content'])==1
                and json.loads(original['result']['content'][0]['text'])['error']==EXPECTED_STALE,
                'stale_request_and_native_capture_not_bound/'+str(ordinal))
        result.append((ordinal,sequence,tx,rx,capture,original))
    return result,pins


def stale_worker(binding_path, output):
    binding = read(binding_path)
    sys.path[:0] = [binding['install_root'],binding['dependency_root']]
    from human_eye_plugin import live_spatial_mcp as mcp, source_region
    from human_eye_plugin.live_service import LiveSpatialService
    from human_eye_plugin.runtime_identity import runtime_identity

    require(runtime_identity()['source_sha256']==binding['source_sha256']
            and Path(mcp.__file__).resolve().is_relative_to(Path(binding['install_root']).resolve()),
            'wrong_installed_stale_runtime')
    output.mkdir()
    config = output/'REPLAY_CONFIG.json'
    state = output/'REPLAY_STATE.json'
    audit = output/'REPLAY_AUDIT.jsonl'
    write(config,{'schema_version':'1.0','enabled':True,'observe_on_prompt':False,'request_budget_s':30,
                  'expected_identity':{'source_sha256':binding['source_sha256']},
                  'project_root':str(output),'state_file':str(state),'audit_file':str(audit)})

    class ArchivedHost:
        def __init__(self,capture):
            self.capture = capture
            self.calls = 0
            self.closed = False

        def capture_scene(self):
            self.calls += 1
            return deepcopy(self.capture)

        def close(self):
            self.closed = True

    requests,pins = frozen_stale_requests()
    cases = {}
    for ordinal,sequence,tx,rx,capture,original in requests:
        host = ArchivedHost(capture)
        service = LiveSpatialService(config,host=host)
        outgoing = StringIO(newline='\r\n')
        valid = source_region.validate_region_ref
        reached = []

        def trace_validation(*args,**kwargs):
            reached.append(True)
            return valid(*args,**kwargs)

        with (patch.object(source_region,'validate_region_ref',trace_validation),
              patch.object(source_region,'observe_region',side_effect=AssertionError('stale_replay_render_forbidden')) as render):
            mcp.run_stdio_mcp_server(service,input_stream=StringIO(tx.read_bytes().decode()),output_stream=outgoing)
        wire = outgoing.getvalue().encode()
        packet = json.loads(wire)
        content = packet['result']['content']
        body = json.loads(content[0]['text'])
        historic_body = json.loads(original['result']['content'][0]['text'])
        require(packet['id']==original['id'] and packet['result']['isError'] is True and len(content)==1
                and content[0]['type']=='text' and body['error']==historic_body['error']==EXPECTED_STALE
                and not body['host_mutation_started'] and not body['connector_state_write_attempted']
                and not body['execution_authority'] and reached==[True] and render.call_count==0
                and host.calls==1 and host.closed and not state.exists(),'actual_stale_rejection_changed/'+str(ordinal))
        target = output/f'observe_{ordinal}_RX.bin'
        target.write_bytes(wire)
        cases[str(ordinal)] = {'native_wire_sequence':sequence,'capture_generation':capture['capture_state']['revision'],
            'archive_TX':pin(tx),'archive_RX':pin(rx),'replayed_RX':pin(target),'reason':body['error'],
            'historical_error_body_equal':body==historic_body,'native_image_blocks':0,'source_region_render_calls':0,
            'archived_host_reads':host.calls,'installed_validator_calls':len(reached),'EOF':host.closed}
    write(output/'STALE.json',{'binding':pin(binding_path),'source_sha256':binding['source_sha256'],
                             'original_pins':pins,'cases':cases})


def compare(output):
    inputs = (read(output/'BASELINE.json'),read(output/'CANDIDATE.json'))
    a,b = inputs
    require(a['original_pins']==b['original_pins'] and a['cases'].keys()==b['cases'].keys()
            and a['source_sha256']==BASE_SOURCE and b['source_sha256']!=BASE_SOURCE,
            'matrix_replay_runtime_or_inputs_changed')
    cases = {}
    for name, old in a['cases'].items():
        new = b['cases'][name]
        packet_a,packet_b = (Path(row['MCP_RX']['path']).read_bytes() for row in (old,new))
        tx_a,tx_b = (Path(row['MCP_TX']['path']).read_bytes() for row in (old,new))
        canonical_path_count = old['expected_B_path']
        unchanged = (packet_a==packet_b and tx_a==tx_b and old['images']==new['images']
                     and old['path_fields']==new['path_fields'] and len(new['path_fields'])==canonical_path_count
                     and old['error']==new['error'] and old['actual_EOF'] and new['actual_EOF']
                     and old['budget_phases']==new['budget_phases'])
        require(unchanged,'description_changed_installed_MCP_replay/'+name)
        cases[name] = {'byte_identical':unchanged,'original_provenance':old['origin'],'error':old['error'],
            'native_PNG_hashes':old['images'],'local_image_paths':new['path_fields'],
            'A_TX':old['MCP_TX'],'B_TX':new['MCP_TX'],'A_RX':old['MCP_RX'],'B_RX':new['MCP_RX']}
    sa,sb = (read(output/f'{arm}_stale/STALE.json') for arm in ('baseline','candidate'))
    require(len(cases)==60 and sa['original_pins']==sb['original_pins'] and sa['source_sha256']==a['source_sha256']
            and sb['source_sha256']==b['source_sha256'],'stale_fixture_or_runtime_mismatch')
    stale = {}
    for ordinal in ('6','8'):
        old,new = (row['cases'][ordinal] for row in (sa,sb))
        exact = Path(old['replayed_RX']['path']).read_bytes()==Path(new['replayed_RX']['path']).read_bytes()
        require(exact and old['archive_TX']==new['archive_TX'] and old['archive_RX']==new['archive_RX'],
                'stale_MCP_reply_not_byte_identical/'+ordinal)
        stale[ordinal] = {'byte_identical':exact,'A':old,'B':new}
    return {'passed':True,'installed_controls':len(cases),'historical_stale_reference_controls':len(stale),
            'byte_identical_business_replies':len(cases)+len(stale),'cases':cases,'stale':stale,
            'A_source':a['source_sha256'],'B_source':b['source_sha256'],
            'new_Blender':0,'new_rasters':0,'new_models':0,
            'scope':'same installed MCP over frozen producer replies; stale cases use actual installed service and validator over original captured host packets'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate',type=Path,default=CANDIDATE)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--stale-worker',action='store_true')
    args = parser.parse_args()
    require(sys.flags.isolated and sys.dont_write_bytecode,'use_pinned_python_I_B')
    output = args.output.resolve()
    if args.stale_worker:
        stale_worker(args.candidate.resolve(strict=True),output)
        return
    output.mkdir(parents=True)
    for arm, install in (('baseline',BASE),('candidate',args.candidate)):
        subprocess.run([sys.executable,'-IB',str(MATRIX),'--worker','--candidate',str(install.resolve()),
                        '--output',str(output/arm),'--shared',str(output/'shared')],check=True,timeout=100)
        subprocess.run([sys.executable,'-IB',str(Path(__file__)), '--stale-worker','--candidate',str(install.resolve()),
                        '--output',str(output/f'{arm}_stale')],check=True,timeout=100)
    result = compare(output)
    write(output/'COMPATIBILITY.json',result)
    print(json.dumps({key:result[key] for key in ('passed','installed_controls','historical_stale_reference_controls',
                    'byte_identical_business_replies','A_source','B_source')},ensure_ascii=False))


if __name__=='__main__':
    main()
