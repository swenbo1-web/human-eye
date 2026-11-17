"""Read each isolated installation's actual public schema without starting a host."""

import argparse
import importlib.util
import json
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--version',choices=('R0','R1'),required=True)
    args=parser.parse_args()
    binding=json.loads((HERE/(args.version+'_RUN_BINDING.json')).read_bytes())
    sys.path.insert(0,binding['dependency_root'])
    spec=importlib.util.spec_from_file_location('_schema_bootstrap',HERE/'harness/reused/verified_bootstrap.py')
    helper=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    guard=helper.bootstrap(binding)
    from human_eye_plugin.live_spatial_mcp import LIVE_MCP_TOOLS_SCHEMA
    tool=next(row for row in LIVE_MCP_TOOLS_SCHEMA if row['name']=='human_eye_scene_observe')
    guard.verify_loaded()
    with (HERE/'public_schema'/(args.version+'_scene_observe.json')).open('x',encoding='utf8',newline='\n') as stream:
        json.dump(tool,stream,sort_keys=True,ensure_ascii=False,indent=2)
        stream.write('\n')
    print(json.dumps(dict(version=args.version,host_started=False)))
