"""Install beside a fixed target bootstrap; installer must pin its SHA first.

This template deliberately fails until configured by a trusted local installer.
It adds a separate owned MCP process and never changes the default live role.
"""
from pathlib import Path
import hashlib
import importlib.util
import sys

EXPECTED_TARGET_ENTRY_SHA256 = ''


def main():
    target=Path(__file__).resolve().with_name('target_runtime_entry.py')
    if (len(EXPECTED_TARGET_ENTRY_SHA256)!=64
            or hashlib.sha256(target.read_bytes()).hexdigest()!=EXPECTED_TARGET_ENTRY_SHA256):
        raise RuntimeError('Owned MCP entry requires its fixed installed target bootstrap')
    spec=importlib.util.spec_from_file_location('_human_eye_owned_fixed_target',target)
    module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
    proof=module.validate_binding(expected_python=sys.executable)
    sys.path.insert(0,proof['module_root']);module.verify_imported_runtime(proof)
    from human_eye_plugin.owned_task_mcp import main as serve
    serve()


if __name__=='__main__':main()
