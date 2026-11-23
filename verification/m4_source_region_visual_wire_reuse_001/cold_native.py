"""The prior cold native launcher with this run's worker path and read-only Python cache."""
import os
from pathlib import Path
from runpy import run_path
import sys
import time


HERE = Path(__file__).resolve().parent
PRIOR = HERE.parent/'m4_source_region_selective_visual_capture_001'
old = run_path(str(PRIOR/'cold_native.py'))
RETAINED = old['RETAINED']
METER = old['METER']
retained = old['retained']
retained['__file__'] = str(Path(__file__).resolve())
NativeSession = retained['NativeSession']


if __name__=='__main__':
    sys.dont_write_bytecode = True
    position = sys.argv.index('--')
    args = sys.argv[position+1:]
    if len(args)!=2 or args[0]!='--worker':
        raise ValueError('owned_worker_entry_required')
    path = Path(args[1]).resolve(strict=True)
    config = retained['load'](path)
    if 'qa_vertex_patch' in config or config['max_calls']!=3 or path.parent.name!='native':
        raise ValueError('read_only_two_calls_then_truth_required')
    retained['save'](path.parent/'COLD_POLICY.json',{
        'guard_scope':'loaded scene RNA names/IDs/frame/unit/visibility/raw transforms and len-only original mesh counts',
        'geometry_array_reads_in_guards':0,'evaluated_depsgraph_or_to_mesh_in_guards':0,
        'pid':os.getpid(),'started_ns':time.perf_counter_ns(),
    })
    retained['worker'](path)
