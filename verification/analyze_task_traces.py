"""Read task-associated request evidence; never infer absent usage or wall time."""
from pathlib import Path
import argparse
import json
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from human_eye_plugin.task_metrics import summarize_task_run


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('audit',type=Path)
    parser.add_argument('--task-id',required=True)
    parser.add_argument('--task-run-id',required=True)
    parser.add_argument('--duration-ns',type=int)
    parser.add_argument('--request-manifest',type=Path)
    args=parser.parse_args(argv)
    if args.audit.stat().st_size>32*1024*1024:
        raise ValueError('Audit input exceeds the 32MiB reader limit')
    traces=[]
    for line in args.audit.read_text(encoding='utf-8-sig').splitlines():
        row=json.loads(line)
        if not isinstance(row,dict):raise ValueError('Audit rows must be objects')
        trace=row.get('trace') if row.get('event')=='request_trace' else None
        if not isinstance(trace,dict):continue
        context=trace.get('correlation',{})
        if context.get('task_id')==args.task_id and context.get('task_run_id')==args.task_run_id:
            traces.append(trace)
    expected=None
    if args.request_manifest:
        expected=json.loads(args.request_manifest.read_text(encoding='utf-8-sig'))
    summary=summarize_task_run(traces,task_id=args.task_id,task_run_id=args.task_run_id,
        duration_ns=args.duration_ns,expected_request_ids=expected)
    print(json.dumps(summary,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
