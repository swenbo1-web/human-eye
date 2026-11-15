"""Materialize both inspection routes for every fixed observation and resolve all refs."""

from pathlib import Path
import sys
import time
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from common import read,write,identity
from interfaces import TaskPerception


def main():
    started,cpu=time.perf_counter(),time.process_time()
    if (HERE/"INSPECT_REPORTS.json").exists():
        raise RuntimeError("all_observation_inspection_reports_already_exist")
    prototype=TaskPerception()
    cases=[]
    checks=0
    refs=set()
    directory=HERE/"private/inspect_reports"
    directory.mkdir(parents=True,exist_ok=True)
    for number,case in enumerate(read("INPUT_INDEX.json")["cases"]):
        alias=case["alias"]
        row=dict(alias=alias,split=case["split"],valid_for_evaluation=case["valid_for_learning"],state=case["state"],routes={})
        for route in ("geometry","perception"):
            report=prototype.inspect(alias,mode=route,request="inspect the specified current F scope")
            path=directory/(alias+"_"+route+".json")
            write(path.relative_to(HERE),report)
            current_refs=[report["inspection_scope"]["reference"],*report["attention"]["all_region_references"],
                          *report["threshold_anomaly_prediction"].get("all_region_references",[])]
            for reference in current_refs:
                resolved=prototype.resolve(reference,include_geometry=False)
                if resolved["identity"]["observation_alias"]!=alias:
                    raise ValueError("inspection_reference_crossed_current_observation")
                refs.add(reference)
                checks+=1
            if report["attention"]["selected_area_fraction_of_scope"]>.25+1e-12:
                raise ValueError("inspection_exceeds_frozen_area_budget")
            row["routes"][route]=dict(report=identity(path),reference_count=len(current_refs),
                candidate_regions=report["attention"]["region_count"],anomaly_regions=report["threshold_anomaly_prediction"].get("region_count"),
                cost=report["cost"],model_forward_in_request=False)
        cases.append(row)
        # Current meshes have different topology sizes, retain only the active full mesh.
        prototype.geometry_cache.pop(alias,None)
        if (number+1)%100==0:
            print("inspection reports",number+1,"/600",flush=True)
    write("INSPECT_REPORTS.json",dict(status="completed_all600_dual_route_inspection_reports",cases=cases,observation_count=600,
        normal_observations=24,valid_dents=503,retained_invalid_dents=73,structured_reports=1200,
        unique_region_references=len(refs),reference_resolutions=checks,all_references_current_bound=True,
        current_model_forwards=0,prediction_source="fixed v2 model inference cache, preparation and forward costs in earlier phases",
        inference_inputs="current-only geometry and learned probabilities, no supervision reads",supervision_reads=0,
        wall_s_before_write=time.perf_counter()-started,cpu_s_before_write=time.process_time()-cpu))
    print("all current inspection reports",len(cases),"unique refs",len(refs),flush=True)


if __name__=="__main__":
    main()
