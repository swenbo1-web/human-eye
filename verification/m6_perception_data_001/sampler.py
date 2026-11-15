"""Hierarchically uniform development pair sampler with exact equal state exposure."""

from pathlib import Path
import sys
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import read
import hashlib
import numpy as np

ROW_DTYPE = np.dtype([("pair_index", "<u2"), ("observation_index", "<u2"), ("F_row", "<u2"),
                      ("source_vertex_id", "<i4"), ("pair_event_id", "<u4"), ("state", "u1")])


class PairedStateSampler:
    def __init__(self, dataset=None, seed=1729):
        self.dataset = read("DATASET_INDEX.json") if dataset is None else dataset
        self.rng = np.random.default_rng(seed)
        self.observation_index = {row["id"]: index for index, row in enumerate(self.dataset["observations"])}
        if len(self.observation_index) != len(self.dataset["observations"]):
            raise ValueError("duplicate_observation_ID")
        self._validate_pairs()
        self.tree = {}
        self.mapping = {}
        self.mapping_sha256 = {}
        self.pairs = self.dataset["pairs"]
        for index, pair in enumerate(self.pairs):
            if pair["split"] != "development" or not pair["usable_for_training"]:
                continue
            node = self.tree
            for key in ("group", "mesh_id", "pose_id", "roi_id"):
                node = node.setdefault(pair[key], {})
            if pair["combo_id"] in node:
                raise ValueError("duplicate_ROI_combo_ID")
            node[pair["combo_id"]] = index
            if pair["roi_id"] not in self.mapping:
                path = HERE / pair["region_mapping"]
                if hashlib.sha256(path.read_bytes()).hexdigest() != pair["mapping_sha256"]:
                    raise ValueError("region_mapping_identity_changed")
                self.mapping[pair["roi_id"]] = np.load(path, allow_pickle=False)
                self.mapping_sha256[pair["roi_id"]] = pair["mapping_sha256"]
            if self.mapping_sha256[pair["roi_id"]] != pair["mapping_sha256"]:
                raise ValueError("pair_region_identity_mismatch")
            if len(self.mapping[pair["roi_id"]]) != pair["F_count"]:
                raise ValueError("F_mapping_count_mismatch")
        if len(self.tree) != 2:
            raise ValueError("both_development_families_required")
        self.event_id = 0

    def _validate_pairs(self):
        membership = {row["id"]: row for row in read("SPLIT.json")["mesh_membership"]}
        if len({pair["id"] for pair in self.dataset["pairs"]}) != len(self.dataset["pairs"]):
            raise ValueError("duplicate_pair_ID")
        for pair in self.dataset["pairs"]:
            source = membership[pair["source_id"]]
            if source["split"] != pair["split"] or source["group"] != pair["group"] or source["mesh_id"] != pair["mesh_id"]:
                raise ValueError("pair_lineage_mismatch")
            for state in ("normal", "damaged"):
                observation = self.dataset["observations"][self.observation_index[pair[state + "_observation_id"]]]
                fields = ("source_id", "mesh_id", "pose_id", "roi_id", "group", "split")
                if observation["state"] != state or any(observation[key] != pair[key] for key in fields):
                    raise ValueError("pair_endpoint_mismatch")
                if observation["input"]["region_mapping"] != pair["region_mapping"]:
                    raise ValueError("pair_endpoint_mapping_mismatch")
                if pair["usable_for_training"] and not observation["usable_for_training"]:
                    raise ValueError("unusable_pair_endpoint")

    def _choose(self, node):
        keys = sorted(node)
        return node[keys[int(self.rng.integers(len(keys)))]]

    def sample_step(self, pair_events=512):
        rows = np.empty(pair_events * 2, dtype=ROW_DTYPE)
        for event in range(pair_events):
            node = self.tree
            for _ in range(5):
                node = self._choose(node)
            index = node
            pair = self.pairs[index]
            mapping = self.mapping[pair["roi_id"]]
            F_row = int(self.rng.integers(len(mapping)))
            swap = int(self.rng.integers(2))
            for offset, state in enumerate((swap, 1 - swap)):
                observation_id = pair["damaged_observation_id"] if state else pair["normal_observation_id"]
                rows[2 * event + offset] = (index, self.observation_index[observation_id], F_row,
                                            int(mapping[F_row]), self.event_id, state)
            self.event_id += 1
        return rows

    def pair_probabilities(self):
        result = {}
        def visit(node, probability):
            child_probability = probability / len(node)
            for child in node.values():
                if isinstance(child, dict):
                    visit(child, child_probability)
                else:
                    result[int(child)] = child_probability
        visit(self.tree, 1.)
        return result
