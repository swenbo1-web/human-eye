"""Fixed installed-target bootstrap; run with the bound Python -I -B.

The adjacent binding is an installation receipt, not an execution permission.
Only the four literal roles below are dispatched. No module/root/exec option
exists, and the dependency environment is reused without adding global paths.
"""
from __future__ import annotations

import hashlib
import importlib
from importlib import metadata, util
import json
from pathlib import Path
import sys


RELEASE_NAME = "9.7.2+20261029.v1.core.r1"
DEPENDENCY_PYTHON = Path("D:/hefe/.human-eye/releases/9.7.2+20261028.support.discovery.r1/.venv/Scripts/python.exe")
SOURCE_SHA256 = "4eff4e3b43d8b3e0a33ee2180b4276596e8ace527a615bc68370add23ee3e1ae"
IDENTITY = {"base_version": "9.7.2", "implementation_revision": "v20-v1-core-20261029",
            "source_sha256": SOURCE_SHA256, "build_id": "sha256:" + SOURCE_SHA256,
            "distribution_version": RELEASE_NAME}
ROOT_MODULES = ("human_eye_hook.py", "human_eye_foveated_renderer.py", "native_3d_spatial_scratchpad.py",
                "module_2_low_token_mcp_scene_bridge.py", "module_3_1_mcp_protocol_ipc_engine.py",
                "module_3_2_vlm_grounding_closed_loop_agent.py", "module_3_3_closed_loop_control_engine.py")
ROLES = {"mcp": "serve", "hook": "hook", "identity": "identity", "admin": "admin"}
_VERIFIED_SOURCES = None
_VERIFIED_ROOT = None
_SOURCE_GUARD = None
_BINDING_KEYS = {"schema_version", "kind", "target_release", "site_packages", "dependency_python",
                 "launcher_sha256", "admin_sha256", "identity", "source_files"}


class BindingError(ValueError):
    pass


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _read(path, limit=4 * 1024 * 1024):
    if not path.is_file() or path.stat().st_size > limit:
        raise BindingError("Missing or unbounded binding/runtime file: " + str(path))
    raw = path.read_bytes()
    if len(raw) > limit:
        raise BindingError("File grew beyond its limit: " + str(path))
    return raw


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise BindingError("Duplicate binding key: " + key)
        result[key] = value
    return result


def _fixed_path(value, expected):
    if not isinstance(value, str) or any(c in value for c in "\x00\r\n"):
        raise BindingError("Binding path must be a literal absolute path")
    candidate = Path(value)
    if not candidate.is_absolute() or candidate != expected or candidate.resolve() != expected:
        raise BindingError("Binding path differs from the fixed installed location")


