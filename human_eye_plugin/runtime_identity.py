"""Read-only runtime identity shared by production transports and write gates.

The descriptor is a local implementation claim, never a host health check or an
execution authorization. Its build digest covers sorted runtime source bytes and
version metadata, captured once when this module loads. Hashing this file's
ordinary source bytes creates no recursion: no computed hash is written here.
"""
from __future__ import annotations

import hashlib
import copy
from importlib import metadata
import json
from pathlib import Path
import sys
from types import MappingProxyType


BASE_VERSION = "9.7.2"
IMPLEMENTATION_REVISION = "v21-perf020-o4-resident-task-host-20261106"
MCP_PROTOCOL_VERSION = "2025-03-26"
IDENTITY_SCHEMA_VERSION = "1.0"

_ROOT_MODULES = (
    "human_eye_hook.py",
    "human_eye_foveated_renderer.py",
    "native_3d_spatial_scratchpad.py",
    "module_2_low_token_mcp_scene_bridge.py",
    "module_3_1_mcp_protocol_ipc_engine.py",
    "module_3_2_vlm_grounding_closed_loop_agent.py",
    "module_3_3_closed_loop_control_engine.py",
)
_PIN_FIELDS = frozenset({
    "base_version", "implementation_revision", "build_id", "source_sha256",
    "source_kind", "protocol_version", "mode",
})


def _distribution(root: Path) -> tuple[str, str | None]:
    if (root / "pyproject.toml").is_file():
        return "source_checkout", None
    try:
        distribution = metadata.distribution("human-eye-spatial-plugin")
        marker = distribution.locate_file("human_eye_plugin/runtime_identity.py")
        if Path(marker).resolve() == Path(__file__).resolve():
            return "installed_distribution", distribution.version
    except metadata.PackageNotFoundError:
        pass
    return "unregistered_runtime", None


