"""The single authorized no-image common-source path check."""

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import traceback


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    arguments = parser.parse_args()
    directory = Path(__file__).resolve().parent
    namespace = directory.parents[1]
    specification = importlib.util.spec_from_file_location("_routed_readonly_bridge", namespace / "bridge.py")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    config = json.loads(arguments.config.read_bytes())
    request = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
        "name": "execute_python", "arguments": {"code":
            "import human_eye_plugin.geometry_safety as gs; open(gs.__file__,'rb').read(1); print(42)"}}}
    owner = None
    response = None
    close = None
    errors = []
    passed = False
    try:
        owner = module.Owner(config)
        response = owner.handle(request)
        body = json.loads(response["result"]["content"][0]["text"])
        passed = (response["result"]["isError"] is False and body["error"] is None
                  and body["stdout"] == "42\n" and not body["stderr"])
    except BaseException as error:
        errors.append({"type": type(error).__name__, "message": str(error), "traceback": traceback.format_exc()})
    finally:
        if owner is not None:
            try:
                close = owner.close(True, errors)
                passed = passed and close["confirmed"] is True
            except BaseException as error:
                errors.append({"type": type(error).__name__, "message": str(error), "traceback": traceback.format_exc()})
                passed = False
        receipt = {"schema": "routed-native-readonly-preparation-v1", "attempt": 1,
            "passed": passed, "request": request, "response": response, "owner_close": close, "errors": errors,
            "actual_execute_python_requests": int(response is not None), "model_calls": 0,
            "product_observation_calls": 0, "raster_attempts": 0, "fake_CLI": False,
            "server_thread_started": False,
            "scope": "Actual isolated N Owner and source-guard bootstrap. Exactly one ordinary Python read; no model, observation, renderer or transport server.",
            "source_sha256": {name: hashlib.sha256((namespace / name).read_bytes()).hexdigest()
                              for name in ("bridge.py", "native_tools.py", "bootstrap.py")}}
        with (directory / "RESULT.json").open("x", encoding="utf8", newline="\n") as stream:
            json.dump(receipt, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
    print(json.dumps({"passed": passed, "attempt": 1, "execute_python_requests": 1 if response is not None else 0,
                      "models": 0, "observations": 0, "rasters": 0}))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
