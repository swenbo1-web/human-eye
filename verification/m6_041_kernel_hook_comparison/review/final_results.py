"""Assemble the 041 owner verdict from independently verified stage results."""
import json
from pathlib import Path
from statistics import median
from hashlib import sha256

ROOT=Path(__file__).resolve().parent.parent
OUT=ROOT/"delivery"
def read(p):
    return json.loads((ROOT/p).read_bytes())
def dump(p,o):
    with (OUT/p).open("x",encoding="utf8",newline="\n") as f:
        json.dump(o,f,ensure_ascii=False,allow_nan=False,indent=2)
        f.write("\n")
def main():
    OUT.mkdir(exist_ok=True)
    s3=read("s3/REVIEW.json"); h=read("review/S1_INDEPENDENT.json"); hooks=read("review/S2_INDEPENDENT.json")
    warm=read("s1/warm_diagnostic/INDEPENDENT_REVIEW.json"); err=read("s2/error_control/run/SUMMARY.json")
    credit=read("review/PAIR129_INDEPENDENT.json"); identity=read("review/GIT_WHEEL_INSTALL.json")
    plans=read("PLAN.json"); src=read("install/PINS.json"); attr=read("review/WARM_ATTRIBUTION.json")
    coverage=read("s3/screen01/RESULT.json")
    assert len(coverage["slots"])==28 and all(v["valid"] for v in coverage["slots"])
    assert warm["checks"]==545 and warm["errors"]==0 and err["valid"]==8 and hooks["all_manual_gates"]
    assert h["paired_queries"]==22 and all(len(arm["rows"])==143 for arm in identity["arms"].values())
    assert credit["lower_bound_squared"]==credit["attained_squared"]=="3"
    regressions=[k for k,v in warm["outcome"].items() if v["material_regression"] is True]
    assert regressions==["Yanyite_warm_high"]
    tail=[x for x in s3["raw"] if x["phase"]=="resource01"]
    assert len(tail)==4
    full=sum(len(o) for o in plans["s3"]["orders"])
    out={"cycle":plans["cycle"],"contract_sha256":sha256(Path(plans["inputs"]["owner_contract"]).read_bytes()).hexdigest(),
         "pins":{k:plans[k] for k in ("base","r3","history","hook_support")},"installed_sources":src["identities"],
         "verdict":{"A":"PASS reference","B":"RESTRICTED; heavy first reads PASS; required Yanyite warm region guard FAIL",
                    "C":"RESTRICTED; manual H1 light and exit behavior PASS; Codex automatic dispatch NOT_RUN",
                    "D":"RESTRICTED; measured G60 combined screen PASS, inherits B and C release limitations",
                    "production_choice":"retain A / accepted serial 032 as the reference. No activation, merge into product or deployment."},
         "counts":{"portable_per_source":3203,"portable_common_fail":23,"portable_common_error":18,"portable_common_skip":13,
              "candidate_focused_passed":25,"candidate_focused_total":26,
              "actual_S1_primary_responses":44,"actual_S1_with_earlier_attempts":51,"S1_complete_cross_arm_pairs":22,
              "S1_warm_measured_responses":warm["complete_responses"],"S1_warm_actual_including_extra_setup":warm["total_business_responses"],
              "S2_manual":84,"S2_exit_controls":err["executed"],"S2_pilot_and_interrupt_controls":6,
              "S3_workflow_slots":full,"S3_separate_resource_slots":4,"S3_pilot_slots":2,
              "S3_host_sessions_including_reference_within_each":full+4+2},
         "S0_independent_pair129":credit,"S1_summary":h["rows"],"S1_warm_scores":warm["outcome"],
         "S1_warm_attribution":attr,"S2_manual":hooks,"S2_native_Codex_auto":"NOT_RUN",
         "S3_medians_and_descriptive_p95":s3["by_arm"],"S3_paired_estimates":s3["paired_reductions_percent"],
         "S3_additive_interaction_ms":s3["interaction_ms"],"S3_unique_resources":tail,
         "counts_and_timings_policy":"Only equivalent complete blocks in foreground screen; all attempts retained; warm diagnosis appended after first S1. CPU and private source/asset reads separated. No tail or end-user LLM latency claim.",
         "product_changes":0,"paid_calls":0,"formal_Codex_config_changes":0}
    dump("RESULTS.json",out)
if __name__=="__main__":
    main()

