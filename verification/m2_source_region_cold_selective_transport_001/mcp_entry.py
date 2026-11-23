"""Expose a private measurement only inside the held experimental process."""

import json
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from host import LABELS, PREVIOUS, PRIVATE_TOOL, load, require
from meter import observe_installed


def call_production(main,arguments,evidence,source_sha256):
    from human_eye_plugin import live_spatial_mcp

    label = evidence.parent.name
    old = live_spatial_mcp.LiveSpatialMCPServer._dispatch_tool
    sequence = 0

    def dispatch(server,name,params):
        nonlocal sequence
        if name != PRIVATE_TOOL or LABELS[label][1] != 'B':
            return old(server,name,params)
        require(type(params) is dict and set(params) == {'query','include_image'},
                'private_measurement_query_and_image_flag_required')
        result = server.service._measure_selective_source_region(
            server.default_session_id,params['query'],include_image=params['include_image'])
        sequence += 1
        raw = json.dumps(result,ensure_ascii=False,allow_nan=False,sort_keys=True,separators=(',',':'))
        with (evidence/f'PRIVATE_RESULT_{sequence}.json').open('x',encoding='utf8') as stream:
            stream.write(raw+'\n')
        return {'isError':False,'content':[{'type':'text','text':raw}]}

    if LABELS[label][1] == 'B':
        live_spatial_mcp.LiveSpatialMCPServer._dispatch_tool = dispatch
    try:
        with observe_installed(evidence,source_sha256):
            return main(arguments)
    finally:
        live_spatial_mcp.LiveSpatialMCPServer._dispatch_tool = old


if __name__ == '__main__':
    entry = load('_selective_retained_held_entry',PREVIOUS/'mcp_entry.py')
    entry.call_production = call_production
    raise SystemExit(entry.main())
