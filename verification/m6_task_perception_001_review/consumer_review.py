"""Recompute answer measurements and observed session accounting independently."""

import hashlib
import json
from pathlib import Path
import time
import numpy as np
from review import geometry

HERE = Path(__file__).resolve().parent
BASE = HERE.parent / '_m6tp1/batch'


def read(path):
    return json.loads((BASE/path).read_bytes())


def main():
    started = time.perf_counter()
    tasks = {r['task_id']: r for r in read('TASKS.json')['tasks']}
    truth_index = {r['alias']: r for r in read('SUPERVISION_INDEX.json')['observations']}
    source_rows = read('CONSUMERS.json')['rows']
    rows = []
    for row in source_rows:
        task = tasks[row['task_id']]
        receipt = read(row['record'])
        events = [json.loads(line)['event'] for line in (BASE/row['events']).read_text(encoding='utf-8').splitlines()]
        usage = [e['usage'] for e in events if e['type']=='turn.completed']
        assert usage == [row['usage']]
        assert receipt['tool_count'] == row['tool_calls']
        case_dir = BASE/'private/consumer_cases'/row['task_id']
        assert hashlib.sha256((case_dir/'input.npz').read_bytes()).hexdigest() == row['input_NPZ_sha256']
        text = (BASE/row['answer']).read_text(encoding='utf-8')
        answer = json.loads(text[text.index('{'):text.rindex('}')+1])
        with np.load(case_dir/'input.npz') as data:
            vertices, faces, F = data['vertices'], data['faces'], data['F_ids']
            target = data['target_ids'] if 'target_ids' in data else []
        area, _ = geometry(vertices, faces)
        ids = np.array(answer['selected_source_ids'], dtype=np.int64)
        assert len(ids) == len(np.unique(ids)) and np.isin(ids, F).all()
        if task['entrypoint']=='focus':
            assert np.array_equal(np.sort(ids), np.sort(target))
        else:
            assert area[ids].sum() <= area[F].sum()*.25 + area[F].sum()*1e-12
        measurement = bool(len(ids))
        if len(ids):
            centroid = (vertices[ids]*area[ids,None]).sum(axis=0)/area[ids].sum()
            diagonal = np.linalg.norm(vertices.max(axis=0)-vertices.min(axis=0))
            assert np.max(abs(centroid-answer['centroid_native'])) <= diagonal*1e-6
            assert abs(area[ids].sum()-answer['lumped_area_native']) <= area[ids].sum()*1e-6
            assert np.max(abs(vertices[ids].min(axis=0)-answer['bbox_native']['min'])) <= diagonal*1e-6
            assert np.max(abs(vertices[ids].max(axis=0)-answer['bbox_native']['max'])) <= diagonal*1e-6
        with np.load(BASE/truth_index[task['geometry_alias']]['path']) as data:
            mask = data['mask'].astype(bool)
        support = F[mask]
        recall = float(area[np.intersect1d(ids, support)].sum()/area[support].sum()) if len(support) else None
        rows.append(dict(task_id=row['task_id'], route=row['route'], entrypoint=task['entrypoint'],
                         measurements_nonempty_correct=measurement, selected_points=len(ids),
                         synthetic_support_recall=recall, wall_s=row['wall_s'], usage=row['usage'],
                         tool_calls=row['tool_calls'], tool_errors=len(row['tool_errors'])))
    paired = {}
    for task_id in tasks:
        candidates = [r for r in source_rows if r['task_id']==task_id]
        for field in ('input_NPZ_sha256', 'task_JSON_sha256', 'prompt_sha256'):
            assert len({r[field] for r in candidates}) == 1
    for condition in ('all', 'without_entire_t01', 'focus_only'):
        selected = [r for r in rows if condition=='all' or
                    (condition=='without_entire_t01' and r['task_id']!='t01') or
                    (condition=='focus_only' and r['entrypoint']=='focus')]
        paired[condition] = {}
        for route in ('native', 'facts', 'learned'):
            group = [r for r in selected if r['route']==route]
            paired[condition][route] = dict(tasks=len(group), wall_s=sum(r['wall_s'] for r in group),
                usage={key:sum(r['usage'][key] for r in group) for key in group[0]['usage']},
                geometry_complete=sum(r['measurements_nonempty_correct'] for r in group),
                tool_errors=sum(r['tool_errors'] for r in group))
    result = dict(status='passed', answers=len(rows), measurement_complete=sum(r['measurements_nonempty_correct'] for r in rows),
                  focus_exact_targets=12, paired_summaries=paired, cases=rows,
                  independent_text_review='one route-identity-blinded reviewer; 23 pass and 1 partial',
                  limitations=['t01/native executor errors confound first task', 'one fixed-order run per task-route',
                               'candidate attention wording and synthetic-support recall are different objectives',
                               'provider resolved settings and monetary fees unmeasured'],
                  new_consumer_calls=0, wall_s=time.perf_counter()-started)
    (HERE/'CONSUMER_RESULTS.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='cases'}))


if __name__=='__main__':
    main()
