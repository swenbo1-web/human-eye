"""Read the tool schema from the controlled isolated candidate."""

import importlib.util
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
binding = json.loads((HERE / 'R0_RUN_BINDING.json').read_bytes())
sys.path.insert(0, binding['dependency_root'])
path = HERE / 'harness/reused/verified_bootstrap.py'
spec = importlib.util.spec_from_file_location('_schema_bootstrap', path)
bootstrap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bootstrap)
guard = bootstrap.bootstrap(binding)
from human_eye_plugin.live_spatial_mcp import LIVE_MCP_TOOLS_SCHEMA

schema = next(value for value in LIVE_MCP_TOOLS_SCHEMA if value['name'] == 'human_eye_scene_observe')
with (HERE / 'public_schema/R0_scene_observe.json').open('x', encoding='utf8', newline='\n') as stream:
    json.dump(schema, stream, sort_keys=True, indent=2)
    stream.write('\n')
guard.verify_loaded()
