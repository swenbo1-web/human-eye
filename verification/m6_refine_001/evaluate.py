"""Evaluate independent Blender readback against a fixed refinement specification."""

import argparse
import json
from pathlib import Path
import sys
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import numpy as np
from quality import evaluate_arrays


def evaluate_packets(before_path, after_path, initial_path, spec_path, *, before_state_path=None,
                     after_state_path=None, deadline=None, check_intersections=True):
    with np.load(before_path,allow_pickle=False) as package:
        before={key:package[key] for key in package.files}
    with np.load(after_path,allow_pickle=False) as package:
        after={key:package[key] for key in package.files}
    with np.load(initial_path,allow_pickle=False) as package:
        fixed={key:package[key] for key in package.files}
    spec=json.loads(Path(spec_path).read_bytes())
    before_state=json.loads(Path(before_state_path).read_bytes()) if before_state_path else None
    after_state=json.loads(Path(after_state_path).read_bytes()) if after_state_path else None
    return evaluate_arrays(before["vertices_local"],after["vertices_local"],before["vertices"],after["vertices"],before["faces"],
        fixed["F_source_ids"],fixed["I_ids"],fixed["C_ids"],int(spec["center_source_id"]),fixed["n0"],float(spec["h"]),float(spec["ell"]),spec,
        after_faces=after["faces"],before_poly_offsets=before.get("poly_offsets"),before_poly_vertices=before.get("poly_vertices"),
        after_poly_offsets=after.get("poly_offsets"),after_poly_vertices=after.get("poly_vertices"),
        before_polygon_ids=before.get("triangle_polygon_ids"),after_polygon_ids=after.get("triangle_polygon_ids"),
        before_matrix=before.get("matrix_world"),after_matrix=after.get("matrix_world"),before_state=before_state,after_state=after_state,
        before_source_ids=before.get("source_ids"),after_source_ids=after.get("source_ids"),
        unreachable_ids=fixed["I_ids"][~np.isfinite(fixed["boundary_distance"][fixed["I_ids"]])] if "boundary_distance" in fixed else None,
        deadline=deadline,check_intersections=check_intersections)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--before",type=Path,required=True)
    parser.add_argument("--after",type=Path,required=True)
    parser.add_argument("--initial",type=Path,required=True)
    parser.add_argument("--spec",type=Path,required=True)
    parser.add_argument("--before-state",type=Path)
    parser.add_argument("--after-state",type=Path)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    result=evaluate_packets(args.before,args.after,args.initial,args.spec,before_state_path=args.before_state,after_state_path=args.after_state)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+"\n",encoding="utf8",newline="\n")
    print(json.dumps(dict(status=result["status"],center_over_h=result["displacement"]["center_over_h"],
                         core_median_over_h=result["displacement"]["core_median_over_h"],checks=result["checks"]),ensure_ascii=False))


if __name__=="__main__":
    main()
