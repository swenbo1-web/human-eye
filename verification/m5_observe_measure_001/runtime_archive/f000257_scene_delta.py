"""Bounded observation-only transport for complete detached scene snapshots.

History is supplied by the existing scene cache; this module neither owns a
cache nor issues observation/action tokens. Only identified complete snapshots
in one document may use a delta. Full payloads are explicit resynchronization,
and incomplete captures never generate deletion instructions.
"""
from __future__ import annotations

import copy
import hashlib
import json

from .auto_router import _validated_scene


SCENE_DELTA_SCHEMA_VERSION = "1.0"
DEFAULT_MAX_BYTES = 8 * 1024 * 1024
_COMPLETE_SCOPE = "complete_scene_meshes"
_PACKET_FIELDS = {"schema_version", "purpose", "execution_authority", "capture_scope",
                  "status", "base", "target", "payload", "reason_codes", "invalidation",
                  "selection", "byte_counts"}
_REFERENCE_FIELDS = {"scene_revision", "scene_fingerprint", "document_epoch"}
_DELTA_FIELDS = {"metadata", "mesh_order", "added", "updated", "replaced", "removed"}


def _encode(value):
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, OverflowError, RecursionError) as exc:
        raise ValueError("Scene transport requires finite canonical JSON values") from exc


def _limits(max_bytes, min_savings_bytes=0):
    if type(max_bytes) is not int or not 1024 <= max_bytes <= 64 * 1024 * 1024:
        raise ValueError("max_bytes must be an integer in 1024..67108864")
    if type(min_savings_bytes) is not int or not 0 <= min_savings_bytes <= max_bytes:
        raise ValueError("min_savings_bytes must be an integer within the byte budget")


def _bounded(value, max_bytes):
    encoded = _encode(value)
    if len(encoded) > max_bytes:
        raise ValueError("Scene transport exceeds its complete-payload byte budget")
    return encoded


def _normalize(scene, max_bytes):
    # Detached cache snapshots are JSON, not arbitrary object graphs or arrays.
    if type(scene) is not dict:
        raise ValueError("Scene transport requires a complete snapshot object")
    _bounded(scene, max_bytes)
    try:
        normalized, _, fingerprint, encoded = _validated_scene(scene, _return_payload=True, _annotate_scene=False)
    except (TypeError, ValueError, OverflowError, RecursionError) as exc:
        raise ValueError("Invalid complete scene snapshot: " + str(exc)) from exc
    if len(encoded) > max_bytes:
        raise ValueError("Normalized scene exceeds the transport byte budget")
    return normalized, encoded, fingerprint


def _reference(scene, fingerprint):
    return {"scene_revision": scene["revision"], "scene_fingerprint": fingerprint,
            "document_epoch": scene.get("host_identity", {}).get("document_epoch")}


def _global_metadata(scene):
    result = {key: copy.deepcopy(value) for key, value in scene.items()
              if key not in {"revision", "meshes"}}
    if "host_identity" in result:
        result["host_identity"].pop("object_instances", None)
    return result


def _invalidation(previous, current, operations):
    changed = sorted(set(operations["added"]) | set(operations["updated"])
                     | set(operations["replaced"]) | set(operations["removed"]))
    global_change = _encode(_global_metadata(previous)) != _encode(_global_metadata(current))
    if global_change:
        changed = sorted({m["object_id"] for m in previous["meshes"] + current["meshes"]})
    return {"mode": "changed_objects", "object_ids": changed,
            "scene_metadata_changed": global_change}


def _operations(previous, current):
    old = {mesh["object_id"]: mesh for mesh in previous["meshes"]}
    new = {mesh["object_id"]: mesh for mesh in current["meshes"]}
    old_instances = previous["host_identity"]["object_instances"]
    new_instances = current["host_identity"]["object_instances"]
    result = {"metadata": {key: copy.deepcopy(value) for key, value in current.items() if key != "meshes"},
              "mesh_order": [mesh["object_id"] for mesh in current["meshes"]],
              "added": {}, "updated": {}, "replaced": {}, "removed": sorted(set(old) - set(new))}
    for identity, mesh in new.items():
        if identity not in old:
            kind = "added"
        elif old_instances[identity] != new_instances[identity]:
            kind = "replaced"
        elif _encode(old[identity]) != _encode(mesh):
            kind = "updated"
        else:
            continue
        result[kind][identity] = copy.deepcopy(mesh)
    return result


