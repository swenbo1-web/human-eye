"""Pinned common experimental stdio adapter; no default-app activation."""
import json
from pathlib import Path
import sys
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1];sys.path.append(str(ROOT))


def main(spec_path):
    spec=json.loads(Path(spec_path).read_text())
    if spec['arm'] not in ('native','he'):raise ValueError('arm')
    if spec['arm']=='he':
        gate=Path(spec['he_gate_file']);registration=json.loads(gate.read_text())
        if registration.get('new_HE_trials_permitted') is not True:raise ValueError('HE_comparability_not_registered')
    from verification.engineering_task_contract import bootstrap
    bootstrap(spec['entry'])
    from human_eye_plugin.live_spatial_mcp import LiveSpatialMCPServer
    from human_eye_plugin.live_service import LiveSpatialService
    from verification.engineering_native_service import NativeService,ReadOnly,verify_helpers
    verify_helpers(spec)
    service=NativeService(spec['config'],spec) if spec['arm']=='native' else LiveSpatialService(spec['config'],production_mode=True)
    server=LiveSpatialMCPServer(ReadOnly(service,spec),'engineering')
    for line in sys.stdin:
        if len(line)>1024*1024:raise ValueError('stdio_request_budget')
        result=server.handle_jsonrpc_message(json.loads(line))
        if result is not None:print(json.dumps(result,ensure_ascii=False,allow_nan=False),flush=True)


if __name__=='__main__':main(sys.argv[1])
