"""Install beside a fixed target bootstrap for static constraint observation."""
from pathlib import Path
import hashlib,importlib.util,sys
EXPECTED_TARGET_ENTRY_SHA256=''


def main():
    target=Path(__file__).resolve().with_name('target_runtime_entry.py')
    if len(EXPECTED_TARGET_ENTRY_SHA256)!=64 or hashlib.sha256(target.read_bytes()).hexdigest()!=EXPECTED_TARGET_ENTRY_SHA256:
        raise RuntimeError('Constraint reader requires its fixed installed target bootstrap')
    spec=importlib.util.spec_from_file_location('_human_eye_fixed_constraint_reader',target);module=importlib.util.module_from_spec(spec)
    sys.modules[spec.name]=module;spec.loader.exec_module(module);proof=module.validate_binding(expected_python=sys.executable)
    sys.path.insert(0,proof['module_root']);module.verify_imported_runtime(proof)
    from human_eye_plugin.rig_constraint_process import main as inspect
    return inspect()


if __name__=='__main__':raise SystemExit(main())
