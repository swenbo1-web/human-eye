"""Recheck the frozen artifacts and the actual one-input settlement ledger."""
from pathlib import Path

from numeric_first import BASE, D, ROOT, check, pin, read, write

LIMIT=1179648
PRIOR=ROOT.parent/"M6-045-R3-REPLACEMENT-ENTRY"
INSTALLS=ROOT.parent/"M6-043-R3-REGION-ATTRIBUTION/timing/PLAN.json"


def checks():
    d=read(D)
    for name in ("design","binding","changed_kernel","patch","transform","launcher","startup"):
        check(d[name])
    original=read(INSTALLS)["release_bindings"]
    for install in [*original.values(),d]:
        info=read(check(install["binding"]))
        assert len(info["source_files"])==143
        for ref in info["source_files"]:
            assert pin(Path(info["site_packages"])/ref["path"])["sha256"]==ref["sha256"]
    freeze=read(BASE)
    native=read(check(freeze["geometry"]))
    first=ROOT/"numeric/first_129/RESULT.json"
    observation=read(first)
    assert observation["installation"]==pin(D)
    assert observation["frozen_geometry_and_truth"]==pin(BASE) and observation["status"]=="unknown"
    w=observation["result"]["work"]
    assert observation["result"]["reason"]=="surface_pair_budget"
    for key in ("distance_m","point_a_world","point_b_world","direction_a_to_b"):
        assert observation["result"][key] is None
    older=read(PRIOR/"boundary_diagnostic/C/RESULT.json")["work"]
    shared={k:v for k,v in older.items() if k in w and not k.startswith(("witness_projection_","previous_witness_"))}
    assert len(shared)==28 and all(w[k]==v for k,v in shared.items())
    diagnostic=ROOT/"numeric/same_input_diagnostic_02/RESULT.json"
    proof=read(diagnostic)
    assert proof["plain"]==pin(first)
    attempts=read(check(proof["credit_attempts"]))
    spent=prev_earned=prev_work=0
    detail={}
    for x in attempts:
        assert x["spent_before"]==spent
        assert x["earned"]>=prev_earned and x["credit_before"]==x["earned"]-spent
        assert x["work_before"]>=prev_work
        safe=x["upper"]<=min(LIMIT-x["work_before"],x["credit_before"])
        assert x["admitted"]==safe and 0<=x["actual"]<=(x["upper"] if safe else 0)
        assert x["work_after"]-x["work_before"]==x["actual"]
        assert x["credit_after"]==x["credit_before"]-x["actual"]>=0
        spent+=x["actual"]
        prev_earned=x["earned"]
        prev_work=x["work_after"]
        current=detail.setdefault(x["role"],{"requests":0,"admitted":0,"paid":0})
        current["requests"]+=1
        current["admitted"]+=int(safe)
        current["paid"]+=x["actual"]
    assert spent==w["witness_projection_credit_spent_units"]==10029
    assert w["witness_projection_credit_balance"]==0
    assert detail["previous_selection"]=={"requests":5021,"admitted":2615,"paid":5230}
    assert detail["previous_build"]=={"requests":1,"admitted":1,"paid":18}
    assert detail["previous_test"]=={"requests":2615,"admitted":0,"paid":0}
    assert detail["current"]["paid"]==4781
    assert w["work_units"]==862622 and w["narrow_phase_pairs"]==16384
    pairs=[proof["capture"]["past_pair"],proof["capture"]["new_pair"]]
    assert pairs==[[127,128],[128,128]]
    native_mapping=[{"native_face_rows":p,"left_source_vertex_rows":native["left"]["faces"][p[0]],
                    "right_source_vertex_rows":native["right"]["faces"][p[1]]} for p in pairs]
    assert proof["activation"]["axis"]==[3,1,-4] and proof["activation"]["current_axis"]==[1,1,-2]
    source=check(d["changed_kernel"]).read_text(encoding="utf-8").splitlines()
    names=("def try_run(self, upper, fn):","class _PreviousWitnessProjection",
           "def _make_previous","class _PreviousWitnessTrial","def prunes(self, left, right, best, best_pair, completed",
           "previous_trial = _PreviousWitnessTrial","if previous_trial is not None and previous_trial.prunes")
    return {"status":"evidence_checked_recovery_failed","custody_source_files":572,
            "all_optional_attempts":len(attempts),"by_phase":detail,
            "original_non_projection_work_fields_same":len(shared),"native_mapping":native_mapping,
            "code_source":d["changed_kernel"],
            "source_lines":{label:next(i for i,l in enumerate(source,1) if label in l) for label in names},
            "first_numeric":pin(first),"same_path_diagnostic":pin(diagnostic),
            "no_nonempty_independent_prune_verification":True,
            "work_remainder":LIMIT-w["work_units"],"old_A_B_C_receipts_archived":True}


if __name__=="__main__":
    print(write(ROOT/"CHECKS.json",checks()))
