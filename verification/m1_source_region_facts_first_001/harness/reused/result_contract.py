"""Bind an owner tool result to either observed CLI result envelope.

Tool identity, arguments, attempt order and slot lifecycle remain the caller's
responsibility. This module performs no file, process, network or tool action.
"""

import json
import math


def _mismatch(reason):
    return {"matched": False, "classification": "protocol_mismatch", "reason": reason}


def _check_json_types(value):
    """Reject Python-only values and object-key coercions before serializing."""
    if type(value) is dict:
        if any(type(key) is not str for key in value):
            raise TypeError("JSON object keys must be strings")
        for member in value.values():
            _check_json_types(member)
    elif type(value) is list:
        for member in value:
            _check_json_types(member)
    elif type(value) not in (str, int, float, bool, type(None)):
        raise TypeError("Non-JSON value")


def _canonical_content(content):
    _check_json_types(content)
    return json.dumps(content, ensure_ascii=False, allow_nan=False,
                      sort_keys=True, separators=(",", ":"))


def bind_tool_result(owner_response, cli_item):
    """Return matched, classification and reason without changing either input.

    Both successful tools and normally reported tool errors pass the same body
    comparison after their envelope, CLI status and null error are checked.
    """
    if type(owner_response) is not dict:
        return _mismatch("owner_response_not_object")
    if "error" in owner_response:
        return _mismatch("owner_jsonrpc_error")
    if set(owner_response) != {"jsonrpc", "id", "result"} or owner_response["jsonrpc"] != "2.0":
        return _mismatch("owner_response_envelope")
    owner_id = owner_response["id"]
    if type(owner_id) not in (str, int, float, type(None)) or (
            type(owner_id) is float and not math.isfinite(owner_id)):
        return _mismatch("owner_response_envelope")

    owner_result = owner_response["result"]
    if type(owner_result) is not dict or set(owner_result) != {"content", "isError"}:
        return _mismatch("owner_result_envelope")
    owner_is_error = owner_result["isError"]
    if type(owner_is_error) is not bool:
        return _mismatch("owner_is_error_not_boolean")

    if type(cli_item) is not dict or cli_item.get("type") != "mcp_tool_call":
        return _mismatch("cli_item_not_tool")
    if "error" not in cli_item:
        return _mismatch("cli_error_missing")
    if cli_item["error"] is not None:
        return _mismatch("cli_error_non_null")
    expected_status = "failed" if owner_is_error else "completed"
    if cli_item.get("status") != expected_status:
        return _mismatch("cli_status_mismatch")

    cli_result = cli_item.get("result")
    if type(cli_result) is not dict:
        return _mismatch("cli_result_envelope")
    if set(cli_result) == {"content", "isError"}:
        if type(cli_result["isError"]) is not bool:
            return _mismatch("cli_is_error_not_boolean")
        if cli_result["isError"] is not owner_is_error:
            return _mismatch("cli_is_error_mismatch")
    elif set(cli_result) == {"content", "structured_content"}:
        if cli_result["structured_content"] is not None:
            return _mismatch("cli_structured_content_non_null")
    else:
        return _mismatch("cli_result_envelope")

    if type(owner_result["content"]) is not list or type(cli_result["content"]) is not list:
        return _mismatch("content_not_json_array")
    try:
        owner_content = _canonical_content(owner_result["content"])
        cli_content = _canonical_content(cli_result["content"])
    except (TypeError, ValueError, RecursionError):
        return _mismatch("content_invalid_json")
    if owner_content != cli_content:
        return _mismatch("content_mismatch")

    return {"matched": True, "classification": "tool_error" if owner_is_error else "success",
            "reason": "content_and_envelope_match"}
