"""Freeze development-normal operating points and evaluate the full fixed inventory."""

import argparse
from collections import Counter
from pathlib import Path
import sys
import time
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from common import DATA,identity,read,write,measure
import numpy as np
from sklearn.metrics import roc_auc_score,average_precision_score
from model import load_model,predict_features


def budget_mask(scores,area,source_ids):
    order=np.lexsort((source_ids,-scores))
    count=int(np.searchsorted(np.cumsum(area[order]),.25*area.sum(),side="right"))
    selected=np.zeros(len(area),dtype=bool)
    selected[order[:count]]=True
    return selected


def metrics(scores,threshold,area,mask,source_ids):
    selected=budget_mask(scores,area,source_ids)
    predicted=scores>threshold
    positive_area=float(area[mask].sum())
    normal=~mask
    return dict(AUC=float(roc_auc_score(mask,scores)) if mask.any() and normal.any() else None,
        AP=float(average_precision_score(mask,scores)) if mask.any() else None,
        area_budget_recall=float(area[selected&mask].sum()/positive_area) if positive_area else None,
        attention_area_fraction=float(area[selected].sum()/area.sum()),
        attention_false_area_fraction=float(area[selected&normal].sum()/area[normal].sum()) if normal.any() else None,
        attention_hit=bool((selected&mask).any()),positive_area_native=positive_area,
        anomaly_predicted_points=int(predicted.sum()),anomaly_any=bool(predicted.any()),
        anomaly_area_recall=float(area[predicted&mask].sum()/positive_area) if positive_area else None,
        anomaly_false_area_fraction=float(area[predicted&normal].sum()/area[normal].sum()) if normal.any() else None,
        support_points=int(mask.sum()))


def summarize(rows):
    damaged=[row for row in rows if row["state"]=="damaged" and row["scored"]]
    normal=[row for row in rows if row["state"]=="normal" and row["scored"]]
    result=dict(physical_observations=len(rows),scored_damaged=len(damaged),normal_observations=len(normal),
                retained_unscored_failures=sum(not row["scored"] for row in rows),methods={})
    for method in ("geometry","learned"):
        data=[row[method] for row in damaged]
        averages={key:float(np.mean([r[key] for r in data])) if data else None for key in ("AUC","AP","area_budget_recall","anomaly_area_recall","anomaly_false_area_fraction")}
        averages.update(zero_attention_hit_cases=sum(not r["attention_hit"] for r in data),
                        anomalous_damaged_cases=sum(r["anomaly_any"] for r in data),
                        normal_false_cases=sum(row[method]["anomaly_any"] for row in normal),
                        normal_false_area_fraction=float(np.mean([row[method]["anomaly_false_area_fraction"] for row in normal])) if normal else None)
        result["methods"][method]=averages
    return result


