"""Resolve a versioned region reference to its saved current source vertices."""

import argparse
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import numpy as np
from region_common import checked_identity, read_json, reference_for, resolve_path, source_ids_digest


def resolve_region(reference, include_geometry=True, reference_index=None):
    if reference_index is None:
        reports = read_json("REGION_REPORTS.json")
        checked_identity(reports["reference_index"]["path"], reports["reference_index"]["sha256"])
        index = read_json(reports["reference_index"]["path"])
    else:
        # Batch verification supplies an already hash-checked index once.
        index = reference_index
    if reference not in index["regions"]:
        raise KeyError("unknown_region_reference")
    record = index["regions"][reference]
    if reference_for(record["identity"]) != reference:
        raise ValueError("region_reference_identity_mismatch")
    checked_identity(record["detail"]["path"], record["detail"]["sha256"])
    with np.load(resolve_path(record["detail"]["path"]), allow_pickle=False) as saved:
        ids = saved["source_ids"].copy()
        if source_ids_digest(ids) != record["identity"]["region_source_ids_sha256"]:
            raise ValueError("region_source_ID_identity_mismatch")
        result = {"reference": reference, "identity": record["identity"], "facts": record["facts"],
                  "source_ids": ids.tolist(), "geometry_payload": record["detail"]}
        if include_geometry:
            result.update(current_positions_native=saved["current_positions_native"].tolist(),
                          lumped_area_native=saved["area"].tolist(),
                          model_scores=saved["scores"].tolist(),
                          model_score_available=saved["valid_mask"].astype(bool).tolist())
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("reference")
    parser.add_argument("--metadata-only", action="store_true")
    args = parser.parse_args()
    print(json.dumps(resolve_region(args.reference, not args.metadata_only), ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
