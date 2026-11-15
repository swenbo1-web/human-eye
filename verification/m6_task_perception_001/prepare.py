"""Reuse verified DATA001 through its current-only reader and blind observation IDs."""

import importlib.util
from pathlib import Path
import sys
import time
HERE = Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from common import DATA, identity, read, write, measure
import numpy as np


def main():
    started,cpu=time.perf_counter(),time.process_time()
    if (HERE/"INPUT_INDEX.json").exists():
        raise RuntimeError("prepared_input_index_already_exists")
    plan=read("PLAN.json")
    dataset=__import__("json").loads((DATA/"DATASET_INDEX.json").read_bytes())
    source_audit=__import__("json").loads((DATA/"SAMPLER_AUDIT.json").read_bytes())
    probabilities={row["pair_id"]:row["probability_per_pair_event"] for row in source_audit["pair_weights"]}
    spec=importlib.util.spec_from_file_location("_data001_current_reader",DATA/"data_io.py")
    reader=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reader)
    aliases=read("ALIASES.json")["observation_aliases"]
    roi_aliases=read("ALIASES.json")["roi_aliases"]
    for directory in ("current","supervision"):
        (HERE/"private"/directory).mkdir(parents=True,exist_ok=True)
    rows,labels,timings=[],[],{}
    for index,observation in enumerate(dataset["observations"]):
        alias=aliases[observation["id"]]
        local={}
        with measure(local,"data001_current_reader"):
            current=reader.read_current(observation)
        path=HERE/"private/current"/(alias+".npz")
        with measure(local,"current_packet_write"):
            np.savez_compressed(path,vertices=current["vertices"],faces=current["faces"],F_source_ids=current["region_source_ids"])
        rows.append(dict(alias=alias,original_index=index,roi_alias=roi_aliases[observation["roi_id"]],split=observation["split"],
                         state=observation["state"],valid_for_learning=observation["usable_for_training"],
                         input=identity(path),timings=local))
        # Supervision uses an entirely separate file and is never loaded by feature preparation.
        with np.load(DATA/observation["supervision"]) as supervision:
            mask=supervision["changed_mask"].copy()
            delta=supervision["actual_delta"].copy()
        target=HERE/"private/supervision"/(alias+".npz")
        np.savez_compressed(target,mask=mask,actual_delta=delta)
        labels.append(dict(alias=alias,path=target.relative_to(HERE).as_posix(),split=observation["split"],state=observation["state"]))
        for name,value in local.items():
            item=timings.setdefault(name,dict(wall_s=0.,cpu_s=0.,calls=0))
            for key in item:
                item[key]+=value[key]
    pairs=[]
    for index,pair in enumerate(dataset["pairs"]):
        pairs.append(dict(index=index,development_group=pair["group"],mesh=pair["mesh_id"],pose=pair["pose_id"],roi_alias=roi_aliases[pair["roi_id"]],
                          normal_alias=aliases[pair["normal_observation_id"]],damaged_alias=aliases[pair["damaged_observation_id"]],
                          mask_path="private/supervision/"+aliases[pair["damaged_observation_id"]]+".npz",split=pair["split"],
                          usable_for_training=pair["usable_for_training"],probability_per_pair_event=probabilities.get(pair["id"],0.)))
    write("INPUT_INDEX.json",dict(cases=rows,current_packet_fields=["vertices","faces","F_source_ids"],
        reused_reader=identity(DATA/"data_io.py"),old_dataset_identity=identity(DATA/"DATASET_INDEX.json"),
        source_geometry_changed=False,download_bytes=0,wall_s_before_write=time.perf_counter()-started,cpu_s_before_write=time.process_time()-cpu,timings=timings))
    write("SUPERVISION_INDEX.json",dict(observations=labels,pairs=pairs,used_for="training and scoring only",validation_labels_for_training=0))
    with np.load(DATA/"private/sampling_index_1200x1024.npz") as saved:
        np.savez_compressed(HERE/"TRAINING_INDICES.npz",rows=saved["rows"])
    # The index is private and must stay outside Git alongside all other arrays.
    (HERE/"TRAINING_INDICES.npz").replace(HERE/"private/TRAINING_INDICES.npz")
    write("TRAINING_INDEX_IDENTITY.json",dict(reused=identity(DATA/"private/sampling_index_1200x1024.npz"),copied=identity(HERE/"private/TRAINING_INDICES.npz"),
        row_shape=[1200,1024],pair_events=614400,normal_rows=614400,damaged_rows=614400,seed=1729,validation_rows=0))
    print("prepared",len(rows),"current-only packets",len(pairs),"pair identities",flush=True)


if __name__=="__main__":
    main()
