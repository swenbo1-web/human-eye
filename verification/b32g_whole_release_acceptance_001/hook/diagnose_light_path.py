from importlib import import_module, util
import json
from pathlib import Path
import sys
import traceback


launcher, config_path = [Path(value).resolve() for value in sys.argv[1:]]
spec = util.spec_from_file_location("_isolated_hook_diagnostic_bootstrap", launcher)
entry = util.module_from_spec(spec)
sys.modules[spec.name] = entry
spec.loader.exec_module(entry)
proof = entry.validate_binding(expected_python=sys.executable)
sys.path.insert(0, proof["module_root"])
identity, _ = entry.verify_imported_runtime(proof)
hook = import_module("human_eye_hook")
entry.verify_imported_runtime(proof)
result = {"build_id": identity["build_id"], "hook_file": hook.__file__}
try:
    config = hook._leaf("agent_hooks")._read_object(config_path)
    light = hook._LightService(config_path, config)
    result["light_service"] = "constructed"
except Exception as exc:
    result.update(error_class=type(exc).__name__, error=str(exc), traceback=traceback.format_exc())
print(json.dumps(result))
