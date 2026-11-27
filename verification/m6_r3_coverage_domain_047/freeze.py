"""Freeze archived sources and stopping rules before any added observations."""
from hashlib import file_digest
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=Path("D:/HumanEye/runs/M6-047-R3-COVERAGE-DOMAIN")
OLD=ROOT.parent
CONTRACT="a303b53c8c69ef2ac24283bc515888dc5fd0cdbd"


def read(path):
    return json.loads(Path(path).read_bytes())


def pin(path):
    path=Path(path).resolve(strict=True)
    with path.open("rb") as f:
        return {"path":str(path),"bytes":path.stat().st_size,"sha256":file_digest(f,"sha256").hexdigest()}


def check(ref):
    path=Path(ref["path"])
    assert pin(path)==ref, path
    return path


def write(path,value):
    with Path(path).open("x",encoding="utf-8",newline="\n") as f:
        json.dump(value,f,ensure_ascii=False,indent=2,allow_nan=False)
        f.write("\n")
    return pin(path)


def main():
    ROOT.mkdir(parents=True,exist_ok=True)
    pressure=OLD/"M6-044-R3-FRESH-BUDGET/pressure"
    boundary=OLD/"M6-045-R3-REPLACEMENT-ENTRY"
    region=OLD/"M6-043-R3-REGION-ATTRIBUTION"
    own=OLD/"M6-046-R3-PREVIOUS-WITNESS/oracle"
    installs=read(region/"timing/PLAN.json")["release_bindings"]
    hold=read(region/"holdouts/PLAN_03.json")
    paths={
        "125_freeze":pressure/"FINAL_FREEZE.json",
        "125_ordinary":pressure.parent/"live_pressure/attempt_001/RESULTS.json",
        "129_freeze":boundary/"oracle/FINAL_FREEZE.json",
        "129_ordinary":boundary/"boundary/attempt_001/RESULTS.json",
        "G60_plain":boundary/"g60/main_001/RESULTS.json",
        "G60_045_independent":boundary/"g60/verification/RESULTS.json",
        "G60_native_original":Path("D:/he_b32g_release_acceptance/matrix/B_G60_D12/INITIAL.json"),
        "real_assembly_holdout":own/"RESULTS.json",
        "independent_assembly_archive":region/"quality/attempt_003/raw/other_family_A.json",
        "Yanyite_separate":region/"holdouts/PLAN_03.json",
        "Yanyite_high_formal_native":region/"live/yanyite/attempt_001/RESULTS.json",
        "Yanyite_high_replay":region/"timing/attempt_001/RESULTS.json",
        "Yanyite_low_prepaid":HERE.parent/"m6_r3_previous_witness_046/quality/original_043_REMAINING_CREDIT_043.json",
        "Yanyite_low_prepaid_source":HERE.parent/"m6_r3_previous_witness_046/quality/original_043_remaining_credit_control.py",
    }
    for x in ("A","C"):
        paths[f"Yanyite_frozen_{x}"]=region/f"holdouts/attempt_03/{x}/RESULT.json"
        paths[f"125_ordinary_{x}"]=pressure.parent/f"live_pressure/attempt_001/{x}/CELL.json"
        paths[f"129_ordinary_{x}"]=boundary/f"boundary/attempt_001/{x}/CELL.json"
        paths[f"assembly_archived_{x}"]=region/f"quality/attempt_003/raw/other_family_{x}.json"
    for key in ("low","high"):
        paths[f"Yanyite_geometry_{key}"]=check(hold["cases"]["Yanyite_"+key])
    frames={
        arm:{
            "identity":installs[arm]["identity"],
            "binding":installs[arm]["binding"],
            "source":{name:pin(Path(installs[arm]["site"])/"human_eye_plugin"/name)
                      for name in ("surface_proximity.py","surface_geometry.py","surface_scan.py","task_query.py",
                                   "live_service.py","scene_cache.py","source_region.py")}
        } for arm in ("A","C")
    }
    records={"cycle_id":ROOT.name,"contract":CONTRACT,"status":"frozen_before_new_observation",
             "runtime":frames,"primary":{k:pin(v) for k,v in paths.items()},
             "optional_inventory":{"fixed_scope":"Native archived ordinary A/C same pair, valid full evaluated geometry. Fixed ordered sources below, then stable lexical source/pair order; only first eligible optional case.",
                "ordinary_archive_roots":[str(region/"live/checks"),str(region/"live/g60"),str(region/"live/yanyite"),
                       str(boundary/"g60/main_001")],
                "eligible":"not one of primary matrix, genuine native asset with potential faces at least 9/10*16384 and sum <=4096, ordinary success/unknown raw binding and same A/C release identifiable",
                "selection_uses":"native counts and archival identity only; no new geometry or outcome search"},
             "budgets":{"faces_sum":4096,"narrow":16384,"work":1179648,
                        "remaining_after_precharge_not_replaced_by_nominal_cap":True,
                        "clock_and_source_change_separate":True},
             "stop":"Report first unproved complete-result condition or not-covered route; do not build router, launch GUI, or benchmark.",
             "execution":"All primary facts from already frozen archives. A single offline observation only if an essential field remains absent and reconstitution has known original identities; otherwise mark unavailable.",
             "claims":{"proof_tiers":["narrow","charged work","representation/publish","all request/clock"],
                       "deployment_and_speed_prediction":False}}
    print(write(ROOT/"FREEZE.json",records))


if __name__=="__main__":
    main()
