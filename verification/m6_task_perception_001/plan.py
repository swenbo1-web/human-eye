"""Freeze one task-facing model, existing-data membership and consumer questions."""

from pathlib import Path
import subprocess
import sys
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from common import DATA,read,write,identity
import json
import numpy as np


def main():
    if (HERE/"PLAN.json").exists():
        raise RuntimeError("plan_already_frozen")
    planner="C:/Users/Administrator/.codex/worktrees/1212/hefe"
    for commit,source,dest in (("28b44c9db9bdc3a3c8e934c18bd87add6f93fb9c","docs/M6_TASK_PERCEPTION_001_TASK.md","CONTRACT.md"),
                               ("4b8a6545162ad9d743a80b30855f1fba3f03a53a","docs/M6_PERCEPTION_DATA_001_REVIEW.md","DATA_REVIEW.md")):
        (HERE/dest).write_bytes(subprocess.check_output(["git","-C",planner,"show",commit+":"+source]))
    dataset=json.loads((DATA/"DATASET_INDEX.json").read_bytes())
    rng=np.random.default_rng(1729)
    permutation=rng.permutation(len(dataset["observations"]))
    aliases={row["id"]:"o"+str(int(index)+1).zfill(4) for row,index in zip(dataset["observations"],permutation)}
    roi_permutation=rng.permutation(len(dataset["rois"]))
    roi_alias={row["id"]:"r"+str(int(index)+1).zfill(3) for row,index in zip(dataset["rois"],roi_permutation)}
    write("ALIASES.json",dict(observation_aliases=aliases,roi_aliases=roi_alias,scope="harness only, never supplied to consumer sandbox"))
    task_rows,focus_pairs=[],[]
    sources=[row for row in dataset["sources"] if row["split"]=="validation"]
    for source_index,source in enumerate(sources):
        for slot in range(2):
            roi_id=source["id"]+"_roi"+str(slot)
            pair=sorted((p for p in dataset["pairs"] if p["roi_id"]==roi_id and p["usable_for_training"]),key=lambda p:p["combo_id"])[0]
            focus_pairs.append(dict(roi_alias=roi_alias[roi_id],normal_alias=aliases[pair["normal_observation_id"]],damaged_alias=aliases[pair["damaged_observation_id"]]))
            state="normal" if (source_index+slot)%2==0 else "damaged"
            original=pair["normal_observation_id"] if state=="normal" else pair["damaged_observation_id"]
            entry="inspect" if slot==0 else "focus"
            request=("检查指定F范围内值得继续查看的局部表面形状，最多分配25%当前F面积作为注意候选。说明测量依据、候选与异常断言的区别、仍需补读的信息和后续几何工具计划。保持当前数据。" if entry=="inspect" else
                     "对我已明确指定的目标准备后续更饱满且平顺的定向精修。先细读当前目标与周边，给出目标质心、面积、包围盒和法向依据。背景属于保护范围，可以观察。说明还需什么参考或幅度信息并制定几何工具操作计划。保持当前数据。")
            task_rows.append(dict(task_id="t"+str(len(task_rows)+1).zfill(2),entrypoint=entry,geometry_alias=aliases[original],
                                  request_text=request,input_file="input.npz",roi_alias=roi_alias[roi_id]))
    write("TASKS.json",dict(tasks=task_rows,selection="DATA source order, each source ROI0 inspect andROI1 focus, alternating states by source+slot, damaged first usable combo alphabetically, no model-score selection",
                           focus_pairs=focus_pairs,focus_target_rule="F-min-sourceID breadth-first traversal, neighbors ascending, first64, complete disconnected remainder by ascending seeds if needed; background/protected=F minus target; same source IDs for normal and preselected dent"))
    write("PLAN.json",dict(cycle_id="M6-TASK-PERCEPTION-001",seed=1729,baseline_commit="a463116f52cc954812cfb6f54513ecfea0eb46ef",contract_commit="28b44c9db9bdc3a3c8e934c18bd87add6f93fb9c",
        user_intent_source=dict(chat="local/01a1d986-24a4-73f1-9689-6845d1f01ef3",message_id="01a1df72-5e51-7802-9c91-5f62e9234d2a",intent="shared local perception supports obvious anomalies and task-directed fine refinement of normal or damaged regions"),
        candidate=dict(count=1,name="multiscale_surface_statistics_shared_MLP",neighbor_counts=[16,48,128,384,1024],descriptor_channels=16,
            channels=["area_mean_normalized_height","area_std_normalized_height","min_height","max_height","q25_height","q75_height","mean_abs_height","mean_normal_dot","std_normal_dot","min_normal_dot","PCA_smallest_ratio","PCA_middle_ratio","outer_quadric_center_residual","outer_quadric_RMS","outer_plane_center_residual","log_radius_over_local_spacing"],
            geometry="one current full mesh area normal computation and KDtree per observation, one batched maximal1024-neighbor query for384 F points, all scales reuse prefixes",
            ring="distance>=0.6 current kth radius, six-term local tangent quadratic ridge1e-6, current area weights; signed residual query minus fitted center height",
            network="shared Linear16,32 GELU Linear32,32 GELU on point-scale rows, concatenate five32D features, Linear160,64 GELU Linear64,1",
            trainable_parameters=11969,pretrained=False,batchnorm=False,dropout=False,
            input_exclusions=["absolute object coordinates","object bbox radius","asset/source IDs","reference coordinates","damage center/radius/depth","supervision mask"],
            context_rationale="F384, maximal1024 neighbors includes at least640 points outside any true changed support confined toF. Label-based posthoc coverage only. Euclidean near-neighbors may cross nearby sheets, retained diagnostic limitation.",
            cache_estimate_bytes=600*384*5*16*4,parameter_and_gradient_estimate_bytes=11969*4*4,
            choice_basis="reuse existing current reader, topology and exact measurements, learn shared local multiscale patterns with full batch tensor operations; no checkpoint download or repeated per-query deep encoder"),
        data=dict(unique_observations=600,valid_dent_pairs=503,development_pairs=338,validation_pairs=165,normal_development=16,normal_validation=8,
                  kept_failed_dents=73,development_groups=["horse_transfer","face_transfer"],validation_groups=["cat_transfer"],independent_final_test=False,
                  scale_diagnostic_wholly_damaged_center_neighborhood=dict(development=[8,338],validation=[55,165]),
                  normalization="development hierarchical case weights only, merge five scales in same16 channels, two-pass moments, divisor1 ifstd<1e-6",
                  labels="synthetic actual displacement support, normals include natural concavity negatives"),
        training=dict(maximum_runs=2,versions=["v1","v2"],steps_each=1200,batch_rows=1024,pair_events=512,optimizer="AdamW",learning_rate=.001,weight_decay=.0001,
                      initial_seed=1729,index="exact DATA001 saved1200x1024 paired-state indices, same rows both versions",initial_loss="BCEWithLogitsLoss, pos_weight=(1-pi)/pi from new dev hierarchy",
                      optimization="after v1 dev-only paired logit diagnostics and committed binding, same initialization and indices, add0.1 positive-pair hinge relu(1-(z_d-z_n)), no validation-tuned choice",
                      calibration="each version16dev normal F max score, q95 methodhigher, strictlygreater threshold. With16 values this is max, disclose finite dependent normal controls, no probability calibration"),
        evaluation=dict(all_valid_development_and_validation=True,normal_controls_all24=True,failed73_kept_status=True,area_budget=.25,
                        baseline="untrained multiscale outer-ring quadratic residual magnitude max across five scales, same current input/area budget; uses existing MLS residual principle, no label-selected scale",
                        gate=dict(validation_macro_area_recall_min=.60,improvement_over_geometry_min=.10,normal_false_observations_max=1,normal_denominator=8),
                        metrics=["point_AUC/AP","macro25percent_area_recall","area_false_positive","zero_hit","normal_patch_false_reports","source/scale groups","all failures"],
                        scale_groups="posthoc original r/R_current bins<=.5,(.5,1],>1 and independent whole-center-neighborhood diagnostic, denominators unchanged"),
        interfaces=dict(inspect="current scope ->25%area attention candidates plus separately thresholded unconfirmed synthetic-depression prediction",focus="explicit target and protected sourceIDs ->direct current geometry facts and appendable topological context, model_invoked=false, no score gate",
                        reference="current vertices/topology/F mapping/sourceIDs/kind/provenance hashed, persisted; stale bindings rejected",focus_QA=16,
                        semantics="explicit source-point binding, anatomical or artistic part classifier absent",edits=0),
        consumer=dict(model="gpt-6.1-sol",reasoning_effort="medium",login="ChatGPT Pro existing auth",routes=["native","facts","learned"],max_tool_calls=6,max_session_seconds=360,
                      python_timeout_s=20,python_output_chars=12000,fact_output_chars=40000,max_tasks=24,task_count=8,
                      fairness="same task bytes/aliases/prompt goal and output schema, same model/effort/tool-call budget, fresh ephemeral session per task route. Native gets full current geometry and reasonable numpy/scipy Python. facts adds direct facts/reference tools, learned adds optimized inspect scores. Focus direct path cost/results kept separate.",
                      execution="local CLI ChatGPT login, no other provider; preserve real launch/provider failures then complete local work; no retries of completed task prompts",
                      scoring="parse final JSON, area-weighted centroid/area/bbox/normals/source-ID mapping from current geometry, inspect selected area<=25% and actual support recall, anomaly assertions separate from candidate attention, author plan scoring explicit, retain all raw outputs for independent blind review",
                      answer_schema=dict(task_id="string",entrypoint="inspect|focus",selected_source_ids="integer list, chosen region for inspect, exact explicit target for focus",region_reference="string or null",centroid_native="3 floats",lumped_area_native="float",bbox_native="{min:[3],max:[3]}",anomaly_asserted="boolean",evidence="list",missing_information="list",operation_plan="list",protection_respected="boolean",editing_executed="false"),
                      cost="record first imports/current reads, feature preparation/cache/predict delivery and references plus actual CLI wall/tool calls/tokens where exposed. Tokens and fees unavailable become unknown, not0; images0 unless actual image requested and generated"),
        budgets=dict(numerical_wall_s=7200,target_memory_bytes=4*1024**3,threads=1,consumer_tasks_separately_counted=True),
        references=["https://arxiv.org/abs/1706.02413","https://docs.pytorch.org/docs/2.15/generated/torch.nn.BCEWithLogitsLoss.html"],
        adoption="all fixed gates and full consumer costs reported. One optimization then adopt/reject conclusion, no further seed/model/source search",completion="one fixed commit callback then end awaiting independent review"))
    names=["PLAN.json","TASKS.json","ALIASES.json","CONTRACT.md","DATA_REVIEW.md"]
    write("PLAN_FREEZE.json",dict(files=[identity(HERE/name) for name in names],reused_data=[identity(DATA/name) for name in ("DATASET_INDEX.json","SPLIT.json","SAMPLER_AUDIT.json","MANIFEST.json","data_io.py")]))
    print("one11969-parameter model, two runs, eight fixed consumer tasks frozen",flush=True)


if __name__=="__main__":
    main()