def _source_manifest(root: Path) -> list[dict]:
    # The rule is stable across checkout and wheel: all top-level Python runtime
    # files in these two packages, plus the declared root modules. Tests, state,
    # machine-local paths and bytecode never enter the digest.
    paths = {root / relative: relative for relative in _ROOT_MODULES}
    for package in ("human_eye_plugin", "human_eye_module1_operators"):
        directory = root / package
        if not (directory / "__init__.py").is_file():
            raise FileNotFoundError("Runtime package is incomplete: " + package)
        paths.update((path, package + "/" + path.name) for path in directory.glob("*.py"))
    # Canonical names follow the same two fixed package prefixes as enumeration.
    # Every call still enumerates and hashes all current source bytes; no stat
    # cache or cached successful source check is involved.
    entries = sorted((relative, path) for path, relative in paths.items())
    return [{"path": relative,
             "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
            for relative, path in entries]


def _capture_source_identity() -> dict:
    root = Path(__file__).resolve().parents[1]
    source_kind, distribution_version = _distribution(root)
    manifest = _source_manifest(root)
    digest_input = {"base_version": BASE_VERSION,
                    "implementation_revision": IMPLEMENTATION_REVISION,
                    "files": manifest}
    source_hash = hashlib.sha256(json.dumps(digest_input, sort_keys=True,
        separators=(",", ":"), ensure_ascii=True).encode("utf-8")).hexdigest()
    return {
        "schema_version": IDENTITY_SCHEMA_VERSION,
        "base_version": BASE_VERSION,
        "implementation_revision": IMPLEMENTATION_REVISION,
        "build_id": "sha256:" + source_hash,
        "build_id_basis": "runtime_source_bytes_and_version_metadata",
        "source_sha256": source_hash,
        "source_kind": source_kind,
        "distribution_version": distribution_version,
        "source_files": manifest,
        "source_hash_exclusions": [],
        "protocol_version": MCP_PROTOCOL_VERSION,
    }


# This process must never claim newly edited on-disk code as its loaded runtime.
# A fresh process computes its own snapshot. Import is local read-only work.
_SOURCE_IDENTITY = _capture_source_identity()


def _bind_task_source():
    """Bind frozen bytes and actual execution witnesses once at import."""
    finders = [finder for finder in sys.meta_path
               if getattr(finder, 'protocol', None) == 'human-eye-verified-source-v1']
    if not finders:
        return None, None
    try:
        if len(finders) != 1 or finders[0].root != _TASK_SOURCE_ROOT:
            raise ValueError('runtime_source_guard_mismatch')
        guard = finders[0]
        loader = sys.modules.get(type(guard).__module__)
        module = sys.modules[__name__]
        if (loader is None or vars(loader).get('SourceGuard') is not type(guard)
                or guard._executed.get(id(loader)) != (loader, 'human_eye_plugin/verified_source_loader.py')
                or guard._executed.get(id(module)) != (module, 'human_eye_plugin/runtime_identity.py')):
            raise ValueError('runtime_source_guard_unverified')
        sources = guard.sources
        if type(sources) is not MappingProxyType or any(type(blob) is not bytes for blob in sources.values()):
            raise ValueError('runtime_source_generation_unverified')
        manifest = {path: hashlib.sha256(blob).hexdigest() for path, blob in sources.items()}
        if manifest != {row['path']: row['sha256'] for row in _SOURCE_IDENTITY['source_files']}:
            raise ValueError('runtime_source_generation_changed')
        verify = guard.verify_loaded
        if (getattr(verify, '__self__', None) is not guard
                or getattr(verify, '__func__', None) is not vars(type(guard)).get('verify_loaded')
                or verify.__func__.__globals__ is not vars(loader)
                or verify.__func__.__qualname__ != 'SourceGuard.verify_loaded'
                or verify.__func__.__module__ != loader.__name__):
            raise ValueError('runtime_source_verifier_unverified')
        return (guard, sources, loader, module, verify), None
    except (AttributeError, OSError, TypeError, ValueError) as exc:
        return None, str(exc)


_TASK_SOURCE_ROOT = Path(__file__).resolve().parents[1]
_TASK_SOURCE_GENERATION, _TASK_SOURCE_ERROR = _bind_task_source()


def runtime_identity(*, mode: str = "live") -> dict:
    """Describe the loaded runtime without connecting or reading live state."""
    if mode not in {"live", "router", "demo"}:
        raise ValueError("Unknown runtime mode")
    return {
        **copy.deepcopy(_SOURCE_IDENTITY),
        "mode": mode,
        "capabilities": {
            "declared_only": True,
            "host_connection": "not_checked",
            "live_host_required": mode == "live",
            "scene_observation": True,
            "guarded_rigid_transform": mode == "live",
            "bounded_clearance_segment": mode == "live",
            "clearance_segment_support": "exact_world_axis_boxes_or_explicit_original_support_triangle" if mode == 'live' else None,
            "segment_inflight_cancel_supported": False,
            'task_correlated_request_evidence': mode == 'live',
            'observation_scene_transport': mode == 'live',
            'optional_observation_task_brief': mode == 'live',
            'operation_local_observation_reuse': mode == 'live',
            'observation_reuse_scope': 'paired_fresh_capture_128_vertices_or_8_meshes'
                if mode == 'live' else None,
            'layered_capability_diagnostics': mode in {'live','router'},
            "execution_scope": "independent_static_rigid_mesh_endpoint_geometry"
                if mode == "live" else "no_live_execution_authority",
            "swept_path_certified": False,
            "model_task_benefit_certified": False,
        },
    }


def check_source_drift() -> dict:
    """Compare current disk source with the process's startup source snapshot.

    This is a read-only compatibility check, not a reload or an authorization.
    Production writes must reject both changed and unreadable source. A later
    operator-approved restart loads a new snapshot; this function never updates
    the existing one, including after a failed check.
    """
    result = {"compatible": False, "check_complete": False, "status": "unavailable",
              "reasons": [], "loaded_build_id": _SOURCE_IDENTITY["build_id"],
              "disk_build_id": None,
              "changed_files": [], "added_files": [], "removed_files": []}
    try:
        current = _capture_source_identity()
    except (OSError, ValueError) as exc:
        result["reasons"] = ["runtime_source_check_failed"]
        result["error"] = type(exc).__name__ + ": " + str(exc)
        return result
    loaded = {item["path"]: item["sha256"] for item in _SOURCE_IDENTITY["source_files"]}
    disk = {item["path"]: item["sha256"] for item in current["source_files"]}
    changed = sorted(key for key in loaded.keys() & disk.keys() if loaded[key] != disk[key])
    compatible = current["build_id"] == _SOURCE_IDENTITY["build_id"]
    result.update(compatible=compatible, check_complete=True,
                  status="unchanged" if compatible else "changed",
                  reasons=[] if compatible else ["runtime_source_changed_restart_required"],
                  disk_build_id=current["build_id"], changed_files=changed,
                  added_files=sorted(disk.keys() - loaded.keys()),
                  removed_files=sorted(loaded.keys() - disk.keys()))
    # Only a controlled entry installs this witness. Ordinary SDK imports
    # remain ordinary source comparisons and acquire no verified-execution claim.
    try:
        import sys
        for finder in sys.meta_path:
            if getattr(finder,'protocol',None)=='human-eye-verified-source-v1' and finder.root==Path(__file__).resolve().parents[1]:
                finder.verify_loaded()
    except (OSError,ValueError) as exc:
        result.update(compatible=False,status='unavailable',reasons=['runtime_executed_source_unverified'],error=str(exc))
    return result


def check_task_source() -> dict:
    """Check bound object identity for explicit readonly tasks.

    Disk diagnosis, new lazy execution and writes retain their original checks.
    Ordinary SDK imports have no execution-generation claim and compare disk.
    """
    finders = [finder for finder in sys.meta_path
               if getattr(finder, 'protocol', None) == 'human-eye-verified-source-v1']
    if _TASK_SOURCE_GENERATION is None and _TASK_SOURCE_ERROR is None and not finders:
        return check_source_drift()
    result = {'compatible': False, 'check_complete': False, 'status': 'unavailable',
              'loaded_build_id': _SOURCE_IDENTITY['build_id'], 'disk_build_id': None,
              'source_check_scope': 'bound_generation_identity',
              'disk_status': 'disk_not_checked', 'reasons': ['runtime_executed_source_unverified']}
    try:
        if _TASK_SOURCE_GENERATION is None:
            raise ValueError(_TASK_SOURCE_ERROR or 'runtime_source_guard_not_bound')
        guard, sources, loader, module, verify = _TASK_SOURCE_GENERATION
        if (len(finders) != 1 or finders[0] is not guard or guard.root != _TASK_SOURCE_ROOT
                or guard.sources is not sources):
            raise ValueError('runtime_source_generation_changed')
        if sys.modules.get(__name__) is not module:
            raise ValueError('verified_source_preloaded_module:' + __name__)
        if (sys.modules.get(loader.__name__) is not loader
                or vars(loader).get('SourceGuard') is not type(guard)):
            raise ValueError('verified_source_preloaded_module:' + loader.__name__)
        current_verify = guard.verify_loaded
        if (getattr(current_verify, '__self__', None) is not guard
                or getattr(current_verify, '__func__', None) is not verify.__func__):
            raise ValueError('runtime_source_verifier_changed')
    except (AttributeError, OSError, TypeError, ValueError) as exc:
        result['error'] = type(exc).__name__ + ': ' + str(exc)
        return result
    result.update(compatible=True, check_complete=True, status='loaded_generation', reasons=[])
    return result


def validate_expected_identity(expected: dict | None, actual: dict | None = None) -> dict:
    """Compare optional trusted pins; a match itself grants no write authority.

    Unknown, empty or malformed constraints are rejected rather than ignored.
    For example ``{"implementation_revision": "...", "build_id": "sha256:..."}``
    pins both implementation and source bytes. Missing pins mean no local pin was
    requested, not that a peer's identity has been independently authenticated.
    """
    if expected is not None:
        if not isinstance(expected, dict) or not expected:
            raise ValueError("expected_identity must be a nonempty object or null")
        unknown = set(expected) - _PIN_FIELDS
        if unknown:
            raise ValueError("Unknown expected_identity fields: " + ", ".join(sorted(unknown)))
        if any(not isinstance(value, str) or not value.strip() for value in expected.values()):
            raise ValueError("expected_identity values must be nonempty strings")
    observed = runtime_identity() if actual is None else actual
    if not isinstance(observed, dict):
        raise ValueError("actual identity must be an object")
    reasons = ["identity_mismatch:" + key for key, value in (expected or {}).items()
               if observed.get(key) != value]
    return {"compatible": not reasons, "pins_requested": expected is not None,
            "reasons": reasons,
            "expected": None if expected is None else dict(expected),
            "actual": {key: observed.get(key) for key in sorted(_PIN_FIELDS)},
            "authorization": "identity_comparison_only"}


__all__ = ["BASE_VERSION", "IMPLEMENTATION_REVISION", "MCP_PROTOCOL_VERSION",
           "runtime_identity", "validate_expected_identity", "check_source_drift", "check_task_source"]
