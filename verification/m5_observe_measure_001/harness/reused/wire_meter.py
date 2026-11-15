"""QA wire recording and existing residency counters, with no profiler."""
import json
from pathlib import Path
import sys

RECORDS = []


class WireSocket:
    def __init__(self, connection, sequence):
        self.connection = connection
        self.row = {'sequence': sequence, 'request': bytearray(), 'response': b'',
                    'sendall_completed': False}
        RECORDS.append(self.row)

    def __getattr__(self, name):
        return getattr(self.connection, name)

    def __enter__(self):
        self.connection.__enter__()
        return self

    def __exit__(self, *error):
        return self.connection.__exit__(*error)

    def recv(self, count):
        raw = self.connection.recv(count)
        self.row['request'].extend(raw)
        return raw

    def sendall(self, raw):
        self.row['response'] = raw
        self.connection.sendall(raw)
        self.row['sendall_completed'] = True


def host_work():
    hosts = {}
    for module in list(sys.modules.values()):
        namespace = getattr(module, '__dict__', {})
        host = namespace.get('_mcp_resident_host')
        if host is None or id(host) in hosts:
            continue
        state = getattr(host, '_residency', None)
        resources = {} if state is None else {
            str(key): {'revision': value['revision'], 'vertices': len(value['vertices_local']),
                       'faces': len(value['faces']), 'edges': len(value['edges'])}
            for key, value in state.resources.items()}
        hosts[id(host)] = {'module': namespace.get('__name__'), 'work': host.residency_work(),
                          'resources': resources,
                          'generation': None if state is None else {
                              'instance_id': state.instance_id, 'epoch': state.epoch, 'revision': state.revision}}
    return list(hosts.values())


def finish_rpc(before, namespace):
    after = host_work()
    old = {key: value for host in before for key, value in host['resources'].items()}
    created = [value for host in after for key, value in host['resources'].items()
               if key not in old or old[key]['revision'] != value['revision']]
    return {'before': before, 'after': after,
            'new_resource_arrays': {key: sum(value[key] for value in created)
                                    for key in ('vertices', 'faces', 'edges')},
            'native_work': namespace.pop('_m2_native_last_work', None),
            'scope': 'existing counters and actually materialized resource arrays; total loop visits otherwise unmeasured'}


def flush(workspace):
    folder = Path(workspace) / 'WIRE'
    folder.mkdir(exist_ok=False)
    rows = []
    for record in RECORDS:
        target = folder / str(record['sequence']).zfill(3)
        target.mkdir()
        (target / 'REQUEST.bin').write_bytes(record['request'])
        (target / 'RESPONSE.bin').write_bytes(record['response'])
        rows.append({'sequence': record['sequence'], 'request_bytes': len(record['request']),
                     'response_attempted_bytes': len(record['response']),
                     'response_sendall_completed': record['sendall_completed'],
                     'request_response_attempted_bytes': len(record['request']) + len(record['response'])})
    (folder / 'INDEX.json').write_text(json.dumps(rows, indent=2) + '\n', encoding='utf8')
