"""Pinned common experimental stdio adapter; no default-app activation."""
import json
from pathlib import Path
import sys
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1];sys.path.append(str(ROOT))


def main(spec_path):
    spec=json.loads(Path(spec_path).read_text())
    if spec['arm'] not in ('native','he'):raise ValueError('arm')
    qualification='qualification_registration' in spec
    if qualification:
        from verification.engineering_qualification import admit,BUILD
        admit(spec)
        import hashlib
        raw=Path(spec['config']).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=spec['config_sha256']:raise ValueError('qualification_config_changed')
        config=json.loads(raw)
        if (config.get('expected_identity',{}).get('source_sha256')!=BUILD
                or config.get('structure_region_mode')!='summary_v1'
                or config.get('structure_patch_mode')!='nonplanar_dense_v1'
                or config.get('blender',{}).get('port')!=spec['port'] or spec['port']==9876
                or config.get('blender',{}).get('host')!=spec['host'] or spec['host']!='127.0.0.1'):
            raise ValueError('qualification_config_scope')
    elif spec['arm']=='he':
        gate=Path(spec['he_gate_file']);registration=json.loads(gate.read_text())
        if registration.get('new_HE_trials_permitted') is not True:raise ValueError('HE_comparability_not_registered')
    from verification.engineering_task_contract import bootstrap
    if qualification:bootstrap(spec['entry'],baseline='region_v3')
    else:bootstrap(spec['entry'])
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