def validate_binding(*, expected_python=None):
    """Read-only proof, also used by the pinned administration recognizer."""
    entry = Path(__file__).resolve()
    release = entry.parent.parent
    if (entry.name != "target_runtime_entry.py" or entry.parent.name != "admin"
            or release.name != RELEASE_NAME or release.parent.name != "releases"
            or release.parent.parent.name != ".human-eye"
            or Path(__file__).absolute() != entry):
        raise BindingError("Bootstrap is outside its fixed managed release location")
    site = release / "site-packages"
    if site.resolve() != site:
        raise BindingError("Installed site-packages escapes the managed release")
    binding_path = entry.with_name("RUNTIME_BINDING.json")
    admin = entry.with_name("installed_release.py")
    raw = _read(binding_path)
    binding = json.loads(raw.decode("utf-8"), object_pairs_hook=_object,
                         parse_constant=lambda value: (_ for _ in ()).throw(BindingError("Nonfinite binding value")))
    if (not isinstance(binding, dict) or set(binding) != _BINDING_KEYS
            or binding["schema_version"] != "1.0" or binding["kind"] != "human_eye_fixed_target_runtime"
            or binding["identity"] != IDENTITY):
        raise BindingError("Unsupported fixed runtime binding/identity")
    for key, expected in (("target_release", release), ("site_packages", site),
                          ("dependency_python", DEPENDENCY_PYTHON.resolve())):
        _fixed_path(binding[key], expected)
    if not DEPENDENCY_PYTHON.is_file():
        raise BindingError("The fixed dependency Python is unavailable")
    if expected_python is not None and Path(expected_python).resolve() != DEPENDENCY_PYTHON.resolve():
        raise BindingError("Launcher uses another dependency interpreter")
    launcher_hash = _sha(_read(entry, 128 * 1024))
    admin_hash = _sha(_read(admin, 1024 * 1024))
    if binding["launcher_sha256"] != launcher_hash or binding["admin_sha256"] != admin_hash:
        raise BindingError("Bootstrap/administration bytes differ from the installation binding")
    paths = {site / name for name in ROOT_MODULES}
    for package in ("human_eye_plugin", "human_eye_module1_operators"):
        directory = site / package
        if not (directory / "__init__.py").is_file():
            raise BindingError("Incomplete installed runtime package")
        paths.update(directory.glob("*.py"))
    manifest = [];sources = {}
    for path in sorted(paths, key=lambda item: item.relative_to(site).as_posix()):
        if path.resolve() != path or not path.resolve().is_relative_to(site):
            raise BindingError("Runtime source escapes the installed target")
        relative = path.relative_to(site).as_posix();blob = _read(path)
        sources[relative] = blob
        manifest.append({"path": relative, "sha256": _sha(blob)})
    digest = _sha(json.dumps({"base_version": IDENTITY["base_version"],
        "implementation_revision": IDENTITY["implementation_revision"], "files": manifest},
        sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8"))
    if len(manifest) != 68 or manifest != binding["source_files"] or digest != SOURCE_SHA256:
        raise BindingError("Installed target source manifest/build differs from the fixed 68-file core")
    distributions = [dist for dist in metadata.distributions(path=[str(site)])
                     if str(dist.metadata.get("Name", "")).lower().replace("_", "-") == "human-eye-spatial-plugin"]
    if (len(distributions) != 1 or distributions[0].version != RELEASE_NAME
            or Path(distributions[0].locate_file("human_eye_plugin/runtime_identity.py")).resolve()
                != site / "human_eye_plugin/runtime_identity.py"):
        raise BindingError("Installed distribution metadata does not identify the fixed target")
    global _VERIFIED_SOURCES, _VERIFIED_ROOT
    _VERIFIED_SOURCES = sources;_VERIFIED_ROOT = site
    return {"kind": "fixed_target_bootstrap", "entry": str(entry), "binding": str(binding_path),
            "target_release": str(release), "module_root": str(site),
            "dependency_python": str(DEPENDENCY_PYTHON.resolve()), "launcher_sha256": launcher_hash,
            "binding_sha256": _sha(raw), "admin_sha256": admin_hash, "source_file_count": len(manifest),
            "source_sha256": digest, "identity": dict(IDENTITY),
            "invocation_prefix": [str(DEPENDENCY_PYTHON.resolve()), "-I", "-B", str(entry)],
            "roles": dict(ROLES)}


def verify_imported_runtime(proof):
    global _SOURCE_GUARD
    root = Path(proof["module_root"])
    if _VERIFIED_ROOT != root or _VERIFIED_SOURCES is None:
        raise BindingError("Runtime source snapshot was not validated by this entry")
    manifest = [{"path": name, "sha256": _sha(blob)} for name, blob in sorted(_VERIFIED_SOURCES.items())]
    if _SOURCE_GUARD is None:
        for finder in sys.meta_path:
            if getattr(finder, 'protocol', None) == 'human-eye-verified-source-v1' and finder.root == root:
                if dict(finder.sources) != _VERIFIED_SOURCES:raise BindingError("Runtime source generation differs")
                _SOURCE_GUARD = finder;break
        if _SOURCE_GUARD is None:
            path = root / 'human_eye_plugin/verified_source_loader.py'
            blob = _VERIFIED_SOURCES.get('human_eye_plugin/verified_source_loader.py')
            if blob is None:raise BindingError("Verified source loader is not in the fixed manifest")
            spec = util.spec_from_file_location('_human_eye_fixed_source_loader', path)
            helper = util.module_from_spec(spec);sys.modules[spec.name] = helper
            exec(compile(blob,str(path),'exec',dont_inherit=True),helper.__dict__)
            _SOURCE_GUARD = helper.install(root,manifest,sources=_VERIFIED_SOURCES,bootstrap_module=helper)
    _SOURCE_GUARD.verify_loaded()
    module = importlib.import_module("human_eye_plugin.runtime_identity")
    identity = module.runtime_identity(mode="live")
    if identity.get("source_kind") != "installed_distribution" or any(
            identity.get(key) != value for key, value in IDENTITY.items()):
        raise BindingError("Imported runtime identity differs from the fixed installed target")
    root = Path(proof["module_root"])
    roots = {Path(name).stem for name in ROOT_MODULES}
    origins = {}
    for name, loaded in list(sys.modules.items()):
        if (name in roots or name == "human_eye_plugin" or name.startswith("human_eye_plugin.")
                or name == "human_eye_module1_operators" or name.startswith("human_eye_module1_operators.")):
            origin = getattr(loaded, "__file__", None)
            if origin is None or not Path(origin).resolve().is_relative_to(root):
                raise BindingError("Engine import escaped fixed installed site-packages: " + name)
            origins[name] = str(Path(origin).resolve())
    if module.check_source_drift().get("compatible") is not True:
        raise BindingError("Installed target source changed after import")
    _SOURCE_GUARD.verify_loaded()
    return identity, origins


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    try:
        if not sys.flags.isolated or not sys.dont_write_bytecode:
            raise BindingError("Invoke the bound dependency Python with -I -B")
        if not args or args[0] not in ROLES.values():
            raise BindingError("Usage: target_runtime_entry.py {serve|hook|identity|admin} [role options]")
        role = args.pop(0)
        if role == "identity" and args:
            raise BindingError("identity accepts no options")
        proof = validate_binding(expected_python=sys.executable)
        sys.path.insert(0, proof["module_root"])
        verify_imported_runtime(proof)
        if role == "identity":
            identity, origins = verify_imported_runtime(proof)
            print(json.dumps({"runtime_identity": identity, "launcher": proof,
                              "python": str(Path(sys.executable).resolve()), "prefix": str(Path(sys.prefix).resolve()),
                              "module_origins": origins}, sort_keys=True))
            return 0
        if role == "admin":
            path = Path(proof["entry"]).with_name("installed_release.py")
            spec = util.spec_from_file_location("_human_eye_installed_release_admin", path)
            module = util.module_from_spec(spec)
            sys.modules[spec.name] = module
            blob = _read(path,1024*1024)
            if _sha(blob) != proof["admin_sha256"]:raise BindingError("Administration source changed")
            exec(compile(blob,str(path),"exec",dont_inherit=True),module.__dict__)
            # Only this pinned bootstrap dispatch can grant the outside-prefix
            # import proof; the helper re-reads the receipt every time.
            module._FIXED_TARGET_BOOTSTRAP = sys.modules[__name__]
            verify_imported_runtime(proof)
            result = module.main(args)
        elif role == "serve":
            module = importlib.import_module("human_eye_plugin.production_server")
            verify_imported_runtime(proof)
            result = module.main(args)
        else:
            module = importlib.import_module("human_eye_hook")
            verify_imported_runtime(proof)
            result = module.main(args)
        verify_imported_runtime(proof)
        return result
    except (BindingError, OSError, ValueError) as exc:
        print("Fixed runtime bootstrap refused: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
