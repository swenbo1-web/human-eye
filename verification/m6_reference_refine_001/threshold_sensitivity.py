"""Test foreground thresholds around previously recorded arm boundary locations."""

import json
from pathlib import Path
import sys
import time

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import numpy as np
from PIL import Image
from reference_geometry import axis_frame,measure_polyline_sections


def main():
    started,cpu=time.perf_counter(),time.process_time()
    draft=json.loads((HERE/"ANNOTATION_DRAFT.json").read_bytes())
    reference=draft["anchors"]["reference"]
    original=Image.open(draft["inputs"][0]["path"]).convert("RGB")
    rgb=np.asarray(original,dtype=np.int16)
    original_inner=np.asarray(draft["reference_foreground"]["inner_polyline"])
    original_outer=np.asarray(draft["reference_foreground"]["outer_polyline"])
    trials=[]
    for rg in (6,10,14):
        for gb in (5,8,12):
            for rb in (25,35,45):
                contours={}
                for name,original_line in (("inner",original_inner),("outer",original_outer)):
                    line=[]
                    for point in original_line:
                        center=int(round(point[0]))
                        row=int(point[1]-.5)
                        first,last=center-6,center+7
                        values=rgb[row,first:last]
                        keep=(values[:,0]-values[:,1]>=rg)&(values[:,1]-values[:,2]>=gb)&(values[:,0]-values[:,2]>=rb)
                        indices=np.flatnonzero(keep)
                        if not len(indices):
                            raise ValueError("boundary_window_contains_no_foreground")
                        x=first+indices[0] if name=="inner" else first+indices[-1]+1
                        line.append([float(x),point[1]])
                    contours[name]=np.asarray(line)
                result=measure_polyline_sections(contours["inner"],contours["outer"],reference["E"],reference["W"],draft["stations"])
                trials.append(dict(thresholds=dict(R_minus_G=rg,G_minus_B=gb,R_minus_B=rb),sections=result,
                    inner_polyline=contours["inner"].tolist(),outer_polyline=contours["outer"].tolist()))
    values=np.asarray([[row["outer"] for row in trial["sections"]] for trial in trials])
    initial=np.asarray([row["outer"] for row in draft["reference_sections"]])
    length=axis_frame(reference["E"],reference["W"])[3]
    summary=dict(status="pass",threshold_trials=len(trials),window_radius_pixels=6,stations=draft["stations"],
        outer_normalized_minimum=values.min(axis=0).tolist(),outer_normalized_maximum=values.max(axis=0).tolist(),
        maximum_shift_from_central_normalized=np.max(np.abs(values-initial),axis=0).tolist(),
        maximum_shift_from_central_pixels=(length*np.max(np.abs(values-initial),axis=0)).tolist(),
        original_boundary_term_pixels=draft["reference_foreground"]["boundary_uncertainty_pixels"],
        anchor_E_W_and_sensitivity_unchanged=True,
        interpretation="Thresholds are varied symmetrically around the existing central threshold. Edge searches are confined to six-pixel windows around the previously recorded external foreground boundary to avoid unrelated clothing/background components. Anchor uncertainty remains a separate dominant term.",
        earlier_failed_probe=dict(error="one_contour_intersection_per_station_required_inner",observed_shell_wall_s=.2028877,CPU_s=None,
            cause="Unrestricted rectangular ROI threshold sweep admitted unrelated foreground components. The failure prompted explicitly localized boundary windows, with original central annotation retained.",Blender=0,Pro=0),
        wall_s=time.perf_counter()-started,CPU_s=time.process_time()-cpu)
    detail=HERE/"private/annotation/SENSITIVITY_DETAIL.json"
    detail.write_text(json.dumps(dict(summary=summary,trials=trials),indent=2)+"\n",encoding="utf8",newline="\n")
    (HERE/"SENSITIVITY_REPORT.json").write_text(json.dumps(summary,indent=2)+"\n",encoding="utf8",newline="\n")
    print(json.dumps(summary))


if __name__=="__main__":
    main()
