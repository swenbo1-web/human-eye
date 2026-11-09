"""Generate only isolated configs/commands for the current common source."""
import argparse
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from human_eye_plugin.runtime_identity import runtime_identity

def prepare(directory,port):
    directory=Path(directory).resolve();directory.mkdir(parents=True,exist_ok=True)
    identity=runtime_identity(mode='live')
    paths={}
    for backend in ('mcp','owned'):
        folder=directory/backend;folder.mkdir(exist_ok=True)
        config={'schema_version':'1.0','enabled':True,'project_root':str(ROOT),
                'state_file':str(folder/'actions.json'),'audit_file':str(folder/'audit.jsonl'),
                'quad_size':64,'max_sessions':4,
                'expected_identity':{key:identity[key] for key in ('source_sha256','build_id','implementation_revision')}}
        if backend=='mcp':config['blender']={'host':'127.0.0.1','port':port,'timeout_s':10.}
        target=folder/'connector.json';target.write_text(json.dumps(config,indent=2)+'\n',encoding='utf8')
        paths[backend]=str(target)
    commands={'source_sha256':identity['source_sha256'],'source_file_count':len(identity['source_files']),
        'project_root':str(ROOT),'mcp_ordinary':[sys.executable,'-B','-m','human_eye_plugin.production_server','--config',paths['mcp']],
        'mcp_narrow':[sys.executable,'-B','-m','human_eye_plugin.production_server','--config',paths['mcp'],'--spatial-task-only'],
        'owned_ordinary':[sys.executable,'-I','-B',str(Path(__file__).with_name('owned_service_stdio.py')),
            '--config',paths['owned'],'--blender','D:/Tools/blender5.2/blender.exe','--scene','ISOLATED_FIXTURE.blend'],
        'owned_narrow_suffix':['--spatial-task-only'],
        'notes':'Run MCP commands with cwd=project_root. Replace owned scene with the generated isolated fixture and use its ready.json port. Blender execution requires the coordinator exclusive window. Regenerate if product source changes.'}
    (directory/'ENTRYPOINTS.json').write_text(json.dumps(commands,indent=2)+'\n',encoding='utf8')
    return paths,commands

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory',required=True)
    source=parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--ready',help='Isolated fixture ready.json supplying port')
    source.add_argument('--port',type=int,help='Explicit isolated fixture port; no server is started')
    args=parser.parse_args()
    port=args.port if args.port is not None else json.loads(Path(args.ready).read_text())['port']
    if type(port) is not int or not 1<=port<=65535:parser.error('port must be 1..65535')
    print(json.dumps(prepare(args.directory,port)[1],indent=2))

if __name__=='__main__':main()
