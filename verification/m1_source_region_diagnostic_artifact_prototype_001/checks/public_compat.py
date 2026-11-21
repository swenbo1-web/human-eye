"""Recheck legacy public full and brief against the same archived producers."""

from copy import deepcopy
import json
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parent))
from prototype import load_fixtures, require, verified_product


def run(root):
    mcp = verified_product()
    reports = {}
    compatibility = root/'public_compatibility'
    compatibility.mkdir()
    for label, fixture in load_fixtures().items():
        original = json.loads(fixture.rx_raw)
        first = json.loads((root/label/'FIRST_RX.bin').read_bytes())

        class FrozenProducer:
            def __init__(self):
                self.calls = 0
                if fixture.image_frame is not None:
                    directory = Path(fixture.image_frame['image_path']).parent.parent
                    self.state_path = directory.with_name(directory.name.removesuffix('.source_region'))

            def observe(self, _session_id, *, query, include_image, **_kwargs):
                args = fixture.request['params']['arguments']
                require(query == args['query'] and include_image == args['include_image'], 'original_job_changed')
                self.calls += 1
                return deepcopy(fixture.producer)

            def _check_request_budget(self, *_args, **_kwargs):
                pass

        service = FrozenProducer()
        server = mcp.LiveSpatialMCPServer(service)
        baseline_brief = json.loads(first['result']['content'][0]['text'])
        del baseline_brief['diagnostic_artifact']
        replies = {}
        for detail in ('full', 'brief', 'default'):
            tx = deepcopy(fixture.request)
            if detail == 'default':
                tx['params']['arguments'].pop('response_detail')
            else:
                tx['params']['arguments']['response_detail'] = detail
            rx = server.handle_jsonrpc_message(tx)
            result = rx['result']
            text = result['content'][0]['text']
            expected = json.loads(original['result']['content'][0]['text']) if detail == 'full' else baseline_brief
            require(result['isError'] is False and json.loads(text) == expected
                    and result['content'][1:] == original['result']['content'][1:],
                    'legacy_public_route_changed/' + label + '/' + detail)
            (compatibility/f'{label}_{detail}_TX.bin').write_bytes((json.dumps(tx)+'\r\n').encode())
            (compatibility/f'{label}_{detail}_RX.bin').write_bytes(
                (mcp.wire.encode_response(rx,tx).removesuffix('\n')+'\r\n').encode())
            replies[detail] = {'public_text_bytes': len(text.encode()), 'passed': True}
        require(service.calls == 3, 'unexpected_public_dispatch_count')
        reports[label] = replies
    (compatibility/'PUBLIC_COMPAT.json').write_text(json.dumps({'passed': 6, 'planned': 6, 'cases': reports},
                                                              indent=2)+'\n', encoding='utf8',newline='\n')


if __name__ == '__main__':
    require(sys.flags.isolated and sys.dont_write_bytecode, 'use_pinned_interpreter_I_B')
    run(Path(sys.argv[1]))
