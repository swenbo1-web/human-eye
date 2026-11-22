"""Replay archived non-target and missing-provenance cases through installed stdio."""

from contextlib import contextmanager
from pathlib import Path
from runpy import run_path
import sys
import time


NS = Path(__file__).resolve().parent
BASE = NS.parent/'m1_region_task_first_packet_projection_001'
ROOT = Path('D:/he_m1_region_task_witness_image_path_001')
OLD_BINDING = BASE/'install/PRODUCT_RUN_BINDING.json'
NEW_BINDING = NS/'install/PRODUCT_RUN_BINDING.json'
prior = run_path(str(BASE/'qualification.py'))
launch = prior['launch']
launch.EXTERNAL = ROOT
require, save, read = launch.require, launch.save, launch.read


@contextmanager
def stock(root,binding,slot,*,isolated=False,extras=(),request_budget_s=30):
    require(not extras and request_budget_s==30,'fixed_compatibility_worker_fixture_only')
    root.mkdir(parents=True,exist_ok=False)
    args = [sys.executable,'-IB','-X','utf8',str(Path(__file__).resolve()),'--worker',
            str(root/'worker'),str(binding),'isolated' if isolated else 'standard']
    process = launch.transport().StdioClient(args,root,root/'wire',time.perf_counter_ns()+70_000_000_000)
    try:
        yield process
    finally:
        close = process.finish()
        save(root/'STOCK_CLOSE.json',close)
        eof = read(root/'worker/EOF.json')
        require(close['confirmed'] and close['exit_code']==0 and close['process_handle_closed']
                and eof['closed'] and eof['host_attempts']==eof['new_rasters']==0,
                'actual_compatibility_stdio_EOF_not_confirmed')


def main():
    keys = ('discover_full','discover_brief','discover_omitted','discover_no_image','no_image_brief',
            'source_region_full','source_region_no_image','source_region_unknown','active_other',
            'bad_png','invalid_detail','invalid_objects','stale_region','after_stale','after_invalid')
    launch.stock = stock
    root = ROOT/'compatibility'
    root.mkdir(parents=True,exist_ok=False)
    cells = {}
    for title,isolation in (('standard',False),('isolated',True)):
        for arm,binding in (('baseline',OLD_BINDING),('candidate',NEW_BINDING)):
            cells[title,arm] = prior['run_cell'](root/(title+'_'+arm),binding,'P3',keys,isolated=isolation)
    for title in ('standard','isolated'):
        old,new = (cells[title,arm] for arm in ('baseline','candidate'))
        require(old['catalogue']==new['catalogue'] and old['service_arguments']==new['service_arguments']
                and old['producers']==new['producers'],'untargeted_directory_or_input_contract_changed/' + title)
        for key in keys:
            a,b = (prior['without_trace_ids'](cell['calls'][key]['result']) for cell in (old,new))
            require(a==b,'untargeted_result_or_missing_provenance_changed/' + title + '/' + key)
            require('witness_image_paths' not in prior['payload'](new,key),
                    'archived_reply_with_no_current_producer_improperly_gained_paths/' + title + '/' + key)
    save(root/'RESULT.json',{'passed':True,'cells':4,'baseline_candidate_comparisons':len(keys)*2,
         'compatibility_cases':list(keys),'actual_closed':4,'model_starts':0,'Blender_starts':0,'new_rasters':0,
         'scope':'real installed production stdio; archived producers without current ReadContext authority'})
    print('Compatibility passed',len(keys)*2,'actual comparisons',flush=True)


if __name__=='__main__':
    require(sys.flags.isolated and sys.dont_write_bytecode,'fixed_isolated_interpreter_required')
    if len(sys.argv)==5 and sys.argv[1]=='--worker':
        raise SystemExit(launch.worker(Path(sys.argv[2]),Path(sys.argv[3]),'P3',sys.argv[4]=='isolated',30,()))
    main()
