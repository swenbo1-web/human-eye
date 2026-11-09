"""Compose existing owned host/service/MCP APIs for an isolated test copy."""
import argparse
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from human_eye_plugin.blender_process import BlenderProcessHost
from human_eye_plugin.live_service import LiveSpatialService
from human_eye_plugin.live_spatial_mcp import _configure_utf8_stdio,run_stdio_mcp_server

def main(argv=None):
    _configure_utf8_stdio()
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',required=True)
    parser.add_argument('--blender',required=True)
    parser.add_argument('--scene',required=True)
    parser.add_argument('--timeout-s',type=float,default=10.)
    parser.add_argument('--spatial-task-only',action='store_true')
    args=parser.parse_args(argv)
    with BlenderProcessHost(args.blender,args.scene,timeout=args.timeout_s) as host:
        service=LiveSpatialService(args.config,host=host,production_mode=True)
        run_stdio_mcp_server(service,**({'spatial_task_only':True} if args.spatial_task_only else {}))
    return 0

if __name__=='__main__':raise SystemExit(main())