def _packet(status, payload, *, base, target, reason_codes, invalidation,
            full_snapshot_bytes, min_savings_bytes):
    result = {"schema_version": SCENE_DELTA_SCHEMA_VERSION, "purpose": "observation_only",
        "execution_authority": False, "capture_scope": _COMPLETE_SCOPE,
        "status": status, "base": copy.deepcopy(base), "target": copy.deepcopy(target),
        "payload": copy.deepcopy(payload), "reason_codes": list(reason_codes),
        "invalidation": copy.deepcopy(invalidation),
        "selection": {"policy": "compare_complete_canonical_envelopes",
                      "minimum_savings_bytes": min_savings_bytes},
        "byte_counts": {"full_snapshot_bytes": full_snapshot_bytes,
                        "payload_bytes": len(_encode(payload)), "envelope_bytes": 0}}
    # Only this integer's digit count feeds back into its encoded wire length.
    for _ in range(16):
        size = len(_encode(result))
        if result["byte_counts"]["envelope_bytes"] == size:
            return result
        result["byte_counts"]["envelope_bytes"] = size
    raise ValueError("Cannot stabilize scene transport byte accounting")


def make_scene_delta(previous, current, *, capture_scope=_COMPLETE_SCOPE,
                     max_bytes=DEFAULT_MAX_BYTES, min_savings_bytes=128):
    """Select a smaller complete delta or a full resynchronization payload.

    Invalid/oversized complete inputs raise ValueError. Partial captures return
    needs_full_resync without add/update/remove operations. Missing identities
    and document changes require a full payload; old data is not merged across
    document epochs. Comparison includes each candidate's canonical envelope.
    """
    _limits(max_bytes, min_savings_bytes)
    if not isinstance(capture_scope, str) or not capture_scope:
        raise ValueError("capture_scope must be a nonempty string")
    identity = current.get("host_identity") if isinstance(current, dict) else None
    if (capture_scope != _COMPLETE_SCOPE or isinstance(identity, dict)
            and identity.get("capture_scope") != _COMPLETE_SCOPE):
        result = _packet("needs_full_resync", None, base=None, target=None,
            reason_codes=["incomplete_capture_not_a_deletion_signal"],
            invalidation={"mode": "none", "object_ids": [], "scene_metadata_changed": False},
            full_snapshot_bytes=None, min_savings_bytes=min_savings_bytes)
        _bounded(result, max_bytes)
        return result
    current, current_bytes, current_hash = _normalize(current, max_bytes)
    target = _reference(current, current_hash)
    previous_normalized = previous_bytes = previous_hash = base = None
    reason = "base_unavailable_full_resync"
    if previous is not None:
        previous_identity = previous.get("host_identity") if isinstance(previous, dict) else None
        if isinstance(previous_identity, dict) and previous_identity.get("capture_scope") != _COMPLETE_SCOPE:
            reason = "incomplete_base_full_resync"
        else:
            previous_normalized, previous_bytes, previous_hash = _normalize(previous, max_bytes)
            base = _reference(previous_normalized, previous_hash)
            reason = "full_snapshot_preferred"
            if "host_identity" not in previous_normalized or "host_identity" not in current:
                reason = "identity_unavailable_full_resync"
            elif base["document_epoch"] != target["document_epoch"]:
                reason = "document_epoch_changed_full_resync"
    full = _packet("full", current, base=base, target=target, reason_codes=[reason],
        invalidation={"mode": "full_resync", "object_ids": sorted(m["object_id"] for m in current["meshes"]),
                      "scene_metadata_changed": True},
        full_snapshot_bytes=len(current_bytes), min_savings_bytes=min_savings_bytes)
    if previous_normalized is None:
        _bounded(full, max_bytes)
        return full
    if previous_hash == current_hash and previous_bytes != current_bytes:
        raise ValueError("Conflicting complete contents have the same scene fingerprint")
    if ("host_identity" not in previous_normalized or "host_identity" not in current
            or base["document_epoch"] != target["document_epoch"]):
        _bounded(full, max_bytes)
        return full
    operations = _operations(previous_normalized, current)
    delta = _packet("delta", operations, base=base, target=target, reason_codes=[],
        invalidation=_invalidation(previous_normalized, current, operations),
        full_snapshot_bytes=len(current_bytes), min_savings_bytes=min_savings_bytes)
    delta_size, full_size = len(_encode(delta)), len(_encode(full))
    if delta_size <= max_bytes and delta_size < full_size and full_size - delta_size >= min_savings_bytes:
        return delta
    _bounded(full, max_bytes)
    return full


