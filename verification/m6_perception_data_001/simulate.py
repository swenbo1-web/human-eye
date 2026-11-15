"""Save the single frozen 1200x1024 index simulation without model execution."""

from collections import Counter, defaultdict
from pathlib import Path
import sys
import time
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import read, write, identity
import numpy as np
from sampler import PairedStateSampler, ROW_DTYPE
from data_io import read_supervision


def main():
    started, cpu = time.perf_counter(), time.process_time()
    output = HERE / "private/sampling_index_1200x1024.npz"
    if output.exists():
        raise RuntimeError("fixed_sampling_simulation_already_exists")
    dataset, plan = read("DATASET_INDEX.json"), read("PLAN.json")
    sampler = PairedStateSampler(dataset, seed=plan["sampling"]["seed"])
    rows = np.empty((1200,1024), dtype=ROW_DTYPE)
    for step in range(1200):
        rows[step] = sampler.sample_step()
    np.savez_compressed(output, rows=rows)
    flat, pairs = rows.reshape(-1), dataset["pairs"]
    events = flat[::2]
    state_counts = np.bincount(flat["state"], minlength=2)
    actual_pairs = Counter(int(index) for index in events["pair_index"])
    probabilities = sampler.pair_probabilities()
    observations = dataset["observations"]
    masks = {}
    expected_positive = 0.
    weight_rows, expected_normal = [], defaultdict(float)
    for index, probability in probabilities.items():
        pair = pairs[index]
        observation = observations[sampler.observation_index[pair["damaged_observation_id"]]]
        mask = read_supervision(observation)["changed_mask"]
        masks[index] = mask
        expected_positive += probability * .5 * float(mask.mean())
        expected_normal[pair["normal_observation_id"]] += probability * .5
        weight_rows.append(dict(pair_id=pair["id"], probability_per_pair_event=probability,
                               normal_joint_pair_state_probability=probability/2,
                               damaged_joint_pair_state_probability=probability/2,
                               joint_probability_per_state_F_point=probability/(2*pair["F_count"]),
                               actual_pair_events=actual_pairs[index], actual_pair_event_probability=actual_pairs[index]/len(events)))
    actual_positive = sum(int(masks[int(row["pair_index"])][int(row["F_row"])]) for row in flat if row["state"] == 1)
    exposure = {}
    for field in ("group", "mesh_id", "pose_id", "roi_id", "center_source_id"):
        expected, actual = defaultdict(float), Counter()
        for index, probability in probabilities.items():
            expected[str(pairs[index][field])] += probability
        for index, count in actual_pairs.items():
            actual[str(pairs[index][field])] += count
        exposure[field] = [dict(id=key, expected_probability=value, actual_pair_events=actual[key],
                               actual_probability=actual[key]/len(events), absolute_gap=abs(actual[key]/len(events)-value))
                           for key, value in sorted(expected.items())]
    event_a, event_b = flat[::2], flat[1::2]
    pairing_checks = {field: bool(np.array_equal(event_a[field], event_b[field]))
                      for field in ("pair_index", "F_row", "source_vertex_id", "pair_event_id")}
    pairing_checks["opposite_states"] = bool(np.all(event_a["state"] + event_b["state"] == 1))
    pairing_checks["exact512_normal512_damaged_every_step"] = bool(np.all(np.sum(rows["state"] == 0, axis=1) == 512))
    validation_rows = sum(int(count) * 2 for index, count in actual_pairs.items() if pairs[index]["split"] != "development")
    mapping_correct = all(np.array_equal(flat["source_vertex_id"][flat["pair_index"] == index],
                                         sampler.mapping[pairs[index]["roi_id"]][flat["F_row"][flat["pair_index"] == index]])
                          for index in actual_pairs)
    pairing_checks["source_mapping_exact"] = mapping_correct
    report = dict(cycle_id=plan["cycle_id"], status="passed" if all(pairing_checks.values()) and validation_rows == 0 else "failed",
                  seed=1729, steps=1200, rows_per_step=1024, pair_events=len(events), rows=len(flat),
                  normal_rows=int(state_counts[0]), damaged_rows=int(state_counts[1]), validation_rows=validation_rows,
                  checks=pairing_checks, index=identity(output), expected_state_weights=dict(normal=.5, damaged=.5),
                  actual_state_weights=dict(normal=float(state_counts[0]/len(flat)), damaged=float(state_counts[1]/len(flat))),
                  pair_weights=weight_rows, normal_observation_expected_weights=dict(expected_normal),
                  exposure=exposure, expected_positive_label_fraction=expected_positive, actual_positive_labels=actual_positive,
                  actual_positive_label_fraction=actual_positive/len(flat),
                  independent_normal_storage=len(expected_normal), logical_normal_exposures=int(state_counts[0]),
                  storage_independence="repeated normal observations are paired exposures, no additional independent data",
                  sampling_fluctuations="hierarchical uniform draws, finite source counts recorded without forced equality",
                  label_access="sampler reads no labels. Simulation audit reads only development supervision after index draws",
                  normalization="future development-only, not fitted", pos_weight="future development-only, not fitted",
                  training_runs=0, model_forwards=0, wall_s_before_write=time.perf_counter()-started, cpu_s_before_write=time.process_time()-cpu)
    write("SAMPLER_AUDIT.json", report)
    print(report["status"], report["normal_rows"], report["damaged_rows"], "validation", validation_rows, flush=True)


if __name__ == "__main__":
    main()
