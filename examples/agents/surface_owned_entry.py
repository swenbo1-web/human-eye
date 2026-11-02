"""Install beside a pinned target bootstrap for the separate restore candidate."""
from pathlib import Path
import hashlib,importlib.util,sys

EXPECTED_TARGET_ENTRY_SHA256=''


def main():
    target=Path(__file__).resolve().with_name('target_runtime_entry.py');target_bytes=target.read_bytes()
    if len(EXPECTED_TARGET_ENTRY_SHA256)!=64 or hashlib.sha256(target_bytes).hexdigest()!=EXPECTED_TARGET_ENTRY_SHA256:
        raise RuntimeError('Surface entry requires its fixed installed target bootstrap')
    spec=importlib.util.spec_from_file_location('_human_eye_surface_fixed_target',target)
    module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;exec(compile(target_bytes,str(target),'exec',dont_inherit=True),module.__dict__)
    proof=module.validate_binding(expected_python=sys.executable)
    sys.path.insert(0,proof['module_root']);module.verify_imported_runtime(proof)
    from human_eye_plugin.surface_owned_mcp import main as serve
    serve()


if __name__=='__main__':main()