def _valid_reference(reference, *, required):
    if reference is None and not required:
        return
    if type(reference) is not dict or set(reference) != _REFERENCE_FIELDS:
        raise ValueError("Invalid scene transport reference")
    revision, fingerprint, epoch = (reference[field] for field in
        ("scene_revision", "scene_fingerprint", "document_epoch"))
    if (not isinstance(revision, str) or not revision.strip()
            or not isinstance(fingerprint, str) or len(fingerprint) != 64
            or any(c not in "0123456789abcdef" for c in fingerprint)
            or epoch is not None and (not isinstance(epoch, str) or not epoch.strip() or len(epoch) > 256)):
        raise ValueError("Invalid scene revision, fingerprint or document epoch")


def _validate_packet(envelope, max_bytes):
    raw = _bounded(envelope, max_bytes)
    if (type(envelope) is not dict or set(envelope) != _PACKET_FIELDS
            or envelope.get("schema_version") != SCENE_DELTA_SCHEMA_VERSION
            or envelope.get("purpose") != "observation_only"
            or envelope.get("execution_authority") is not False
            or envelope.get("capture_scope") != _COMPLETE_SCOPE
            or not isinstance(envelope.get("status"), str)
            or envelope.get("status") not in {"full", "delta", "needs_full_resync"}
            or not isinstance(envelope.get("reason_codes"), list)
            or any(not isinstance(reason, str) or not reason for reason in envelope["reason_codes"])):
        raise ValueError("Invalid observation-only scene transport envelope")
    selection = envelope["selection"]
    if (type(selection) is not dict or set(selection) != {"policy", "minimum_savings_bytes"}
            or selection["policy"] != "compare_complete_canonical_envelopes"):
        raise ValueError("Invalid scene transport selection policy")
    _limits(max_bytes, selection["minimum_savings_bytes"])
    counts = envelope["byte_counts"]
    if (type(counts) is not dict or set(counts) != {"full_snapshot_bytes", "payload_bytes", "envelope_bytes"}
            or any(type(counts[field]) is not int or counts[field] < 0
                   for field in ("payload_bytes", "envelope_bytes"))
            or counts["full_snapshot_bytes"] is not None
               and (type(counts["full_snapshot_bytes"]) is not int or counts["full_snapshot_bytes"] < 0)
            or counts["payload_bytes"] != len(_encode(envelope["payload"]))
            or counts["envelope_bytes"] != len(raw)):
        raise ValueError("Invalid scene transport byte accounting")
    _valid_reference(envelope["base"], required=envelope["status"] == "delta")
    _valid_reference(envelope["target"], required=envelope["status"] != "needs_full_resync")
    if envelope["status"] == "needs_full_resync":
        raise ValueError("A complete full snapshot is required before applying scene state")


