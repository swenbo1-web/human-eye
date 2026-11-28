"""Wire the installed product's normal stdio server to one owned Blender instance."""
import hashlib
import json
from pathlib import Path
import sys
import time

def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2), encoding='utf8')

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

if __name__ == '__main__':
    site, blender, slot = map(Path, sys.argv[1:])
    sys.path.insert(0, str(site.resolve()))
    from human_eye_plugin.blender_process import BlenderProcessHost
    from human_eye_plugin.live_service import LiveSpatialService
    from human_eye_plugin.live_spatial_mcp import run_stdio_mcp_server
    from human_eye_plugin.runtime_identity import runtime_identity
    fixture = slot / 'cube.blend'
    ident = runtime_identity()
    source = ident['source_sha256']
    config = slot/'config.json'
    save(config, dict(schema_version='1.0', enabled=True, project_root=str(slot.resolve()),
        state_file='state.json', audit_file='audit.jsonl', request_budget_s=30,
        expected_identity={'source_sha256': source}))
    boot = time.perf_counter_ns()
    with BlenderProcessHost(blender, fixture, timeout=25, startup_timeout=45) as host:
        ready = time.perf_counter_ns()
        service = LiveSpatialService(config, host=host, production_mode=True)
        save(slot/'ready.json', dict(pid=host._process.pid, startup_ns=ready-boot,
            source_sha256=source, source_files=len(ident['source_files']),
            source_kind=ident['source_kind'], fixture_before=digest(fixture)))
        def finish():
            try:
                # Post-business truth read. It cannot warm any measured request.
                capture = host.capture_scene()
                save(slot/'post_capture.json', capture)
            finally:
                host.close()
                save(slot/'closed.json', dict(pid=host._process.pid, blender_exit=host._process.returncode,
                    fixture_after=digest(fixture)))
        service.close = finish
        run_stdio_mcp_server(service)
