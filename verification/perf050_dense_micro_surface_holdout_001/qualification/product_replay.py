"""Exercise the installed service and CLI replay over the planned geometry in memory."""

import argparse
from copy import deepcopy
from io import StringIO
import json
from pathlib import Path
from runpy import run_path
import sys


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from product_identity import BINDING, SOURCE
from product_qa import CONDITIONS, DISCOVER, MEASURE, TOOL, V, body, check_cli, digest, read, require, save, verify_measurement


def planned_capture():
    slot = Path('D:/he_m4_dense_region_brief_001/slots/QP')
    old = V/'m4_dense_region_brief_001/install/PRODUCT_RUN_BINDING.json'
    checker = run_path(str(V/'m4_cross_scale_discovery_001/oracle/check_saved.py'))
    audit = checker['Audit']()
    old_captures, commands = checker['decode_captures'](slot, read(old), audit)
    binding = read(slot/'product_full/call_001/SERVICE_RESULT.json')['binding']
    capture = deepcopy(checker['current_capture'](old_captures, binding, audit))
    snapshot = capture['display_snapshot']
    patches = [
        ('S021', 4.5, 0.5, 1.875, 1/16, 1/16, True), ('S034', 1.5, 0.5, 1.875, 1/16, 1/16, True),
        ('S055', 7.5, 0.5, 1.875, 1/16, 1/16, True), ('S012', 5.5, 0.5, 1.875, 1/16, 13/256, True),
        ('S067', 9.5, 0.5, 1.875, 1/16, 19/256, True), ('S041', 10.5, 0.5, 1.875, 1/16, 1/16, False),
        ('S019', 243/32, 13/32, 2., 5/16, 5/16, True),
    ]
    for index, (name, x, y, z, width, height, forward) in enumerate(patches, len(capture['meshes'])+1):
        left, right = x - width/2, x + width/2
        low, high = y - height/2, y + height/2
        points = [[left,low,z], [right,low,z], [right,high,z], [left,high,z]]
        faces = [[0,1,2], [0,2,3]] if forward else [[0,2,1], [0,3,2]]
        host_id, instance = 'blender:' + digest(name.encode()), str(10000 + index)
        mesh = deepcopy(capture['meshes'][0])
        mesh.update(name=name, object_id=host_id, mark_label=f'#B{index:04}', vertices=points, faces=faces,
                    edges=[[0,1],[1,2],[2,3],[0,3],[0,2]], color_rgb=[45,108,179])
        capture['meshes'].append(mesh)
        capture['host_identity']['object_instances'][host_id] = instance
        snapshot['objects'].append(dict(snapshot['objects'][0], host_id=host_id, instance_id=instance))
    unsigned = {k:v for k,v in snapshot.items() if k!='sha256'}
    snapshot['sha256'] = digest(json.dumps(unsigned, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode())
    return capture, commands


def replay(output):
    installed = read(BINDING)
    sys.path[:0] = [installed['install_root'], installed['dependency_root']]
    from human_eye_plugin import live_spatial_mcp as mcp
    from human_eye_plugin.live_service import LiveSpatialService

    capture, commands = planned_capture()
    output.mkdir()
    save(output/'MEMORY_CAPTURE.json', capture)
    config = output/'CONFIG.json'
    save(config, {'schema_version':'1.0','enabled':True,'observe_on_prompt':False,
        'project_root':installed['install_root'],'state_file':str(output/'product_state.json'),
        'audit_file':str(output/'product_audit.jsonl'),'request_budget_s':60,
        'expected_identity':{'source_sha256':SOURCE}})

    class RetainedHost:
        def capture_scene(self):
            return deepcopy(capture)

    class Service(LiveSpatialService):
        def __init__(self):
            super().__init__(config, host=RetainedHost())
            self.producers = []
            self.closed = False

        def observe(self, *args, **kwargs):
            value = super().observe(*args, **kwargs)
            self.producers.append(deepcopy(value))
            return value

        def close(self):
            self.closed = True

    def call(key, arguments):
        return {'jsonrpc': '2.0', 'id': key, 'method': 'tools/call', 'params': {'name': TOOL, 'arguments': arguments}}

    rows = [call('rejected', {'query': {'mode':'active_observation', 'region_task':dict(CONDITIONS, normal_z_min=2)}}),
            call('discovery', DISCOVER), call('measurement', MEASURE)]
    incoming = ''.join(json.dumps(row)+'\n' for row in rows)
    (output/'TX.jsonl').write_bytes(incoming.encode())
    outgoing = StringIO()
    service = Service()
    mcp.run_stdio_mcp_server(service, input_stream=StringIO(incoming), output_stream=outgoing)
    raw = outgoing.getvalue()
    (output/'RX.jsonl').write_bytes(raw.encode())
    responses = [json.loads(line) for line in raw.splitlines()]
    require(len(responses) == 3 and responses[0]['result']['isError'] is True and service.closed
            and len(service.producers) == 2, 'installed_readonly_preflight_route_did_not_close')
    results = {}
    for label, result, producer in zip(('discovery','measurement'), (p['result'] for p in responses[1:]),
                                         service.producers, strict=True):
        save(output/f'{label}_PRODUCER.json', producer)
        save(output/f'{label}_MCP.json', result)
        try:
            packet = body(result)
        except ValueError as error:
            results[label] = {'error':str(error)}
            continue
        proof = {'CLI': check_cli(result, output, label), 'work':producer['work']}
        if label == 'discovery':
            proof.update(rows=packet['region_task']['rows'], frames=packet['frames'], witnesses=packet['witnesses'],
                         blocked=packet['blocker_evidence'])
        else:
            proof.update(measurement=verify_measurement(result, producer, service.producers[0]['binding']))
        results[label] = proof
    report = {'qualification': False, 'purpose': 'Offline installed preflight only. Old captured meshes plus planned '
              'dyadic rows in memory. No actual derived asset or material attested.', 'source_sha256':SOURCE,
              'source_captures_commands':len(commands), 'owned_Blender':0, 'models':0,
              'closed':service.closed, 'pre_request_rejection':responses[0]['result']['content'], 'results':results}
    save(output/'PREFLIGHT.json', report)
    print(json.dumps({'closed':service.closed, 'results':{label: {'error':row.get('error'),
        'text_bytes':row.get('CLI',{}).get('original_text_bytes'), 'cli_exact':row.get('CLI',{}).get('passed'),
        'rasters':row.get('work',{}).get('raster_attempts')} for label,row in results.items()}}))


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    replay(parser.parse_args().output.resolve())
