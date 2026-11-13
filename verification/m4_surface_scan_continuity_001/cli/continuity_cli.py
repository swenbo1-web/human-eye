"""Small continuity adapters for the frozen CLI argv and public event stream.

No process or provider operation is performed by this module. Actual resume
history and usage semantics still require evidence from future model turns.
"""

import copy
from uuid import UUID


TURN_LABELS = ("BASE", "REPEAT", "EDIT")
USAGE_FIELDS = (
    "input_tokens", "cached_input_tokens", "cache_write_input_tokens",
    "output_tokens", "total_tokens", "reasoning_tokens", "reasoning_output_tokens",
)


def argv_for_turn(initial_argv, expected_thread_id=None):
    """Reuse the original argv/config and select an explicit persisted session."""
    argv = list(initial_argv)
    if len(argv) < 3 or argv[1] != "exec" or argv[-1] != "-":
        raise ValueError("expected_existing_exec_argv_with_stdin_prompt")
    if any(flag in argv for flag in ("resume", "fork", "--last", "--all")):
        raise ValueError("expected_fresh_argv_template")
    argv = [item for item in argv if item != "--ephemeral"]
    if expected_thread_id is None:
        return argv
    if str(UUID(expected_thread_id)) != expected_thread_id:
        raise ValueError("canonical_explicit_thread_UUID_required")

    # These two options belong to exec, while the resume help lists the
    # remaining frozen options, including each -c override and -o final path.
    parent_options = []
    resume_options = []
    index = 2
    while index < len(argv) - 1:
        item = argv[index]
        if item in ("-C", "--cd", "--color"):
            if index + 1 >= len(argv) - 1:
                raise ValueError("missing_parent_option_value")
            parent_options.extend(argv[index:index + 2])
            index += 2
            continue
        resume_options.append(item)
        index += 1
    return [argv[0], "exec", *parent_options, "resume", *resume_options, expected_thread_id, "-"]


def summarize_turn(events, *, episode_id, turn_index, expected_thread_id, exit_code):
    """Keep execution validity, visible final text and raw usage separate."""
    if turn_index not in (1, 2, 3):
        raise ValueError("fixed_three_turns_required")
    if not episode_id:
        raise ValueError("episode_id_required")
    if (turn_index == 1) != (expected_thread_id is None):
        raise ValueError("explicit_resume_binding_required_after_first_turn")
    thread_rows = []
    usage_rows = []
    completion_count = 0
    errors = []
    messages = []
    for source in events:
        event = source.get("event", source)
        kind = event.get("type")
        if kind == "thread.started":
            thread_rows.append(event.get("thread_id"))
        if kind in ("error", "turn.failed"):
            errors.append(copy.deepcopy(event))
        if kind == "turn.completed":
            completion_count += 1
            usage = event.get("usage")
            if isinstance(usage, dict):
                usage_rows.append(copy.deepcopy(usage))
                for key in USAGE_FIELDS:
                    if key in usage and (type(usage[key]) is not int or usage[key] < 0):
                        errors.append({"type": "invalid_usage", "field": key})
            else:
                errors.append({"type": "missing_usage"})
        item = event.get("item", {})
        if kind == "item.completed" and item.get("type") == "agent_message":
            messages.append(copy.deepcopy(item))
    observed_thread = thread_rows[0] if len(thread_rows) == 1 else None
    if not observed_thread:
        errors.append({"type": "thread_identity_missing_or_ambiguous"})
    else:
        try:
            canonical = str(UUID(observed_thread)) == observed_thread
        except (ValueError, TypeError, AttributeError):
            canonical = False
        if not canonical:
            errors.append({"type": "thread_identity_invalid"})
    if expected_thread_id is not None and observed_thread != expected_thread_id:
        errors.append({"type": "resume_thread_mismatch", "expected": expected_thread_id, "observed": observed_thread})
    if completion_count != 1:
        errors.append({"type": "terminal_turn_count", "observed": completion_count})
    final = messages[-1].get("text") if messages else None
    if not isinstance(final, str) or not final.strip():
        errors.append({"type": "final_missing"})
    if exit_code != 0:
        errors.append({"type": "CLI_exit", "exit_code": exit_code})
    return {
        "episode_id": episode_id, "turn_index": turn_index, "turn_label": TURN_LABELS[turn_index - 1],
        "execution_state": "completed" if not errors else "failed",
        "valid_completion": not errors, "CLI_exit_code": exit_code,
        "expected_thread_id": expected_thread_id, "observed_thread_id": observed_thread,
        "thread_events": thread_rows, "errors": errors, "public_messages": messages,
        "final": final, "final_present": isinstance(final, str) and bool(final.strip()),
        "content_quality": "unscored", "usage_events": usage_rows,
        "usage_semantics": "unconfirmed_turn_or_session_scope",
        "usage_aggregation": None, "interrupted_stream_usage_coverage": "unknown",
        "scope": "event/exit projection only; process cleanup, deadlines, backend continuity and content correctness require separate evidence",
    }


def episode_manifest(episode_id, turn_records, anonymous_episode_id):
    """Project three fixed slots, retaining a failed final and every error body.

This is the episode/turn envelope for the existing raw archive and business
request/response projector. It supplies no correctness or cleanup attestation.
"""
    if not episode_id or not anonymous_episode_id:
        raise ValueError("episode_ids_required")
    by_turn = {}
    for record in turn_records:
        index = record["turn_index"]
        if record["episode_id"] != episode_id or index not in (1, 2, 3) or index in by_turn:
            raise ValueError("episode_turn_binding_or_duplicate")
        if record["turn_label"] != TURN_LABELS[index - 1]:
            raise ValueError("turn_label_binding")
        if record["execution_state"] not in ("completed", "failed"):
            raise ValueError("recorded_turn_execution_state")
        by_turn[index] = record
    rows = []
    for index, label in enumerate(TURN_LABELS, 1):
        record = by_turn.get(index)
        if record is None:
            rows.append({"turn_index": index, "turn_label": label, "execution_state": "not_run",
                         "valid_completion": False, "final": None, "final_present": False,
                         "content_quality": "unscored", "errors": []})
            continue
        # Administrative timing is removed from the known source envelope.
        # Event payloads and JSON-looking strings are preserved verbatim.
        rows.append({key: copy.deepcopy(record[key]) for key in (
            "turn_index", "turn_label", "execution_state", "valid_completion", "final", "final_present",
            "content_quality", "errors",
        )})
    return {
        "anonymous_episode_id": anonymous_episode_id, "planned_turns": 3,
        "turns": rows,
        "counts": {state: sum(row["execution_state"] == state for row in rows)
                   for state in ("completed", "failed", "not_run")},
        "final_present": sum(row["final_present"] for row in rows),
        "content_quality": "unscored", "model_continuity_attestation": "pending_actual_consumer",
        "scope": "known episode administrative projection; business content may reveal route",
    }