def main():
    started,cpu=time.perf_counter(),time.process_time()
    parser=argparse.ArgumentParser()
    parser.add_argument("--version",choices=("v1","v2"),required=True)
    version=parser.parse_args().version
    if (HERE/("EVALUATION_"+version+".json")).exists():
        raise RuntimeError("fixed_version_already_evaluated")
    timings={}
    with measure(timings,"model_first_load"):
        model,model_identity=load_model(version)
    cases=read("INPUT_INDEX.json")["cases"]
    feature_index={row["alias"]:row for row in read("FEATURES.json")["cases"]}
    outputs={}
    folder=HERE/"private/predictions"
    folder.mkdir(parents=True,exist_ok=True)
    for case in cases:
        local={}
        feature=feature_index[case["alias"]]
        with measure(local,"descriptor_cache_read"):
            if identity(HERE/feature["path"])["sha256"]!=feature["sha256"]:
                raise ValueError("feature_cache_identity_changed")
            with np.load(HERE/feature["path"]) as data:
                arrays=dict(data)
        with measure(local,"shared_encoder_and_head_forward"):
            prediction=predict_features(model,arrays["features"],arrays["valid_mask"])
        path=folder/(case["alias"]+"_"+version+".npz")
        with measure(local,"prediction_cache_write"):
            np.savez_compressed(path,probability=prediction["scores"],logits=prediction["logits"],source_ids=arrays["source_ids"])
        outputs[case["alias"]]=dict(prediction=prediction,area=arrays["area"],baseline=arrays["baseline_score"],source_ids=arrays["source_ids"],
                                     identity=identity(path),timings=local)
    # Calibration never reads validation labels or validation statistics.
    development_normal=[case for case in cases if case["split"]=="development" and case["state"]=="normal"]
    maxima={"geometry":[float(outputs[case["alias"]]["baseline"].max()) for case in development_normal]}
    maxima["learned"]=[float(outputs[case["alias"]]["prediction"]["scores"].max()) for case in development_normal]
    calibration=dict(version=version,development_normal_aliases=[case["alias"] for case in development_normal],count=len(development_normal),
        rule="q95 per-normal-observation maximum with higher quantile, strictlygreater",validation_labels_read=0,validation_statistics_used=0,
        note="16dependent controls, q95 higher equals maximum, operating point only, probabilities uncalibrated",
        thresholds={method:float(np.quantile(values,.95,method="higher")) for method,values in maxima.items()},normal_maxima=maxima)
    write("CALIBRATION_"+version+".json",calibration)
    old=__import__("json").loads((DATA/"DATASET_INDEX.json").read_bytes())
    aliases=read("ALIASES.json")["observation_aliases"]
    old_metadata={aliases[row["id"]]:row for row in old["observations"]}
    truth_index={row["alias"]:row for row in read("SUPERVISION_INDEX.json")["observations"]}
    old_current={aliases[row["id"]]:row for row in __import__("json").loads((DATA/"CURRENT_GEOMETRY_QA.json").read_bytes())["cases"]}
    rows=[]
    context_coverage=[]
    for case in cases:
        alias=case["alias"]
        item=outputs[alias]
        meta=old_metadata[alias]
        row=dict(alias=alias,split=case["split"],state=case["state"],roi_alias=case["roi_alias"],source=meta["mesh_id"],group=meta["group"],
                 scored=case["valid_for_learning"],generator_failures=meta.get("failures",[]),valid_points=int(item["prediction"]["valid_mask"].sum()),
                 prediction=item["identity"],timings=item["timings"])
        if case["state"]=="damaged":
            ratio=old_current[alias]["radius_over_current_encoder_radius"]
            row["scale_group"]="r/R<=.5" if ratio<=.5 else ".5<r/R<=1" if ratio<=1 else "r/R>1"
            row["old_center_neighborhood_wholly_damaged"]=old_current[alias]["current_encoder_neighborhood_damaged_fraction"]==1.
        else:
            row["scale_group"]="normal"
        with np.load(HERE/truth_index[alias]["path"]) as truth:
            mask=truth["mask"].astype(bool)
        if row["scored"]:
            row["learned"]=metrics(item["prediction"]["scores"],calibration["thresholds"]["learned"],item["area"],mask,item["source_ids"])
            row["geometry"]=metrics(item["baseline"],calibration["thresholds"]["geometry"],item["area"],mask,item["source_ids"])
            if case["state"]=="damaged" and version=="v1":
                with np.load(HERE/feature_index[alias]["context"]["path"]) as cache:
                    neighbor_ids=cache["neighbor_ids"]
                changed_ids=item["source_ids"][mask]
                fraction=np.isin(neighbor_ids,changed_ids).mean(axis=1)
                context_coverage.append(dict(alias=alias,split=case["split"],changed_source_points=int(mask.sum()),
                    maximal_context_damaged_fraction_min=float(fraction.min()),maximal_context_damaged_fraction_max=float(fraction.max()),
                    maximal_context_has_unchanged_points_for_all_F=bool((fraction<1).all()),
                    old_center_neighborhood_wholly_damaged=row["old_center_neighborhood_wholly_damaged"]))
        rows.append(row)
    groups={split:summarize([row for row in rows if row["split"]==split]) for split in ("development","validation")}
    by_source={source:summarize([row for row in rows if row["source"]==source]) for source in sorted({row["source"] for row in rows})}
    by_scale={key:summarize([row for row in rows if row["split"]=="validation" and row["scale_group"]==key]) for key in ("r/R<=.5",".5<r/R<=1","r/R>1")}
    validation=groups["validation"]["methods"]
    gates=dict(macro_area_recall_ge060=validation["learned"]["area_budget_recall"]>=.6,
               gain_over_geometry_ge010=validation["learned"]["area_budget_recall"]-validation["geometry"]["area_budget_recall"]>=.1,
               normal_false_cases_le1_of8=validation["learned"]["normal_false_cases"]<=1,
               nonempty_anomaly_predictions_on_damaged=validation["learned"]["anomalous_damaged_cases"]>0)
    report=dict(version=version,model=model_identity,calibration=calibration,cases=rows,groups=groups,by_source=by_source,by_validation_scale=by_scale,
                gates=gates,passed=all(gates.values()),invalid_dents_retained=73,
                validation_denominator=dict(damaged=165,normal=8),timings=timings,
                wall_s_before_write=time.perf_counter()-started,cpu_s_before_write=time.process_time()-cpu,
                limitations=["3derived groups in one corpus", "no independent final test", "synthetic dent labels", "Euclidean context may cross close sheets", "normal calibration has16dependent observations"])
    write("EVALUATION_"+version+".json",report)
    if version=="v1":
        write("CONTEXT_COVERAGE.json",dict(cases=context_coverage,selection_supervision_reads=0,posthoc_scoring_only=True,
            all_maximal_contexts_have_unchanged_points=all(row["maximal_context_has_unchanged_points_for_all_F"] for row in context_coverage),
            old_center_fully_changed_counts={split:sum(r["old_center_neighborhood_wholly_damaged"] for r in context_coverage if r["split"]==split) for split in ("development","validation")}))
    else:
        first=read("EVALUATION_v1.json")
        predictions=[]
        for case in cases:
            alias=case["alias"]
            with np.load(folder/(alias+"_v1.npz")) as initial:
                initial_probability=initial["probability"]
            path=folder/(alias+".npz")
            np.savez_compressed(path,initial_probability=initial_probability,optimized_probability=outputs[alias]["prediction"]["scores"],source_ids=outputs[alias]["source_ids"])
            predictions.append(dict(alias=alias,current_input_sha256=case["input"]["sha256"],**identity(path)))
        write("PREDICTIONS.json",dict(cases=predictions,models=dict(initial=first["model"],optimized=model_identity),candidate_versions=2))
        write("CALIBRATION.json",dict(initial=dict(threshold=first["calibration"]["thresholds"]["learned"]),optimized=dict(threshold=calibration["thresholds"]["learned"]),geometry=dict(threshold=calibration["thresholds"]["geometry"]),
            rule=calibration["rule"],development_normals=16,validation_labels_for_calibration=0))
        write("EVALUATION.json",dict(initial=first["groups"],optimized=groups,initial_gates=first["gates"],optimized_gates=gates,
            passed=report["passed"],same_denominators=True,optimization="same model/init/steps/sampling, one paired positive margin term",only_two_candidate_runs=True))
    print(version,groups["validation"],"gates",gates,flush=True)


if __name__=="__main__":
    main()
