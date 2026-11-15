"""Create eight identical current-data tasks with private scoring material."""

from pathlib import Path
import sys
import time
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from common import identity,read,write
import numpy as np
from interfaces import fixed_target_ids


def main():
    started,cpu=time.perf_counter(),time.process_time()
    if (HERE/"CONSUMER_INPUTS.json").exists():
        raise RuntimeError("fixed_consumer_tasks_already_prepared")
    index={row["alias"]:row for row in read("INPUT_INDEX.json")["cases"]}
    truth={row["alias"]:row for row in read("SUPERVISION_INDEX.json")["observations"]}
    tasks=read("TASKS.json")["tasks"]
    records=[]
    scoring=[]
    for task in tasks:
        case=index[task["geometry_alias"]]
        with np.load(HERE/case["input"]["path"]) as package:
            vertices,faces,F=package["vertices"],package["faces"],package["F_source_ids"]
        if task["entrypoint"]=="focus":
            target=fixed_target_ids(faces,F,64)
            protected=np.setdiff1d(F,target)
        else:
            target=np.empty(0,dtype=np.int64)
            protected=np.empty(0,dtype=np.int64)
        directory=HERE/"private/consumer_cases"/task["task_id"]
        directory.mkdir(parents=True,exist_ok=False)
        path=directory/"input.npz"
        np.savez_compressed(path,vertices=vertices,faces=faces,F_ids=F,target_ids=target,protected_ids=protected)
        write(directory.relative_to(HERE)/"task.json",task)
        with np.load(HERE/truth[task["geometry_alias"]]["path"]) as labels:
            mask=labels["mask"]
        scoring_dir=HERE/"private/scoring"
        scoring_dir.mkdir(parents=True,exist_ok=True)
        np.savez_compressed(scoring_dir/(task["task_id"]+".npz"),mask=mask,F_source_ids=F,target_ids=target,protected_ids=protected)
        scoring.append(dict(task_id=task["task_id"],state=case["state"],entrypoint=task["entrypoint"],geometry_alias=case["alias"],
                            truth_file="private/scoring/"+task["task_id"]+".npz"))
        records.append(dict(task_id=task["task_id"],entrypoint=task["entrypoint"],current_input=identity(path),
                            task_packet=identity(directory/"task.json"),target_points=len(target),protected_points=len(protected),
                            all_routes_same_current_bytes=True))
    write("private/scoring/TASK_TRUTH.json",dict(cases=scoring,consumer_access=False))
    write("CONSUMER_INPUTS.json",dict(tasks=records,task_count=8,maximum_routes=24,
        visible_array_fields=["vertices","faces","F_ids","target_ids","protected_ids"],
        original_names_or_state_in_visible_payload=False,supervision_visible=False,
        wall_s_before_write=time.perf_counter()-started,cpu_s_before_write=time.process_time()-cpu))
    print("eight frozen tasks prepared",flush=True)


if __name__=="__main__":
    main()
