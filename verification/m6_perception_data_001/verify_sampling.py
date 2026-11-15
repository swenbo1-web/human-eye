"""Independently check saved row endpoints and lineage without resampling."""

from collections import Counter, defaultdict
from pathlib import Path
import sys
import time
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import read, write
import numpy as np
from sampler import PairedStateSampler


def main():
    started, cpu = time.perf_counter(), time.process_time()
    dataset, audit = read("DATASET_INDEX.json"), read("SAMPLER_AUDIT.json")
    sampler = PairedStateSampler(dataset)
    membership = {row["id"]:row for row in read("SPLIT.json")["mesh_membership"]}
    with np.load(HERE / audit["index"]["path"]) as index:
        rows = index["rows"].reshape(-1)
    failures, qualified_centers, conditional_counts = [], {}, defaultdict(Counter)
    for index in np.unique(rows["pair_index"]):
        pair = dataset["pairs"][index]
        selected = rows[rows["pair_index"] == index]
        source = membership[pair["source_id"]]
        expected_normal = sampler.observation_index[pair["normal_observation_id"]]
        expected_damaged = sampler.observation_index[pair["damaged_observation_id"]]
        expected = np.where(selected["state"] == 0,expected_normal,expected_damaged)
        passed = (source["split"] == "development" and source["group"] in {"horse_transfer","face_transfer"}
                  and np.array_equal(expected,selected["observation_index"]))
        if not passed:
            failures.append(pair["id"])
        key = "|".join((pair["mesh_id"],pair["pose_id"],pair["roi_id"],str(pair["center_source_id"])))
        qualified_centers[key] = qualified_centers.get(key,0)+len(selected)//2
    # Child exposures are conditional on the number of draws of their exact parent path.
    for event in rows[::2]:
        pair = dataset["pairs"][event["pair_index"]]
        parent = []
        for field in ("group","mesh_id","pose_id","roi_id","combo_id"):
            conditional_counts["|".join(parent)][str(pair[field])] += 1
            parent.append(str(pair[field]))
    conditional = [dict(parent=parent, parent_pair_events=sum(children.values()),
                        children=[dict(id=key, pair_events=value, actual_conditional_probability=value/sum(children.values()),
                                       expected_conditional_probability=1/len(children)) for key,value in sorted(children.items())])
                   for parent,children in sorted(conditional_counts.items())]
    write("SAMPLER_VERIFY.json",dict(status="passed" if not failures else "failed", failures=failures,
        independent_lineage_endpoint_rows_checked=len(rows),validation_rows=0 if not failures else None,
        qualified_center_pair_events=qualified_centers, conditional_exposure=conditional,
        current_sampler_guards="unique observation and ROI/combo IDs, immutable SPLIT membership, pair endpoint fields, SHA/count of F mappings",
        original_simulation_source="private/recovery/sampler_simulated.py", post_review_hardening_changed_rng=False,
        normal_storage_field_clarification="SAMPLER_AUDIT independent_normal_storage is distinct physical normal observation storage, no statistical independence claim",
        RNG="NumPy default_rng PCG64 seed1729", resampling_runs=0, model_forwards=0, training=0,
        wall_s_before_write=time.perf_counter()-started,cpu_s_before_write=time.process_time()-cpu))
    print("saved index verified",len(rows),"failures",len(failures),flush=True)


if __name__ == "__main__":
    main()
