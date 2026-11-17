"""Add scoped, non-authorizing result fields without replacing legacy facts."""
from __future__ import annotations

import copy


PAIR_SCOPE = "known_mesh_pair_clearance_alignment_and_world_pivot"
CONTRACT_VERSION = "1.1"
_REFUSALS = {
    "blocked", "observation_required", "invalid_action", "invalid_goal", "disabled",
    "host_quarantined", "implementation_mismatch", "host_snapshot_unavailable",
    "host_execution_uncertain", "host_readback_uncertain", "host_readback_rejected",
}


def _reasons(*sources):
    result = []
    for source in sources:
        if isinstance(source, (list, tuple)):
            for reason in source:
                if isinstance(reason, str) and reason and reason not in result:
                    result.append(reason)
    return result


def scoped_result(value, *, operation, goal=None, pair=None):
    """Separate observation, pair goal and execution; never grants authority.

    The compatible ``task_succeeded`` field describes caller-supplied pair
    criteria only. A preview is still a preview; no field here is a token.
    """
    result = dict(value)
    route = result.get("routing") or {}
    if not isinstance(route, dict):
        route = {}
    verification = result.get("goal_verification") or {}
    if not isinstance(verification, dict):
        verification = {}
    requested_goal = verification.get("goal") or goal or {}
    pair = pair if isinstance(pair, dict) else {}
    requested_goal = requested_goal if isinstance(requested_goal, dict) else {}
    evaluation = result.get("goal_evaluation", "not_requested")
    requested = bool(verification or goal is not None or evaluation != "not_requested")
    if requested and evaluation == "not_requested":
        evaluation = result["goal_evaluation"] = "not_evaluated"
    goal_status = {
        "goal_satisfied": "satisfied", "goal_not_satisfied": "not_satisfied",
        "measurement_unavailable": "unknown", "evaluation_failed": "error",
        "invalid_goal": "error", "not_evaluated": "not_evaluated",
    }.get(evaluation, "not_evaluated" if requested else "not_requested")
    result["pair_goal"] = {
        "status": goal_status, "scope": PAIR_SCOPE,
        "evaluation_status": evaluation,
        "satisfied": result.get("task_succeeded") if goal_status in {"satisfied", "not_satisfied"} else None,
        "focal_id": verification.get("focal_id", requested_goal.get("focal_id", pair.get("focal_id"))),
        "reference_id": verification.get("reference_id", requested_goal.get("reference_id", pair.get("reference_id"))),
        "scene_revision": verification.get("scene_revision"),
        "reason_codes": _reasons(verification.get("reason_codes")),
        "goal_source": "caller_supplied_not_verified_user_intent" if requested else None,
    }
    result["task_succeeded_scope"] = PAIR_SCOPE if requested else None

    observation = route.get("observation_status")
    if observation not in {"complete", "partial", "unavailable", "not_requested"}:
        if operation == "observe":
            observation = ("complete" if result.get("status") in {"observed", "overview"}
                           else "partial" if result.get("status") == "partial"
                           else "not_requested" if result.get("status") == "disabled" else "unavailable")
        else:
            observation = "complete" if route.get("reason_codes") == ["spatial_3d_observed"] else "not_requested"
    result["observation_status"] = observation
    capabilities = route.get('scene_capabilities', result.get('scene_capabilities'))
    if isinstance(capabilities, dict):
        result['scene_capabilities'] = copy.deepcopy(capabilities)
    assessment = route.get("scene_assessment") or result.get("scene_assessment")
    result["scene_assessment"] = copy.deepcopy(assessment) if isinstance(assessment, dict) else {
        "status": "not_evaluated", "scope": "all_scene_objects",
        "unknown_object_ids": [], "reason_codes": [],
    }
    result["reason_codes"] = _reasons(result.get("reason_codes"), route.get("reason_codes"))
    if result.get("status") in _REFUSALS and not result["reason_codes"]:
        result["reason_codes"] = [result["status"]]

    executed = result.get("executed", False)
    if operation != "transform":
        execution = "not_requested"
    elif executed is None or executed is True and result.get("execution_verified") is not True:
        execution = "execution_uncertain"
    elif executed is True:
        execution = "executed_verified"
    else:
        execution = "not_executed"
    result["execution_status"] = execution

    capability = result.get("host_execution")
    if isinstance(capability, dict) and capability.get("supported") is False:
        result["reason_codes"] = _reasons(result["reason_codes"], ["host_execution_unsupported"],
            [item.get("reason") for item in capability.get("reasons", []) if isinstance(item, dict)])
    reasons = result["reason_codes"]
    if (observation == "partial" or result.get("allow_action") is False
          or route.get("allow_action") is False
          or isinstance(capability, dict) and capability.get("supported") is False
          or result.get("status") in _REFUSALS
          or execution == "execution_uncertain"):
        eligibility = "blocked"
        eligibility_reasons = _reasons(reasons, result["scene_assessment"].get("reason_codes"))
        if not eligibility_reasons:
            eligibility_reasons = ["fresh_execution_conditions_not_established"]
    elif operation == "preview" and result.get("allow_action") is True:
        eligibility = "eligible_preview"
        eligibility_reasons = ["preview_only_fresh_execution_gate_required"]
    else:
        eligibility = "not_evaluated"
        eligibility_reasons = ["fresh_execution_gate_required"]
    result["action_eligibility"] = {
        "status": eligibility, "reason_codes": eligibility_reasons,
        "execution_authority": False,
    }
    result["result_contract_version"] = CONTRACT_VERSION
    return result
