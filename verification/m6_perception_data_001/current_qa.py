"""Current-geometry encoder-neighborhood diagnostics and abnormal-normal audit."""

from pathlib import Path
import sys
import time
HERE = Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from common import read, write
import numpy as np
from data_io import read_current, read_supervision


def main():
    started,cpu=time.perf_counter(),time.process_time()
    dataset=read("DATASET_INDEX.json")
    results=[]
    for observation in dataset["observations"]:
        if observation["state"] != "damaged":
            continue
        current=read_current(observation)
        vertices,faces=current["vertices"],current["faces"]
        center=observation["center_source_id"]
        diagonal=float(np.linalg.norm(np.ptp(vertices,axis=0)))
        radius=.05*diagonal
        within=np.linalg.norm(vertices-vertices[center],axis=1)<radius
        mask=np.zeros(len(vertices),dtype=bool)
        mask[current["region_source_ids"]]=read_supervision(observation)["changed_mask"]
        cross=np.cross(vertices[faces[:,1]]-vertices[faces[:,0]],vertices[faces[:,2]]-vertices[faces[:,0]])
        sums=np.zeros_like(vertices)
        for corner in range(3):
            np.add.at(sums,faces[:,corner],cross)
        lengths=np.linalg.norm(sums,axis=1)
        bad=~np.isfinite(lengths)|(lengths<=64*np.finfo(float).eps*diagonal**2)
        with np.load(HERE/observation["input"]["base_mesh"]) as source:
            baseline=source["vertices"]
        original_cross=np.cross(baseline[faces[:,1]]-baseline[faces[:,0]],baseline[faces[:,2]]-baseline[faces[:,0]])
        original_sums=np.zeros_like(baseline)
        for corner in range(3):
            np.add.at(original_sums,faces[:,corner],original_cross)
        original_bad=~np.isfinite(original_sums).all(axis=1)|(np.linalg.norm(original_sums,axis=1)<=64*np.finfo(float).eps*np.linalg.norm(np.ptp(baseline,axis=0))**2)
        results.append(dict(id=observation["id"],current_bbox_diagonal=diagonal,current_encoder_radius=radius,
            radius_over_current_encoder_radius=observation["radius"]/radius,depth_over_current_encoder_radius=observation["depth"]/radius,
            current_encoder_neighborhood_points=int(within.sum()),current_encoder_neighborhood_damaged_points=int((within&mask).sum()),
            current_encoder_neighborhood_damaged_fraction=float((within&mask).sum()/within.sum()),
            nonfinite_current_vertex_normals=int((~np.isfinite(sums).all(axis=1)).sum()),
            newly_unavailable_vertex_normals=int((bad&~original_bad).sum()),original_unavailable_vertex_normals=int(original_bad.sum()),
            usable_for_training=observation["usable_for_training"]))
    write("CURRENT_GEOMETRY_QA.json",dict(status="completed",cases=results,model_forwards=0,
        baseline_fields="DATASET_INDEX radius_over_encoder_radius/depth_over_encoder_radius/neighborhood fields use undamaged posture center and bbox as frozen in PLAN",
        current_fields="this report uses actual damaged full current bbox, current center and current Euclidean neighbors with official radius0.05*bboxdiag",
        original_generator="private/recovery/generate_executed.py",post_review_hardening="generic outward-sign fallback now explicitly uses visual sign if closed volume unconfirmed. All actual used source signs +1, no generated values changed or matrix rerun",
        wall_s_before_write=time.perf_counter()-started,cpu_s_before_write=time.process_time()-cpu))
    print("current geometry diagnostic rows",len(results),"newly unavailable normals",sum(r["newly_unavailable_vertex_normals"] for r in results),flush=True)


if __name__=="__main__":
    main()
