"""Validate exported schemas with the existing compatible jsonschema runtime."""

import hashlib
import importlib.metadata
import json
from pathlib import Path
import sys

from jsonschema import Draft202012Validator


def main():
    request = json.load(sys.stdin)
    checks = []
    for job in request["jobs"]:
        Draft202012Validator.check_schema(job["schema"])
        validator = Draft202012Validator(job["schema"])
        for case in job["cases"]:
            errors = list(validator.iter_errors(case["value"]))
            actual = not errors
            assert actual is case["valid"], (job["name"], case, [error.message for error in errors])
            checks.append(dict(job=job["name"], value=case["value"], expected_valid=case["valid"],
                               actual_valid=actual, error_messages=[error.message for error in errors]))
    sources = []
    packages = ("jsonschema", "jsonschema_specifications", "referencing", "rpds", "attr", "attrs")
    for name, module in sorted(sys.modules.items()):
        path = getattr(module, "__file__", None)
        if path and name.split(".")[0] in packages:
            data = Path(path).read_bytes()
            sources.append(dict(module=name, path=path, bytes=len(data), sha256=hashlib.sha256(data).hexdigest()))
    interpreter = Path(sys.executable).read_bytes()
    result = dict(schema="surface_scan_external_schema_validation_v1", checks=checks,
                  schema_count=len(request["jobs"]), check_count=len(checks),
                  python=sys.executable, python_version=sys.version,
                  python_sha256=hashlib.sha256(interpreter).hexdigest(),
                  jsonschema_version=importlib.metadata.version("jsonschema"), sources=sources,
                  new_Blender_model_business_API_runs=0)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
