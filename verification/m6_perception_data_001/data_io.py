"""Reconstruct compact current observations with an explicit inference whitelist."""

from pathlib import Path
import sys
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import numpy as np


def read_current(observation):
    entry = observation["input"]
    with np.load(HERE / entry["base_mesh"]) as source:
        vertices = source["vertices"].copy()
        faces = source["faces"].copy()
    source_ids = np.load(HERE / entry["region_mapping"], allow_pickle=False)
    with np.load(HERE / entry["current_local_positions"]) as local:
        vertices[source_ids] = local["positions"]
    # The reconstruction baseline and supervision never appear in this return value.
    return dict(vertices=vertices, faces=faces, region_source_ids=source_ids,
                mesh_id=observation["mesh_id"], pose_id=observation["pose_id"])


def read_supervision(observation):
    """Training/QA-only entry point, separate from current input reconstruction."""
    with np.load(HERE / observation["supervision"]) as data:
        return {name: data[name] for name in data.files}


def main():
    import argparse
    import hashlib
    import json
    from common import read
    parser = argparse.ArgumentParser()
    parser.add_argument("observation_id")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    observation = next(row for row in read("DATASET_INDEX.json")["observations"] if row["id"] == args.observation_id)
    current = read_current(observation)
    if args.output:
        np.savez_compressed(args.output, vertices=current["vertices"], faces=current["faces"], region_source_ids=current["region_source_ids"])
    print(json.dumps(dict(observation_id=args.observation_id, vertices=len(current["vertices"]), triangles=len(current["faces"]),
                          F_points=len(current["region_source_ids"]), current_vertices_sha256=hashlib.sha256(current["vertices"].tobytes()).hexdigest(),
                          returned_fields=list(current)), indent=2))


if __name__ == "__main__":
    main()