def apply_scene_delta(base, envelope, *, max_bytes=DEFAULT_MAX_BYTES):
    """Return a new complete normalized observation, never mutate base/history.

    A full envelope deliberately replaces any local base after its own target
    content is validated. A delta requires the exact base revision, full SHA256
    and document epoch, plus consistent per-object incarnation transitions.
    Returned data is not an execution authorization or a fresh host capture.
    """
    _limits(max_bytes)
    _validate_packet(envelope, max_bytes)
    payload = envelope["payload"]
    previous = None
    if envelope["status"] == "full":
        current, encoded, fingerprint = _normalize(payload, max_bytes)
        if encoded != _encode(payload):
            raise ValueError("Full scene payload is not the complete normalized snapshot")
        expected_invalidation = {"mode": "full_resync", "object_ids": sorted(m["object_id"] for m in current["meshes"]),
                                 "scene_metadata_changed": True}
    else:
        previous, _, previous_hash = _normalize(base, max_bytes)
        if _reference(previous, previous_hash) != envelope["base"]:
            raise ValueError("Scene delta base revision, fingerprint or epoch mismatch; full resync required")
        if ("host_identity" not in previous or envelope["base"]["document_epoch"] is None
                or envelope["base"]["document_epoch"] != envelope["target"]["document_epoch"]):
            raise ValueError("Delta cannot cross a missing or changed document epoch")
        if type(payload) is not dict or set(payload) != _DELTA_FIELDS or type(payload["metadata"]) is not dict:
            raise ValueError("Invalid complete scene delta payload")
        if "meshes" in payload["metadata"]:
            raise ValueError("Delta metadata cannot hide a separate mesh inventory")
        order, removed = payload["mesh_order"], payload["removed"]
        if (type(order) is not list or not 1 <= len(order) <= 256
                or any(not isinstance(identity, str) or not identity for identity in order)
                or len(set(order)) != len(order) or type(removed) is not list
                or any(not isinstance(identity, str) or not identity for identity in removed)
                or len(set(removed)) != len(removed)):
            raise ValueError("Delta requires a unique nonempty complete mesh order and removal set")
        old = {mesh["object_id"]: mesh for mesh in previous["meshes"]}
        maps = [payload[field] for field in ("added", "updated", "replaced")]
        if any(type(mapping) is not dict or len(mapping) > 256 for mapping in maps):
            raise ValueError("Invalid delta object operation map")
        operation_ids = [set(mapping) for mapping in maps] + [set(removed)]
        if any(left & right for i, left in enumerate(operation_ids) for right in operation_ids[i + 1:]):
            raise ValueError("Delta operations must be disjoint")
        added, updated, replaced = operation_ids[:3]
        new_ids = set(order)
        if (added != new_ids - set(old) or set(removed) != set(old) - new_ids
                or not updated.issubset(set(old) & new_ids) or not replaced.issubset(set(old) & new_ids)):
            raise ValueError("Delta operations do not match the complete object inventories")
        rebuilt = copy.deepcopy(old)
        for identity in removed:
            rebuilt.pop(identity)
        for mapping in maps:
            for identity, mesh in mapping.items():
                if type(mesh) is not dict or mesh.get("object_id") != identity:
                    raise ValueError("Delta mesh identity differs from its operation key")
                rebuilt[identity] = copy.deepcopy(mesh)
        candidate = {**copy.deepcopy(payload["metadata"]), "meshes": [rebuilt[identity] for identity in order]}
        current, encoded, fingerprint = _normalize(candidate, max_bytes)
        if encoded != _encode(candidate):
            raise ValueError("Replayed scene is not complete normalized data")
        if ("host_identity" not in current
                or _operations(previous, current) != payload):
            raise ValueError("Delta object changes or incarnation replacement classification is inconsistent")
        expected_invalidation = _invalidation(previous, current, payload)
    if _reference(current, fingerprint) != envelope["target"]:
        raise ValueError("Replayed target revision, fingerprint or document epoch mismatch")
    if len(encoded) != envelope["byte_counts"]["full_snapshot_bytes"]:
        raise ValueError("Replayed target byte length does not match its declaration")
    if envelope["invalidation"] != expected_invalidation:
        raise ValueError("Delta invalidation does not match the complete recorded changes")
    return copy.deepcopy(current)


__all__ = ["SCENE_DELTA_SCHEMA_VERSION", "DEFAULT_MAX_BYTES", "make_scene_delta", "apply_scene_delta"]
